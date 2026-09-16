"""Offline GeoClient: travel times from a packed matrix, no network."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from busroutes.geo import haversine_m
from busroutes.models import Point
from busroutes.tomtom import (
    MATRIX_OPTIONS,
    RouteLeg,
    RouteResult,
    Usage,
    _digest,
    _point_key,
    _read_json,
)

OFFLINE_ROAD_FACTOR = 1.3  # km-schatting: grote-cirkel × wegenfactor, geen TomTom-lengte.


class OfflineError(RuntimeError):
    pass


class OfflineClient:
    def __init__(self, cells_dir: Path) -> None:
        self._cells_dir = Path(cells_dir)
        self.usage = Usage()

    def _cells_path(self, origin: Point) -> Path:
        return self._cells_dir / _digest(MATRIX_OPTIONS)[:16] / f"{_point_key(origin)}.json"

    def _read_cells(self, origin: Point) -> dict[str, int]:
        payload = _read_json(self._cells_path(origin))
        return payload if isinstance(payload, dict) else {}

    def _require(self, pairs: list[tuple[Point, Point]]) -> dict[tuple[str, str], int]:
        cache: dict[str, dict[str, int]] = {}
        found: dict[tuple[str, str], int] = {}
        missing: set[tuple[str, str]] = set()
        for origin, dest in pairs:
            origin_key, dest_key = _point_key(origin), _point_key(dest)
            row = cache.setdefault(origin_key, self._read_cells(origin))
            if dest_key in row:
                found[(origin_key, dest_key)] = int(row[dest_key])
            else:
                missing.add((origin_key, dest_key))
        if missing:
            raise OfflineError(
                f"{len(missing)} matrixparen ontbreken; vul aan met "
                "busroutes data fetch-matrix --dry-run"
            )
        return found

    def route(self, points: list[Point], depart_at: datetime) -> RouteResult:
        del depart_at
        pairs = list(zip(points, points[1:], strict=False))
        cells = self._require(pairs)
        return RouteResult(
            legs=[
                RouteLeg(
                    travel_time_s=cells[(_point_key(a), _point_key(b))],
                    length_m=round(haversine_m(a, b) * OFFLINE_ROAD_FACTOR),
                    points=[a, b],
                )
                for a, b in pairs
            ]
        )

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        pairs = [(o, d) for o in origins for d in destinations]
        cells = self._require(pairs)
        return [[cells[(_point_key(o), _point_key(d))] for d in destinations] for o in origins]
