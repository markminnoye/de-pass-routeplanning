"""Overpass client: De Lijn / TEC / NMBS stops in a bounding box, cached on disk.

Used only to decorate map.html. A failed fetch must not abort scenario evaluation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Literal

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY_VERSION = 1
USER_AGENT = "de-pass-routeplanning/busroutes (schoolbus scenario evaluator)"

OperatorKind = Literal["delijn", "tec", "nmbs"]
Fetcher = Callable[[str, str], dict]


class OverpassError(RuntimeError):
    pass


def overlay_cache_dir(tomtom_cache_dir: Path | None) -> Path | None:
    """Sibling of the TomTom cache: `.cache/tomtom` → `.cache/overpass`."""
    if tomtom_cache_dir is None:
        return None
    return Path(tomtom_cache_dir).parent / "overpass"


def empty_collection() -> dict:
    return {"type": "FeatureCollection", "features": []}


def _coords_from_geometry(geom: dict) -> list[tuple[float, float]]:
    kind = geom.get("type")
    coords = geom.get("coordinates")
    if kind == "Point" and coords and len(coords) >= 2:
        return [(float(coords[0]), float(coords[1]))]
    if kind == "LineString" and coords:
        return [(float(p[0]), float(p[1])) for p in coords if len(p) >= 2]
    if kind in ("MultiPoint", "MultiLineString", "Polygon") and coords:
        out: list[tuple[float, float]] = []
        for part in coords:
            if part and isinstance(part[0], (int, float)):
                out.append((float(part[0]), float(part[1])))
            else:
                out.extend((float(p[0]), float(p[1])) for p in part if len(p) >= 2)
        return out
    return []


def bbox_from_geojson(geojson: dict, pad_frac: float = 0.05) -> tuple[float, float, float, float]:
    """(south, west, north, east), padded ~5% around all scenario coordinates."""
    pairs: list[tuple[float, float]] = []
    for feature in geojson.get("features") or []:
        geom = feature.get("geometry") or {}
        pairs.extend(_coords_from_geometry(geom))
    if not pairs:
        raise OverpassError("geen coördinaten in GeoJSON om een bbox voor OV-haltes te maken")
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    dlat = max(north - south, 0.01)
    dlon = max(east - west, 0.01)
    return (
        south - dlat * pad_frac,
        west - dlon * pad_frac,
        north + dlat * pad_frac,
        east + dlon * pad_frac,
    )


def _round_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    s, w, n, e = bbox
    return (round(s, 4), round(w, 4), round(n, 4), round(e, 4))


def build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = _round_bbox(bbox)
    box = f"{s},{w},{n},{e}"
    return f"""[out:json][timeout:25];
(
  nwr["ref:De_Lijn"]({box});
  nwr["operator"~"De Lijn",i]({box});
  nwr["ref:TEC"]({box});
  nwr["network"~"^TEC"]({box});
  nwr["operator"~"(^|;[[:space:]]*)TEC($|;|[[:space:]])",i]({box});
  nwr["railway"~"^(station|halt)$"]["operator"~"NMBS|SNCB",i]({box});
  nwr["railway"~"^(station|halt)$"]["uic_ref"~"^88"]({box});
);
out center;
"""


def _tag(tags: dict, key: str) -> str:
    raw = tags.get(key)
    return raw.strip() if isinstance(raw, str) else ""


def _is_delijn(tags: dict) -> bool:
    if _tag(tags, "ref:De_Lijn"):
        return True
    return "de lijn" in _tag(tags, "operator").lower()


def _is_tec(tags: dict) -> bool:
    if _tag(tags, "ref:TEC"):
        return True
    network = _tag(tags, "network")
    if any(part.strip().upper().startswith("TEC") for part in network.replace(",", ";").split(";")):
        return True
    return bool(re.search(r"(^|;\s*)tec(\s|$|;)", _tag(tags, "operator"), re.IGNORECASE))


def _is_nmbs(tags: dict) -> bool:
    if _tag(tags, "railway") not in {"station", "halt"}:
        return False
    op = _tag(tags, "operator").lower()
    if "nmbs" in op or "sncb" in op:
        return True
    return _tag(tags, "uic_ref").startswith("88")


def _kinds(tags: dict) -> list[tuple[OperatorKind, str]]:
    if _is_nmbs(tags):
        return [("nmbs", _tag(tags, "uic_ref") or _tag(tags, "ref"))]
    found: list[tuple[OperatorKind, str]] = []
    if _is_delijn(tags):
        found.append(("delijn", _tag(tags, "ref:De_Lijn") or _tag(tags, "ref")))
    if _is_tec(tags):
        found.append(("tec", _tag(tags, "ref:TEC") or _tag(tags, "ref")))
    return found


def _element_latlon(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _dedup_key(kind: OperatorKind, ref: str, lat: float, lon: float) -> tuple:
    if ref:
        return (kind, ref)
    return (kind, round(lat, 5), round(lon, 5))


def parse_overpass(payload: dict) -> dict:
    """Filter Overpass JSON down to a GeoJSON FeatureCollection of transit stops."""
    features: list[dict] = []
    seen: set[tuple] = set()
    for el in payload.get("elements") or []:
        if not isinstance(el, dict):
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        pos = _element_latlon(el)
        if pos is None:
            continue
        lat, lon = pos
        osm_id = f"{el.get('type', 'node')}/{el.get('id', '')}"
        name = _tag(tags, "name") or _tag(tags, "name:nl") or _tag(tags, "name:fr")
        for kind, ref in _kinds(tags):
            key = _dedup_key(kind, ref, lat, lon)
            if key in seen:
                continue
            seen.add(key)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "kind": "transit",
                        "name": name or ref or osm_id,
                        "operator_kind": kind,
                        "ref": ref,
                        "osm_id": osm_id,
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def _digest(bbox: tuple[float, float, float, float]) -> str:
    payload = {"v": QUERY_VERSION, "bbox": list(_round_bbox(bbox))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, path)


def _http_overpass(url: str, query: str, retries: int = 5) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode())
            if not isinstance(payload, dict):
                raise OverpassError("Overpass gaf geen JSON-object terug")
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 504, 502} and attempt < retries - 1:
                time.sleep(0.5 * 2**attempt)
                continue
            raw = exc.read().decode("utf-8", errors="replace")[:1000]
            raise OverpassError(f"Overpass HTTP {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise OverpassError(f"Overpass netwerkfout: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise OverpassError("Overpass gaf ongeldige JSON terug") from exc
    raise OverpassError("Overpass: server bleef overbelast na herhaalde pogingen")


def fetch_transit_stops(
    bbox: tuple[float, float, float, float],
    cache_dir: Path | None,
    fetch: Fetcher = _http_overpass,
) -> dict:
    """GeoJSON of De Lijn / TEC / NMBS stops. Raises OverpassError on network/parse failure."""
    digest = _digest(bbox)
    path = Path(cache_dir) / f"{digest}.json" if cache_dir else None
    if path is not None:
        cached = _read_json(path)
        if isinstance(cached, dict) and cached.get("type") == "FeatureCollection":
            return cached
    payload = fetch(OVERPASS_URL, build_query(bbox))
    if not isinstance(payload, dict):
        raise OverpassError("Overpass gaf geen JSON-object terug")
    if "remark" in payload and "elements" not in payload:
        raise OverpassError(f"Overpass: {payload['remark']}")
    geojson = parse_overpass(payload)
    if path is not None:
        _write_json(path, geojson)
    return geojson


def load_transit_overlay(
    geojson: dict,
    tomtom_cache_dir: Path | None,
    fetch: Fetcher = _http_overpass,
) -> tuple[dict, str | None]:
    """Never raises: (collection, waarschuwing of None)."""
    try:
        bbox = bbox_from_geojson(geojson)
        stops = fetch_transit_stops(bbox, overlay_cache_dir(tomtom_cache_dir), fetch=fetch)
        return stops, None
    except OverpassError as exc:
        return empty_collection(), str(exc)
