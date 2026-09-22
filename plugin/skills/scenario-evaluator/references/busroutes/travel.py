"""In-memory travel-time lookup over one loaded matrix."""

from __future__ import annotations

from busroutes.models import Point
from busroutes.ordering import Matrix


def travel_from_matrix(points: list[Point], matrix: Matrix):
    index: dict[tuple[float, float], int] = {}
    for i, point in enumerate(points):
        index.setdefault((point.lat, point.lon), i)

    def travel(a: Point, b: Point) -> int:
        return matrix[index[(a.lat, a.lon)]][index[(b.lat, b.lon)]]

    return travel
