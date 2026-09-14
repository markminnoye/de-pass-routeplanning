from datetime import datetime

import pytest

from busroutes.models import Point
from busroutes.tomtom import TomTomClient, TomTomError, parse_route

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
