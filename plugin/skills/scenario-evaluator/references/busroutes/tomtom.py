"""Thin TomTom REST client: calculateRoute (legs + geometry) and Matrix Routing v2.

Both calls are cached on disk (key = hash of the request) so repeated runs are
free and reproducible. Limits (checked 14/09/2026):
- calculateRoute: max 150 waypoints per request.
- synchronous matrix: max 100 cells with a concrete departAt; max 200 cells with
  departAt "any" + traffic "historical" + routeType "fastest" (what we use).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from busroutes.models import Point

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
MATRIX_URL = "https://api.tomtom.com/routing/matrix/2"
REVERSE_GEOCODE_URL = "https://api.tomtom.com/search/2/reverseGeocode"
MATRIX_MAX_CELLS = 200
ROUTE_MAX_WAYPOINTS = 150

Traffic = Literal["historical", "live"]


class TomTomError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteLeg:
    travel_time_s: int
    length_m: int
    points: list[Point]


@dataclass(frozen=True)
class RouteResult:
    legs: list[RouteLeg]

    @property
    def travel_time_s(self) -> int:
        return sum(leg.travel_time_s for leg in self.legs)

    @property
    def length_m(self) -> int:
        return sum(leg.length_m for leg in self.legs)


class GeoClient(Protocol):
    def route(self, points: list[Point], depart_at: datetime) -> RouteResult: ...

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        """Travel time in seconds, time-independent (departAt 'any'), for ordering only."""
        ...


Fetcher = Callable[[str, dict | None], dict]


def _http_json(url: str, body: dict | None, retries: int = 5) -> dict:
    """GET/POST JSON. Retries with backoff on HTTP 429 (TomTom rate limit, ~5 QPS)."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if body is not None else "GET",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(0.5 * 2**attempt)
                continue
            raw = exc.read().decode("utf-8", errors="replace")[:1000]
            raise TomTomError(f"TomTom HTTP {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise TomTomError(f"TomTom netwerkfout: {exc.reason}") from exc
    raise TomTomError("TomTom: rate limit bleef actief na herhaalde pogingen")


class TomTomClient:
    def __init__(
        self,
        api_key: str,
        cache_dir: Path | None,
        traffic: Traffic = "historical",
        fetch: Fetcher = _http_json,
    ) -> None:
        if not api_key:
            raise TomTomError("TOMTOM_API_KEY ontbreekt")
        self._key = api_key
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._traffic = traffic
        self._fetch = fetch

    # -- caching -----------------------------------------------------------

    def _cached(self, kind: str, request: dict, do_fetch: Callable[[], dict]) -> dict:
        if self._cache_dir is None:
            return do_fetch()
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        path = self._cache_dir / kind / f"{digest}.json"
        if path.exists():
            return json.loads(path.read_text())
        payload = do_fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        return payload

    # -- calculateRoute ----------------------------------------------------

    def route(self, points: list[Point], depart_at: datetime) -> RouteResult:
        if len(points) < 2:
            raise TomTomError("route vraagt minstens 2 punten")
        if len(points) > ROUTE_MAX_WAYPOINTS:
            raise TomTomError(f"route: {len(points)} punten > {ROUTE_MAX_WAYPOINTS}")
        locations = ":".join(f"{p.lat:.6f},{p.lon:.6f}" for p in points)
        params = {
            "travelMode": "car",
            "routeType": "fastest",
            "traffic": "true" if self._traffic == "live" else "false",
            "departAt": depart_at.isoformat(timespec="seconds"),
            "routeRepresentation": "polyline",
            "computeTravelTimeFor": "all",
        }
        request = {"locations": locations, **params}
        url = f"{ROUTE_URL}/{locations}/json?{urllib.parse.urlencode({**params, 'key': self._key})}"
        payload = self._cached("route", request, lambda: self._fetch(url, None))
        return parse_route(payload)

    # -- matrix ------------------------------------------------------------

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        result: list[list[int]] = [[0] * len(destinations) for _ in origins]
        rows_per_chunk = max(1, MATRIX_MAX_CELLS // len(destinations))
        for start in range(0, len(origins), rows_per_chunk):
            chunk = origins[start : start + rows_per_chunk]
            body = {
                "origins": [{"point": {"latitude": p.lat, "longitude": p.lon}} for p in chunk],
                "destinations": [
                    {"point": {"latitude": p.lat, "longitude": p.lon}} for p in destinations
                ],
                "options": {
                    "departAt": "any",
                    "traffic": "historical",
                    "travelMode": "car",
                    "routeType": "fastest",
                },
            }
            url = f"{MATRIX_URL}?key={self._key}"
            payload = self._cached("matrix", body, lambda u=url, b=body: self._fetch(u, b))
            for cell in payload.get("data", []):
                summary = cell.get("routeSummary")
                if summary is None:
                    err = cell.get("detailedError", {})
                    raise TomTomError(
                        f"matrix-cel {cell.get('originIndex')}->{cell.get('destinationIndex')}: "
                        f"{err.get('code')} {err.get('message')}"
                    )
                result[start + cell["originIndex"]][cell["destinationIndex"]] = int(
                    summary["travelTimeInSeconds"]
                )
        return result

    # -- reverse geocode (snap to street) -----------------------------------

    def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point | None:
        """Nearest position on a normal street (local street or arterial), or None."""
        params = {
            "returnRoadUse": "true",
            "roadUse": "LocalStreet,Arterial",
            "radius": str(radius_m),
        }
        request = {"lat": round(point.lat, 6), "lon": round(point.lon, 6), **params}
        url = (
            f"{REVERSE_GEOCODE_URL}/{point.lat:.6f},{point.lon:.6f}.json?"
            f"{urllib.parse.urlencode({**params, 'key': self._key})}"
        )
        payload = self._cached("reverse_geocode", request, lambda: self._fetch(url, None))
        for address in payload.get("addresses", []):
            pos = address.get("position")
            if pos:
                lat, lon = pos.split(",")
                return Point(float(lat), float(lon))
        return None


def parse_route(payload: dict) -> RouteResult:
    try:
        route = payload["routes"][0]
    except (KeyError, IndexError) as exc:
        raise TomTomError(f"onverwacht calculateRoute-antwoord: {str(payload)[:300]}") from exc
    legs = [
        RouteLeg(
            travel_time_s=int(leg["summary"]["travelTimeInSeconds"]),
            length_m=int(leg["summary"]["lengthInMeters"]),
            points=[Point(p["latitude"], p["longitude"]) for p in leg.get("points", [])],
        )
        for leg in route["legs"]
    ]
    return RouteResult(legs=legs)
