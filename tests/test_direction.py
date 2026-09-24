"""SR-73: open school route, default to_school, mirrored from_school."""

import json
from pathlib import Path

import pytest

from busroutes.evaluate import evaluate
from busroutes.geo import haversine_m
from busroutes.models import ScenarioError, load_samples, load_scenario
from busroutes.optimize import order_stops_for_bus, score_bus
from busroutes.ordering import order_stops, path_cost
from busroutes.render import render_map_html, to_geojson
from busroutes.travel import travel_from_matrix
from tests.test_evaluate import SETTINGS, given_scenario
from tests.test_sr68_objective import SETTINGS as HAVERSINE_SETTINGS
from tests.test_sr68_objective import TIENEN, _stops

ROOT_SAMPLES = Path(__file__).resolve().parents[1] / "docs" / "samples"
SPEED_M_S = 40_000 / 3600


def _two_buses(direction: str | None = None) -> dict:
    payload: dict = {
        "name": "given",
        "ordering": "given",
        "buses": [
            {"bus_id": "bus1", "stops": ["s002", "s001"]},
            {"bus_id": "bus2", "stops": ["s004", "s003"]},
        ],
    }
    if direction is not None:
        payload["direction"] = direction
    return payload


def test_omitted_direction_defaults_to_school(students, buses):
    scenario = load_scenario(_two_buses(), students, buses)
    assert scenario.direction == "to_school"
    assert all(plan.direction == "to_school" for plan in scenario.buses)


def test_invalid_direction_is_rejected(students, buses):
    with pytest.raises(ScenarioError, match="direction"):
        load_scenario({**_two_buses(), "name": "bad", "direction": "sideways"}, students, buses)


def test_bus_direction_overrides_scenario(students, buses):
    scenario = load_scenario(
        {
            "name": "mix",
            "direction": "to_school",
            "buses": [
                {"bus_id": "bus1", "stops": ["s002", "s001"], "direction": "from_school"},
                {"bus_id": "bus2", "stops": ["s004", "s003"]},
            ],
        },
        students,
        buses,
    )
    assert scenario.buses[0].direction == "from_school"
    assert scenario.buses[1].direction == "to_school"


def test_given_order_is_not_reversed(school, students, buses, fake_client):
    morning = load_scenario(_two_buses("to_school"), students, buses)
    afternoon = load_scenario(_two_buses("from_school"), students, buses)
    morning_result = evaluate(morning, school, students, buses, fake_client, SETTINGS)
    afternoon_result = evaluate(afternoon, school, students, buses, fake_client, SETTINGS)
    assert [s.stop.id for s in morning_result.buses[0].stops] == ["s002", "s001"]
    assert [s.stop.id for s in afternoon_result.buses[0].stops] == ["s002", "s001"]
    assert fake_client.matrix_calls == []


def test_from_school_drops_near_children_first_and_matches_ride(school, students, buses):
    """On a symmetric haversine matrix the afternoon order is the morning reverse."""
    school_pack, students_pack, _buses = load_samples(ROOT_SAMPLES)
    del school, students, buses
    ranked = sorted(
        (sid for sid, student in students_pack.items() if student.zone == "hoegaarden-centrum"),
        key=lambda sid: haversine_m(students_pack[sid].point, school_pack.point),
    )
    near = []
    seen: set[tuple[float, float]] = set()
    for sid in ranked:
        key = (students_pack[sid].point.lat, students_pack[sid].point.lon)
        if key in seen:
            continue
        seen.add(key)
        near.append(sid)
        if len(near) == 2:
            break
    ids = TIENEN + near
    stops = _stops(students_pack, ids)
    points = [school_pack.point, *[stop.point for stop in stops], school_pack.point]
    seconds = [[round(haversine_m(a, b) / SPEED_M_S) for b in points] for a in points]
    travel = travel_from_matrix(points, seconds)
    stop_idx = list(range(1, len(points) - 1))
    morning_idx = order_stops(stop_idx, 0, len(points) - 1, seconds, "to_school")
    afternoon_idx = order_stops(stop_idx, 0, len(points) - 1, seconds, "from_school")
    assert afternoon_idx == list(reversed(morning_idx))
    morning_stops = [stops[i - 1] for i in morning_idx]
    afternoon_stops = [stops[i - 1] for i in afternoon_idx]
    morning = score_bus(
        morning_stops,
        school_pack.point,
        school_pack.point,
        travel,
        HAVERSINE_SETTINGS,
        "to_school",
    )
    afternoon = score_bus(
        afternoon_stops,
        school_pack.point,
        school_pack.point,
        travel,
        HAVERSINE_SETTINGS,
        "from_school",
    )
    assert morning[0] == afternoon[0]
    assert morning[1] == afternoon[1]
    assert morning[0] / 60 <= 21.7
    assert morning_stops[0].id not in near
    assert morning_stops[-1].id in near
    metres = [[round(haversine_m(a, b)) for b in points] for a in points]
    closed_m = path_cost([0, *morning_idx, len(points) - 1], metres)
    assert 13_000 <= closed_m <= 13_500
    open_s = morning[2]
    closed_s = path_cost([0, *morning_idx, len(points) - 1], seconds)
    assert open_s < closed_s


def test_ride_solver_from_school_is_the_morning_reverse(
    hand_school, hand_students, hand_buses, hand_client
):
    from tests.test_optimize import SETTINGS as OPT_SETTINGS
    from tests.test_optimize import _given, _travel

    scenario = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    travel = _travel(hand_client)
    start = hand_buses["bus1"].start
    morning = order_stops_for_bus(
        scenario.buses[0].stops, start, hand_school.point, travel, OPT_SETTINGS, "to_school"
    )
    afternoon = order_stops_for_bus(
        scenario.buses[0].stops, start, hand_school.point, travel, OPT_SETTINGS, "from_school"
    )
    assert [s.id for s in afternoon] == list(reversed([s.id for s in morning]))


def test_direction_is_visible_in_metrics_and_on_the_map(school, students, buses, fake_client):
    scenario = load_scenario(_two_buses("from_school"), students, buses)
    result = evaluate(scenario, school, students, buses, fake_client, SETTINGS)
    payload = result.to_dict()
    assert payload["settings"]["direction"] == "from_school"
    assert payload["buses"][0]["direction"] == "from_school"
    assert "Laatste uitstap" in render_map_html(result, to_geojson(result))
    route = next(f for f in to_geojson(result)["features"] if f["properties"]["kind"] == "route")
    assert route["properties"]["direction"] == "van school"
    assert route["geometry"]["coordinates"][0] == [school.point.lon, school.point.lat]
    html = render_map_html(result, to_geojson(result))
    assert "van school" in html
    assert "Richting" in html


def test_default_metrics_direction_and_no_extra_matrix_calls(school, students, buses, fake_client):
    result = evaluate(
        given_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    )
    payload = result.to_dict()
    assert payload["settings"]["direction"] == "to_school"
    assert payload["buses"][0]["direction"] == "to_school"
    assert fake_client.matrix_calls == []
    assert len(fake_client.route_calls) == 2
    html = render_map_html(result, to_geojson(result))
    assert "naar school" in html
    json.dumps(payload)
