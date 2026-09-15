import json
from datetime import datetime

import pytest

from busroutes.models import Point
from busroutes.tomtom import (
    MATRIX_MAX_CELLS,
    TomTomClient,
    TomTomError,
    _digest,
    _matrix_body,
    matrix_transactions,
    parse_route,
    plan_blocks,
    plan_cost,
)

ROUTE_PAYLOAD = {
    "routes": [
        {
            "summary": {"lengthInMeters": 300, "travelTimeInSeconds": 30},
            "legs": [
                {
                    "summary": {"lengthInMeters": 100, "travelTimeInSeconds": 10},
                    "points": [
                        {"latitude": 50.0, "longitude": 4.0},
                        {"latitude": 50.1, "longitude": 4.1},
                    ],
                },
                {
                    "summary": {"lengthInMeters": 200, "travelTimeInSeconds": 20},
                    "points": [
                        {"latitude": 50.1, "longitude": 4.1},
                        {"latitude": 50.2, "longitude": 4.2},
                    ],
                },
            ],
        }
    ]
}


def test_parse_route_reads_legs_and_points():
    result = parse_route(ROUTE_PAYLOAD)
    assert [leg.travel_time_s for leg in result.legs] == [10, 20]
    assert result.length_m == 300
    assert result.legs[1].points[-1] == Point(50.2, 4.2)


def test_parse_route_rejects_garbage():
    with pytest.raises(TomTomError):
        parse_route({"error": "nope"})


def test_route_builds_url_and_caches(tmp_path):
    calls: list[str] = []

    def fetch(url, body):
        calls.append(url)
        return ROUTE_PAYLOAD

    client = TomTomClient("k", tmp_path, traffic="historical", fetch=fetch)
    pts = [Point(50.0, 4.0), Point(50.1, 4.1), Point(50.2, 4.2)]
    when = datetime(2026, 9, 15, 7, 30)
    client.route(pts, when)
    client.route(pts, when)
    assert len(calls) == 1, "second call must come from the cache"
    url = calls[0]
    assert "50.000000,4.000000:50.100000,4.100000:50.200000,4.200000" in url
    assert "traffic=false" in url
    assert "departAt=2026-09-15T07%3A30%3A00" in url
    assert "key=k" in url


def test_matrix_is_chunked_and_reassembled(tmp_path):
    bodies: list[dict] = []

    def fetch(url, body):
        bodies.append(body)
        data = []
        for oi, o in enumerate(body["origins"]):
            for di, d in enumerate(body["destinations"]):
                secs = round(abs(o["point"]["latitude"] - d["point"]["latitude"]) * 1000)
                data.append(
                    {
                        "originIndex": oi,
                        "destinationIndex": di,
                        "routeSummary": {"travelTimeInSeconds": secs, "lengthInMeters": 1},
                    }
                )
        return {"data": data}

    client = TomTomClient("k", None, fetch=fetch)
    pts = [Point(50.0 + i / 100, 4.0) for i in range(30)]  # 30x30 = 900 cells
    m = client.matrix(pts, pts)
    assert len(bodies) > 1
    assert all(len(b["origins"]) * len(b["destinations"]) <= 200 for b in bodies)
    assert all(b["options"]["departAt"] == "any" for b in bodies)
    assert m[0][0] == 0
    assert m[0][29] == 290 == m[29][0]
    assert m[7][3] == 40


def line(n: int) -> list[Point]:
    return [Point(50.0 + i / 100, 4.0) for i in range(n)]


def matrix_fetcher(record: list[dict]):
    """Stub matrix endpoint: travel time == the latitude gap in milli-degrees."""

    def fetch(url, body):
        record.append(body)
        data = []
        for oi, o in enumerate(body["origins"]):
            for di, d in enumerate(body["destinations"]):
                secs = round(abs(o["point"]["latitude"] - d["point"]["latitude"]) * 1000)
                data.append(
                    {
                        "originIndex": oi,
                        "destinationIndex": di,
                        "routeSummary": {"travelTimeInSeconds": secs, "lengthInMeters": 1},
                    }
                )
        return {"data": data}

    return fetch


def test_matrix_transactions_follows_tomtom_dimension_formula():
    # The examples from TomTom's Discounted Transaction Billing page.
    assert matrix_transactions(2, 3) == 6
    assert matrix_transactions(5, 5) == 25
    assert matrix_transactions(1, 100) == 100
    assert matrix_transactions(5, 100) == 500
    assert matrix_transactions(6, 100) == 500
    assert matrix_transactions(1000, 1000) == 5000


def test_blocks_are_square_because_a_cell_costs_five_over_the_short_side():
    missing = {i: set(range(22)) for i in range(22)}
    blocks = plan_blocks(missing)
    assert all(len(rows) * len(cols) <= MATRIX_MAX_CELLS for rows, cols in blocks)
    assert plan_cost(blocks) == 220  # 4 blocks of 11x11; row strips of 9x22 cost 308
    covered = {(r, c) for rows, cols in blocks for r in rows for c in cols}
    assert covered == {(r, c) for r in range(22) for c in range(22)}


def test_one_extra_stop_only_buys_its_own_row_and_column():
    known, new = range(30), 30
    missing = {i: {new} for i in known}
    missing[new] = set(range(31))
    blocks = plan_blocks(missing)
    assert plan_cost(blocks) == 30 + 31  # not the 480 of a full 31x31 refetch


def test_a_patchy_cache_is_refilled_as_one_rectangle():
    """A request with a single origin is billed per cell, so once the gaps are big but
    irregular, re-buying known cells inside a square-blocked rectangle costs less."""
    missing = {i: {(i * 7 + k) % 40 for k in range(30)} for i in range(40)}
    blocks = plan_blocks(missing)
    assert plan_cost([([i], sorted(c)) for i, c in missing.items()]) == 1200  # gaps only
    assert plan_cost(blocks) == 610  # one 40x40 rectangle in square blocks
    covered = {(r, c) for rows, cols in blocks for r in rows for c in cols}
    assert all((r, c) in covered for r, cols in missing.items() for c in cols)


def test_a_few_scattered_gaps_are_fetched_as_gaps():
    missing = {i: {(i * 7) % 40} for i in range(40)}
    assert plan_cost(plan_blocks(missing)) == 40  # not the 610 of a full rectangle


def test_pairs_survive_a_regrouping_of_the_same_stops(tmp_path):
    """The credit saver: moving children between buses must not re-buy known pairs."""
    bodies: list[dict] = []
    points = line(6)
    TomTomClient("k", tmp_path, fetch=matrix_fetcher(bodies)).matrix(points, points)
    assert bodies, "first run has to fetch"

    after_first = len(bodies)
    client = TomTomClient("k", tmp_path, fetch=matrix_fetcher(bodies))
    client.matrix(points[:4], points[:4])
    client.matrix(points[2:], points[2:])
    assert len(bodies) == after_first
    assert client.usage.matrix_transactions == 0
    assert client.usage.matrix_cells_cached == 16 + 16


def test_coincident_stops_are_only_charged_once(tmp_path):
    bodies: list[dict] = []
    p = Point(50.0, 4.0)
    points = [p, p, p, Point(50.1, 4.1)]
    client = TomTomClient("k", tmp_path, fetch=matrix_fetcher(bodies))
    result = client.matrix(points, points)
    assert len(bodies) == 1
    assert (len(bodies[0]["origins"]), len(bodies[0]["destinations"])) == (2, 2)
    assert client.usage.matrix_transactions == 4
    assert result[0] == result[1] == result[2]


def test_legacy_request_cache_is_harvested_for_free(tmp_path):
    """A warm .cache/tomtom/matrix from before pair-level caching stays usable."""
    points = line(6)
    legacy = tmp_path / "matrix"
    legacy.mkdir(parents=True)
    body = _matrix_body(points, points)
    payload = matrix_fetcher([])("", body)
    (legacy / f"{_digest(body)}.json").write_text(json.dumps(payload))

    def refuse(url, body):
        raise AssertionError("must not call TomTom; the legacy cache covers this")

    client = TomTomClient("k", tmp_path, fetch=refuse)
    assert client.matrix(points, points)[0][5] == 50
    assert client.usage.matrix_transactions == 0
    assert client.usage.matrix_cells_cached == 36


def test_dry_run_counts_but_never_fetches(tmp_path):
    def refuse(url, body):
        raise AssertionError("dry run must not touch the network")

    client = TomTomClient("k", tmp_path, fetch=refuse, dry_run=True)
    points = line(22)
    client.matrix(points, points)
    route = client.route(points[:5], datetime(2026, 9, 15, 7, 20))
    assert client.usage.matrix_transactions == 220
    assert client.usage.route_requests == 1
    assert client.usage.transactions == 221
    assert len(route.legs) == 4
    assert list(tmp_path.rglob("*.json")) == []


def test_a_truncated_cache_entry_is_refetched_instead_of_crashing(tmp_path):
    calls: list[str] = []

    def fetch(url, body):
        calls.append(url)
        return ROUTE_PAYLOAD

    points = [Point(50.0, 4.0), Point(50.1, 4.1)]
    when = datetime(2026, 9, 15, 7, 20)
    TomTomClient("k", tmp_path, fetch=fetch).route(points, when)
    cached = next((tmp_path / "route").glob("*.json"))
    cached.write_text('{"routes": [')  # interrupted write

    client = TomTomClient("k", tmp_path, fetch=fetch)
    assert client.route(points, when).legs
    assert len(calls) == 2
    assert client.usage.route_requests == 1


def test_matrix_cell_error_is_reported(tmp_path):
    def fetch(url, body):
        return {
            "data": [
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "detailedError": {"code": "NO_ROUTE_FOUND", "message": "x"},
                }
            ]
        }

    client = TomTomClient("k", None, fetch=fetch)
    with pytest.raises(TomTomError, match="NO_ROUTE_FOUND"):
        client.matrix([Point(1, 1)], [Point(2, 2)])
