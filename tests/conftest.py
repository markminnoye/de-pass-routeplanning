"""Shared fixtures: a tiny two-bus world and a fake geo client (no network)."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from busroutes.geo import haversine_m
from busroutes.models import Bus, Point, School, Student
from busroutes.tomtom import RouteLeg, RouteResult, Usage, _point_key

SCHOOL = Point(50.7782, 4.8960)


class FakeGeoClient:
    """Straight-line 'routing' at 36 km/h (10 m/s): 1 m == 0.1 s. Counts calls."""

    speed_m_s = 10.0

    def __init__(self) -> None:
        self.route_calls: list[list[Point]] = []
        self.matrix_calls: list[tuple[list[Point], list[Point]]] = []
        self.snap_calls: list[Point] = []
        self.usage = Usage()

    def route(self, points: list[Point], depart_at: datetime) -> RouteResult:
        self.route_calls.append(list(points))
        legs = []
        for a, b in zip(points, points[1:], strict=False):
            length = haversine_m(a, b)
            legs.append(
                RouteLeg(
                    travel_time_s=round(length / self.speed_m_s),
                    length_m=round(length),
                    points=[a, b],
                )
            )
        return RouteResult(legs=legs)

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        self.matrix_calls.append((list(origins), list(destinations)))
        return [[round(haversine_m(o, d) / self.speed_m_s) for d in destinations] for o in origins]

    def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point:
        del radius_m
        self.snap_calls.append(point)
        return point


@pytest.fixture(autouse=True)
def no_live_basemap_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI tests must not download OSM tiles. Tile servers block CI runners,
    and this suite stays offline. maptiles unit tests call the loader directly.
    """
    monkeypatch.setattr("busroutes.cli.load_basemap_tiles", lambda *_a, **_k: ({}, None))


@pytest.fixture
def school() -> School:
    return School(id="school", name="de pass", point=SCHOOL, target_arrival=time(8, 20))


@pytest.fixture
def students() -> dict[str, Student]:
    pts = {
        "s001": Point(50.7900, 4.9000),  # ~1.3 km NNE
        "s002": Point(50.8000, 4.9100),  # ~2.6 km NNE
        "s003": Point(50.7600, 4.8800),  # ~2.3 km SSW
        "s004": Point(50.7500, 4.8700),  # ~3.6 km SSW
    }
    return {sid: Student(id=sid, point=p, zone="test") for sid, p in pts.items()}


@pytest.fixture
def buses() -> dict[str, Bus]:
    return {
        "bus1": Bus(id="bus1", capacity=2, start=SCHOOL),
        "bus2": Bus(id="bus2", capacity=2, start=SCHOOL),
    }


@pytest.fixture
def fake_client() -> FakeGeoClient:
    return FakeGeoClient()


# Hand-matrix world (WP3 solver). Dummy coords are unique only so `_point_key`
# distinguishes them; they are not geographic. Letters match the travel-time
# table: S = school, W/X/Y/Z = stops `w`/`x`/`y`/`z` (one student each).
HAND_POINTS = {
    "S": Point(50.000000, 4.000000),
    "W": Point(50.100000, 4.100000),
    "X": Point(50.200000, 4.200000),
    "Y": Point(50.300000, 4.300000),
    "Z": Point(50.400000, 4.400000),
}

_HAND_LABELS = ("S", "W", "X", "Y", "Z")
_HAND_SPECIFIC = {
    ("S", "W"): 10,
    ("S", "Z"): 5000,
    ("W", "S"): 40,
    ("W", "X"): 400,
    ("X", "W"): 30,
    ("X", "Y"): 400,
    ("Y", "X"): 30,
    ("Y", "Z"): 400,
    ("Z", "S"): 40,
    ("Z", "Y"): 30,
}
_HAND_FILL_S = 50_000


def _hand_seconds() -> dict[tuple[str, str], int]:
    """Complete 5×5: specified cells, 0 on the diagonal, 50000 everywhere else."""
    seconds: dict[tuple[str, str], int] = {}
    for origin in _HAND_LABELS:
        for dest in _HAND_LABELS:
            key = (_point_key(HAND_POINTS[origin]), _point_key(HAND_POINTS[dest]))
            if origin == dest:
                seconds[key] = 0
            else:
                seconds[key] = _HAND_SPECIFIC.get((origin, dest), _HAND_FILL_S)
    return seconds


class HandMatrixClient:
    """GeoClient backed by a fixed asymmetric in-memory travel-time matrix."""

    def __init__(self, seconds: dict[tuple[str, str], int] | None = None) -> None:
        self._seconds = seconds if seconds is not None else _hand_seconds()
        self.usage = Usage()

    def _lookup(self, origin: Point, dest: Point) -> int:
        return self._seconds[_point_key(origin), _point_key(dest)]

    def route(self, points: list[Point], depart_at: datetime) -> RouteResult:
        del depart_at
        legs = [
            RouteLeg(travel_time_s=self._lookup(a, b), length_m=0, points=[a, b])
            for a, b in zip(points, points[1:], strict=False)
        ]
        return RouteResult(legs=legs)

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        return [[self._lookup(o, d) for d in destinations] for o in origins]

    def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point:
        del radius_m
        return point


@pytest.fixture
def hand_school() -> School:
    return School(id="school", name="de pass", point=HAND_POINTS["S"], target_arrival=time(8, 20))


@pytest.fixture
def hand_students() -> dict[str, Student]:
    return {
        label.lower(): Student(id=label.lower(), point=HAND_POINTS[label], zone="hand")
        for label in "WXYZ"
    }


@pytest.fixture
def hand_buses() -> dict[str, Bus]:
    start = HAND_POINTS["S"]
    return {
        "bus1": Bus(id="bus1", capacity=10, start=start),
        "bus2": Bus(id="bus2", capacity=10, start=start),
    }


@pytest.fixture
def hand_client() -> HandMatrixClient:
    return HandMatrixClient()
