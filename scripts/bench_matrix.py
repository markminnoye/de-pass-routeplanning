"""One travel-time model for every solver in the full benchmark.

The sample matrix stores TomTom cells per reference bus, not the pairs between
buses. A hybrid (real cell when it exists, estimate otherwise) would make a
cross-bus edge a different kind of number than a within-bus edge. This module
fits one straight line through every positive sample cell and uses that line
for every pair, so order and assignment see the same matrix.

    seconds = max(1, round(alpha + beta * haversine_m))

The diagonal is 0. The model is symmetric. Kilometres in evaluate stay
haversine × the offline road factor; they are not TomTom lengths.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from busroutes.geo import haversine_m
from busroutes.models import Point
from busroutes.offline import OFFLINE_ROAD_FACTOR, OfflineClient
from busroutes.tomtom import RouteLeg, RouteResult, Usage


def point_key(point: Point) -> str:
    """Same 6-decimal identity as the matrix cache."""
    return f"{point.lat:.6f},{point.lon:.6f}"


def _point_from_key(key: str) -> Point:
    lat_s, lon_s = key.split(",")
    return Point(float(lat_s), float(lon_s))


@dataclass(frozen=True)
class TravelModel:
    """Least squares of travel time (s) on great-circle distance (m)."""

    alpha_s: float
    beta_s_per_m: float
    n_cells: int
    r2: float
    median_abs_pct: float
    median_speed_m_s: float

    def seconds(self, meters: float) -> int:
        if meters < 1:
            return 0
        return max(1, round(self.alpha_s + self.beta_s_per_m * meters))


def fit_travel_model(matrix_dir: Path) -> TravelModel:
    """Fit on every positive cell under matrix_dir. Path order is sorted."""
    distances: list[float] = []
    times: list[float] = []
    for path in sorted(matrix_dir.rglob("*.json")):
        origin = _point_from_key(path.stem)
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            continue
        for dest_key in sorted(payload):
            raw = payload[dest_key]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            seconds = float(raw)
            if seconds <= 0:
                continue
            meters = haversine_m(origin, _point_from_key(str(dest_key)))
            if meters < 1:
                continue
            distances.append(meters)
            times.append(seconds)
    n_cells = len(distances)
    if n_cells < 2:
        raise RuntimeError(f"te weinig matrixcellen in {matrix_dir}")
    n = float(n_cells)
    sum_x = sum(distances)
    sum_y = sum(times)
    sum_xx = sum(x * x for x in distances)
    sum_xy = sum(x * y for x, y in zip(distances, times, strict=True))
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        raise RuntimeError(f"geen afstandsspreiding in {matrix_dir}")
    beta = (n * sum_xy - sum_x * sum_y) / denom
    alpha = (sum_y - beta * sum_x) / n
    mean_y = sum_y / n
    ss_tot = sum((y - mean_y) ** 2 for y in times)
    residual = (alpha + beta * x for x in distances)
    ss_res = sum((y - yhat) ** 2 for y, yhat in zip(times, residual, strict=True))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    abs_pct = [abs(y - (alpha + beta * x)) / y for x, y in zip(distances, times, strict=True)]
    speeds = [x / y for x, y in zip(distances, times, strict=True)]
    return TravelModel(
        alpha_s=alpha,
        beta_s_per_m=beta,
        n_cells=n_cells,
        r2=r2,
        median_abs_pct=statistics.median(abs_pct),
        median_speed_m_s=statistics.median(speeds),
    )


class SpeedMatrixClient(OfflineClient):
    """OfflineClient whose every pair comes from one TravelModel."""

    def __init__(self, model: TravelModel) -> None:
        self.model = model
        self.usage = Usage()

    def pair_seconds(self, origin: Point, dest: Point) -> int:
        if point_key(origin) == point_key(dest):
            return 0
        return self.model.seconds(haversine_m(origin, dest))

    def route(self, points: list[Point], depart_at: object) -> RouteResult:
        del depart_at
        legs = [
            RouteLeg(
                travel_time_s=self.pair_seconds(origin, dest),
                length_m=round(haversine_m(origin, dest) * OFFLINE_ROAD_FACTOR),
                points=[origin, dest],
            )
            for origin, dest in zip(points, points[1:], strict=False)
        ]
        return RouteResult(legs=legs)

    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]:
        return [[self.pair_seconds(origin, dest) for dest in destinations] for origin in origins]


def freeze_travel(client: SpeedMatrixClient, points: list[Point]):
    """Dict lookup of pair_seconds, for the stdlib search hot path."""
    unique: dict[str, Point] = {}
    for point in points:
        unique.setdefault(point_key(point), point)
    table: dict[str, dict[str, int]] = {}
    for origin in unique.values():
        row = table.setdefault(point_key(origin), {})
        for dest in unique.values():
            row[point_key(dest)] = client.pair_seconds(origin, dest)

    def travel(origin: Point, dest: Point) -> int:
        return table[point_key(origin)][point_key(dest)]

    return travel


def load_imbalance(counts: list[int]) -> int:
    """Pupils on the fullest bus minus pupils on the emptiest, empty buses included."""
    if not counts:
        return 0
    return max(counts) - min(counts)
