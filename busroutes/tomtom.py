"""Thin TomTom REST client: calculateRoute (legs + geometry) and Matrix Routing v2.

Answers are cached on disk (see below) so repeated runs are free and reproducible.
Limits and costs, checked 15/09/2026:

- calculateRoute: max 150 waypoints per request, billed as one request.
- synchronous matrix: max 100 cells with a concrete departAt; max 200 cells with
  departAt "any" + traffic "historical" + routeType "fastest" (what we use).
- matrix billing is per *dimension*, not per cell: 5 x max(origins, destinations) once
  both exceed 5, and origins x destinations otherwise. A cell in a big request costs
  5 / min(origins, destinations) transactions, so square blocks are the cheapest shape
  and long thin strips the most expensive. See `matrix_transactions`.

Because of that formula the matrix cache stores *individual pairs* rather than whole
requests: a pair that was paid for once is never paid for again, even when a later
scenario groups the same points differently over the buses.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from busroutes.geo import haversine_m
from busroutes.models import Point

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
MATRIX_URL = "https://api.tomtom.com/routing/matrix/2"
REVERSE_GEOCODE_URL = "https://api.tomtom.com/search/2/reverseGeocode"
MATRIX_MAX_CELLS = 200
MATRIX_FREE_DIMENSION = 5
ROUTE_MAX_WAYPOINTS = 150

# The only option set that allows 200 cells per request; also the cache namespace.
MATRIX_OPTIONS = {
    "departAt": "any",
    "traffic": "historical",
    "travelMode": "car",
    "routeType": "fastest",
}

Traffic = Literal["historical", "live"]


class TomTomError(RuntimeError):
    pass


def matrix_transactions(origins: int, destinations: int) -> int:
    """Billable transactions for one matrix request, per TomTom's dimension formula."""
    if origins > MATRIX_FREE_DIMENSION and destinations > MATRIX_FREE_DIMENSION:
        return MATRIX_FREE_DIMENSION * max(origins, destinations)
    return origins * destinations


@dataclass
class Usage:
    """What a run cost, and what the cache saved. Transactions == what TomTom bills."""

    matrix_transactions: int = 0
    matrix_cells_fetched: int = 0
    matrix_cells_cached: int = 0
    route_requests: int = 0
    routes_cached: int = 0
    geocode_requests: int = 0
    geocodes_cached: int = 0

    @property
    def transactions(self) -> int:
        return self.matrix_transactions + self.route_requests + self.geocode_requests


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
    usage: Usage

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


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _point_key(p: Point) -> str:
    """Cache identity of a point. Coincident stops collapse onto the same key."""
    return f"{p.lat:.6f},{p.lon:.6f}"


def _unique(points: Iterable[Point]) -> list[Point]:
    seen: dict[str, Point] = {}
    for p in points:
        seen.setdefault(_point_key(p), p)
    return list(seen.values())


def _read_json(path: Path) -> object | None:
    """None when the file is absent or truncated, so a damaged cache refetches
    instead of crashing the run."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: object) -> None:
    """Atomic, so an interrupted run cannot leave half a cache entry behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, path)


def _matrix_body(origins: list[Point], destinations: list[Point]) -> dict:
    return {
        "origins": [{"point": {"latitude": p.lat, "longitude": p.lon}} for p in origins],
        "destinations": [{"point": {"latitude": p.lat, "longitude": p.lon}} for p in destinations],
        "options": dict(MATRIX_OPTIONS),
    }


def _split_counts(total: int, parts: int) -> list[tuple[int, int]]:
    """[(block size, how many blocks), ...] for `total` cut into `parts` equal-ish pieces."""
    base, extra = divmod(total, parts)
    counts = [(base + 1, extra)] if extra else []
    if parts - extra:
        counts.append((base, parts - extra))
    return counts


def _cheapest_split(rows: int, cols: int, max_cells: int) -> tuple[list[int], list[int]]:
    """Block sizes that cover a rows x cols matrix for the fewest transactions.

    Cells are capped per request, and cost per cell is 5 / min(rows, cols), so the
    answer is always the most square split that still fits under the cap.
    """
    best: tuple[int, int, int] | None = None
    for n_rows in range(1, rows + 1):
        row_counts = _split_counts(rows, n_rows)
        for n_cols in range(1, cols + 1):
            col_counts = _split_counts(cols, n_cols)
            if row_counts[0][0] * col_counts[0][0] > max_cells:
                continue
            cost = sum(
                r_n * c_n * matrix_transactions(r, c)
                for r, r_n in row_counts
                for c, c_n in col_counts
            )
            if best is None or cost < best[0]:
                best = (cost, n_rows, n_cols)
    if best is None:
        raise TomTomError(f"matrixblok {rows}x{cols} past niet in {max_cells} cellen per request")
    _, n_rows, n_cols = best
    return _sizes(rows, n_rows), _sizes(cols, n_cols)


def _sizes(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + 1] * extra + [base] * (parts - extra)


def _chunks(items: list[int], sizes: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    start = 0
    for size in sizes:
        out.append(items[start : start + size])
        start += size
    return out


Plan = list[tuple[list[int], list[int]]]


def _rectangle(rows: list[int], cols: list[int], max_cells: int) -> Plan:
    row_sizes, col_sizes = _cheapest_split(len(rows), len(cols), max_cells)
    return [
        (row_block, col_block)
        for row_block in _chunks(rows, row_sizes)
        for col_block in _chunks(cols, col_sizes)
    ]


def plan_cost(plan: Plan) -> int:
    return sum(matrix_transactions(len(rows), len(cols)) for rows, cols in plan)


def plan_blocks(missing: dict[int, set[int]], max_cells: int = MATRIX_MAX_CELLS) -> Plan:
    """Turn the still-unknown (origin, destination) pairs into matrix requests.

    Two candidate plans, whichever is cheaper. Fetching exactly the gaps groups origins
    that miss the same destinations into rectangles; that wins when the gaps are
    regular, e.g. one stop added to a known set. But a scattered cache fragments into
    single rows, and a request with one origin is billed per cell, so re-buying some
    known cells inside one big square-blocked rectangle can cost less.
    """
    if not missing:
        return []
    groups: dict[frozenset[int], list[int]] = {}
    for row, cols in missing.items():
        groups.setdefault(frozenset(cols), []).append(row)
    exact: Plan = []
    for cols_key, rows in sorted(groups.items(), key=lambda kv: min(kv[1])):
        exact += _rectangle(sorted(rows), sorted(cols_key), max_cells)
    whole = _rectangle(sorted(missing), sorted(set().union(*missing.values())), max_cells)
    return min(exact, whole, key=plan_cost)


class TomTomClient:
    def __init__(
        self,
        api_key: str,
        cache_dir: Path | None,
        traffic: Traffic = "historical",
        fetch: Fetcher = _http_json,
        dry_run: bool = False,
        cells_dir: Path | None = None,
    ) -> None:
        if not api_key:
            raise TomTomError("TOMTOM_API_KEY ontbreekt")
        self._key = api_key
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cells_dir = Path(cells_dir) if cells_dir else None
        self._traffic = traffic
        self._fetch = fetch
        self._dry_run = dry_run
        self.usage = Usage()

    # -- request-level cache (one call in, one payload out) -----------------

    def _cache_path(self, kind: str, request: dict) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / kind / f"{_digest(request)}.json"

    def _read_cached(self, kind: str, request: dict) -> dict | None:
        path = self._cache_path(kind, request)
        if path is None:
            return None
        payload = _read_json(path)
        return payload if isinstance(payload, dict) else None

    def _write_cached(self, kind: str, request: dict, payload: dict) -> None:
        path = self._cache_path(kind, request)
        if path is not None and not self._dry_run:
            _write_json(path, payload)

    # -- pair-level matrix cache -------------------------------------------

    def _cells_path(self, origin: Point) -> Path | None:
        options = _digest(MATRIX_OPTIONS)[:16]
        name = f"{_point_key(origin)}.json"
        if self._cells_dir is not None:
            return self._cells_dir / options / name
        if self._cache_dir is None:
            return None
        return self._cache_dir / "cells" / options / name

    def _read_cells(self, origin: Point) -> dict[str, int]:
        path = self._cells_path(origin)
        if path is None:
            return {}
        payload = _read_json(path)
        return payload if isinstance(payload, dict) else {}

    def _write_cells(self, origin: Point, row: dict[str, int]) -> None:
        path = self._cells_path(origin)
        if path is None or self._dry_run:
            return
        _write_json(path, {**self._read_cells(origin), **row})

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
        cached = self._read_cached("route", request)
        if cached is not None:
            self.usage.routes_cached += 1
            return parse_route(cached)
        self.usage.route_requests += 1
        if self._dry_run:
            return RouteResult(legs=[RouteLeg(0, 0, []) for _ in range(len(points) - 1)])
        url = f"{ROUTE_URL}/{locations}/json?{urllib.parse.urlencode({**params, 'key': self._key})}"
        payload = self._fetch(url, None)
        self._write_cached("route", request, payload)
        return parse_route(payload)

    # -- matrix ------------------------------------------------------------

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        if not origins or not destinations:
            return [[] for _ in origins]
        # Plan over distinct points; report back over the caller's own lists, which may
        # repeat a point (a bus that starts and ends at the school does).
        u_origins, u_dests = _unique(origins), _unique(destinations)
        u_dest_keys = [_point_key(p) for p in u_dests]
        cells = {_point_key(p): dict(self._read_cells(p)) for p in u_origins}

        missing = _gaps(u_origins, u_dest_keys, cells)
        if missing:
            self._harvest_legacy(origins, destinations, cells)
            missing = _gaps(u_origins, u_dest_keys, cells)
        requested = len(u_origins) * len(u_dests)
        self.usage.matrix_cells_cached += requested - sum(len(g) for g in missing.values())

        for row_block, col_block in plan_blocks(missing):
            self._fill_block(
                [u_origins[i] for i in row_block], [u_dests[j] for j in col_block], cells
            )
        dest_keys = [_point_key(p) for p in destinations]
        return [[_cell(cells, _point_key(o), k) for k in dest_keys] for o in origins]

    def _fill_block(
        self, origins: list[Point], destinations: list[Point], cells: dict[str, dict[str, int]]
    ) -> None:
        self.usage.matrix_transactions += matrix_transactions(len(origins), len(destinations))
        self.usage.matrix_cells_fetched += len(origins) * len(destinations)
        if self._dry_run:
            for origin in origins:
                row = cells.setdefault(_point_key(origin), {})
                for dest in destinations:
                    row.setdefault(_point_key(dest), round(haversine_m(origin, dest)))
            return

        payload = self._fetch(f"{MATRIX_URL}?key={self._key}", _matrix_body(origins, destinations))
        fresh: dict[str, dict[str, int]] = {}
        failure: str | None = None
        for cell in payload.get("data", []):
            origin = origins[cell["originIndex"]]
            dest = destinations[cell["destinationIndex"]]
            summary = cell.get("routeSummary")
            if summary is None:
                err = cell.get("detailedError", {})
                failure = failure or (
                    f"matrix-cel {_point_key(origin)}->{_point_key(dest)}: "
                    f"{err.get('code')} {err.get('message')}"
                )
                continue
            fresh.setdefault(_point_key(origin), {})[_point_key(dest)] = int(
                summary["travelTimeInSeconds"]
            )
        # Persist before raising: TomTom charged for this request either way.
        for key, row in fresh.items():
            cells.setdefault(key, {}).update(row)
        for origin in origins:
            row = fresh.get(_point_key(origin))
            if row:
                self._write_cells(origin, row)
        if failure is not None:
            raise TomTomError(failure)

    def _harvest_legacy(
        self, origins: list[Point], destinations: list[Point], cells: dict[str, dict[str, int]]
    ) -> None:
        """Fill the pair cache from the older request-level matrix cache.

        Costs nothing and keeps a warm `.cache/tomtom/matrix/` (row strips, one payload
        per chunk) usable now that pairs are cached individually.
        """
        if self._cache_dir is None:
            return
        legacy = self._cache_dir / "matrix"
        if not legacy.is_dir():
            return
        rows_per_chunk = max(1, MATRIX_MAX_CELLS // len(destinations))
        for start in range(0, len(origins), rows_per_chunk):
            chunk = origins[start : start + rows_per_chunk]
            payload = _read_json(legacy / f"{_digest(_matrix_body(chunk, destinations))}.json")
            if not isinstance(payload, dict):
                continue
            harvested: dict[str, dict[str, int]] = {}
            for cell in payload.get("data", []):
                summary = cell.get("routeSummary")
                if summary is None:
                    continue
                origin_key = _point_key(chunk[cell["originIndex"]])
                dest_key = _point_key(destinations[cell["destinationIndex"]])
                harvested.setdefault(origin_key, {})[dest_key] = int(summary["travelTimeInSeconds"])
            for key, row in harvested.items():
                cells.setdefault(key, {}).update(row)
            for origin in chunk:
                row = harvested.get(_point_key(origin))
                if row:
                    self._write_cells(origin, row)

    # -- reverse geocode (snap to street) -----------------------------------

    def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point | None:
        """Nearest position on a normal street (local street or arterial), or None."""
        params = {
            "returnRoadUse": "true",
            "roadUse": "LocalStreet,Arterial",
            "radius": str(radius_m),
        }
        request = {"lat": round(point.lat, 6), "lon": round(point.lon, 6), **params}
        payload = self._read_cached("reverse_geocode", request)
        if payload is not None:
            self.usage.geocodes_cached += 1
        else:
            self.usage.geocode_requests += 1
            if self._dry_run:
                return point
            url = (
                f"{REVERSE_GEOCODE_URL}/{point.lat:.6f},{point.lon:.6f}.json?"
                f"{urllib.parse.urlencode({**params, 'key': self._key})}"
            )
            payload = self._fetch(url, None)
            self._write_cached("reverse_geocode", request, payload)
        for address in payload.get("addresses", []):
            pos = address.get("position")
            if pos:
                lat, lon = pos.split(",")
                return Point(float(lat), float(lon))
        return None


def _gaps(
    origins: list[Point], dest_keys: list[str], cells: dict[str, dict[str, int]]
) -> dict[int, set[int]]:
    """Indices of the (origin, destination) pairs that are not in the cache yet."""
    missing: dict[int, set[int]] = {}
    for i, origin in enumerate(origins):
        row = cells.get(_point_key(origin), {})
        gaps = {j for j, key in enumerate(dest_keys) if key not in row}
        if gaps:
            missing[i] = gaps
    return missing


def _cell(cells: dict[str, dict[str, int]], origin_key: str, dest_key: str) -> int:
    try:
        return cells[origin_key][dest_key]
    except KeyError as exc:
        raise TomTomError(f"matrix-cel {origin_key}->{dest_key} ontbreekt na ophalen") from exc


def usage_report(usage: Usage, dry_run: bool = False) -> str:
    head = "TomTom-raming (niets opgehaald)" if dry_run else "TomTom-verbruik"
    return (
        f"{head}: {usage.transactions} transacties "
        f"(matrix {usage.matrix_transactions} voor {usage.matrix_cells_fetched} cellen, "
        f"routes {usage.route_requests}, geocoding {usage.geocode_requests}) · "
        f"uit cache: {usage.matrix_cells_cached} cellen, {usage.routes_cached} routes, "
        f"{usage.geocodes_cached} geocodes"
    )


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
