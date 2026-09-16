"""OfflineClient reads a packed matrix from disk and never talks to TomTom."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from busroutes.geo import haversine_m
from busroutes.models import Point
from busroutes.offline import OFFLINE_ROAD_FACTOR, OfflineClient, OfflineError
from busroutes.tomtom import MATRIX_OPTIONS, TomTomClient, _digest, _point_key

A = Point(50.778200, 4.896000)
B = Point(50.790000, 4.900000)
C = Point(50.800000, 4.910000)
WHEN = datetime(2026, 9, 15, 7, 30)


def write_origin_row(cells_dir: Path, origin: Point, row: dict[str, int]) -> Path:
    path = cells_dir / _digest(MATRIX_OPTIONS)[:16] / f"{_point_key(origin)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row))
    return path


def test_route_leg_travel_time_matches_cell(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(B): 120})
    result = OfflineClient(tmp_path).route([A, B], WHEN)
    assert result.legs[0].travel_time_s == 120


def test_route_leg_length_is_haversine_times_road_factor(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(B): 120})
    result = OfflineClient(tmp_path).route([A, B], WHEN)
    assert result.legs[0].length_m == round(haversine_m(A, B) * OFFLINE_ROAD_FACTOR)


def test_missing_pair_raises_offline_error_naming_fetch_command(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(B): 120})
    with pytest.raises(OfflineError, match="busroutes data fetch-matrix --dry-run") as exc:
        OfflineClient(tmp_path).route([A, C], WHEN)
    assert "1" in str(exc.value)


def test_matrix_returns_cell_without_network(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(A): 0, _point_key(B): 120, _point_key(C): 240})
    write_origin_row(tmp_path, B, {_point_key(A): 110, _point_key(B): 0, _point_key(C): 90})
    times = OfflineClient(tmp_path).matrix([A, B], [A, B, C])
    assert times == [[0, 120, 240], [110, 0, 90]]


def test_route_builds_one_leg_per_consecutive_pair(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(B): 120})
    write_origin_row(tmp_path, B, {_point_key(C): 90})
    result = OfflineClient(tmp_path).route([A, B, C], WHEN)
    assert [leg.travel_time_s for leg in result.legs] == [120, 90]
    assert result.legs[0].points == [A, B]
    assert result.legs[1].points == [B, C]


def test_empty_cells_dir_reports_count_of_missing_pairs(tmp_path):
    with pytest.raises(OfflineError, match="busroutes data fetch-matrix --dry-run") as exc:
        OfflineClient(tmp_path).matrix([A, B], [C])
    assert "2" in str(exc.value)


def test_usage_stays_zero_after_route_and_matrix(tmp_path):
    write_origin_row(tmp_path, A, {_point_key(A): 0, _point_key(B): 120})
    client = OfflineClient(tmp_path)
    client.route([A, B], WHEN)
    client.matrix([A], [A, B])
    assert client.usage.transactions == 0


def test_reads_cells_written_by_tomtom_client(tmp_path):
    def fetch(url, body):
        return {
            "data": [
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "routeSummary": {"travelTimeInSeconds": 77, "lengthInMeters": 1000},
                }
            ]
        }

    cells_dir = tmp_path / "matrix"
    TomTomClient("k", tmp_path / "cache", fetch=fetch, cells_dir=cells_dir).matrix([A], [B])
    result = OfflineClient(cells_dir).route([A, B], WHEN)
    assert result.legs[0].travel_time_s == 77
