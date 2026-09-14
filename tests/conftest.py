"""Shared fixtures: a tiny two-bus world and a fake geo client (no network)."""

from __future__ import annotations

import math
from datetime import datetime, time

import pytest

from busroutes.models import Bus, Point, School, Student
from busroutes.tomtom import RouteLeg, RouteResult

SCHOOL = Point(50.7782, 4.8960)


def haversine_m(a: Point, b: Point) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class FakeGeoClient:
    """Straight-line 'routing' at 36 km/h (10 m/s): 1 m == 0.1 s. Counts calls."""

    speed_m_s = 10.0

    def __init__(self) -> None:
        self.route_calls: list[list[Point]] = []
        self.matrix_calls: list[tuple[list[Point], list[Point]]] = []

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
