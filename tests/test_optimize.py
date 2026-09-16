"""Score function and order search for the stdlib solver, on the hand-matrix world."""

from datetime import date, datetime

import pytest

from busroutes.config import Settings
from busroutes.evaluate import evaluate, evaluate_bus
from busroutes.models import BusPlan, Point, Scenario, Stop, load_scenario
from busroutes.optimize import Score, optimize_order, order_stops_for_bus, score_bus, score_scenario
from busroutes.ordering import order_stops
from tests.conftest import HAND_POINTS, HandMatrixClient

SETTINGS = Settings(
    api_key="test",
    cache_dir=None,
    dwell_base_s=30,
    dwell_per_student_s=10,
    reference_date=date(2026, 9, 15),
)


def _travel(client: HandMatrixClient):
    def travel(a: Point, b: Point) -> int:
        return client.matrix([a], [b])[0][0]

    return travel


def _given(name: str, stop_ids: list[str], students, buses) -> Scenario:
    return load_scenario(
        {
            "name": name,
            "ordering": "given",
            "buses": [{"bus_id": "bus1", "stops": stop_ids}],
        },
        students,
        buses,
    )


def _two_buses(name: str, bus1: list[str], bus2: list[str], students, buses) -> Scenario:
    return load_scenario(
        {
            "name": name,
            "ordering": "given",
            "buses": [
                {"bus_id": "bus1", "stops": bus1},
                {"bus_id": "bus2", "stops": bus2},
            ],
        },
        students,
        buses,
    )


def _stop_ids(stops: list[Stop]) -> list[str]:
    return [s.id for s in stops]


def test_score_bus_empty_returns_zeros(hand_school, hand_buses, hand_client):
    bus = hand_buses["bus1"]
    assert score_bus([], bus.start, hand_school.point, _travel(hand_client), SETTINGS) == (0, 0, 0)


def test_score_bus_matches_evaluate_on_given_order(
    hand_school, hand_students, hand_buses, hand_client
):
    scenario = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    result = evaluate(scenario, hand_school, hand_students, hand_buses, hand_client, SETTINGS)
    bus = result.buses[0]
    rides = result.ride_times_s()
    scored = score_bus(
        scenario.buses[0].stops,
        hand_buses["bus1"].start,
        hand_school.point,
        _travel(hand_client),
        SETTINGS,
    )
    assert scored == (max(rides), sum(rides), bus.drive_s)


def test_score_bus_pickup_with_two_students_counts_sum_twice(hand_school, hand_buses, hand_client):
    stop = Stop(id="w", point=HAND_POINTS["W"], students=["p1", "p2"], name="W")
    plan = BusPlan(bus_id="bus1", stops=[stop], ordering="given")
    dummy = Scenario(name="two", description="", ordering="given", buses=[plan])
    arrival = SETTINGS.reference_arrival(hand_school.target_arrival)
    depart_at = SETTINGS.reference_departure(hand_school.target_arrival)
    bus_result = evaluate_bus(
        plan,
        hand_buses["bus1"],
        hand_school,
        dummy,
        hand_client,
        SETTINGS,
        arrival,
        depart_at,
    )
    ride = bus_result.stops[0].ride_s
    scored = score_bus(
        [stop],
        hand_buses["bus1"].start,
        hand_school.point,
        _travel(hand_client),
        SETTINGS,
    )
    assert scored[0] == ride
    assert scored[1] == 2 * ride
    assert scored[2] == bus_result.drive_s


def test_score_scenario_is_lexicographic_max_ride_first(
    hand_school, hand_students, hand_buses, hand_client
):
    w_first = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    z_first = _given("z-first", ["z", "y", "x", "w"], hand_students, hand_buses)
    travel = _travel(hand_client)
    score_w = score_scenario(w_first, hand_buses, hand_school, travel, SETTINGS)
    score_z = score_scenario(z_first, hand_buses, hand_school, travel, SETTINGS)
    # Z-first: lower max-ride, higher total drive. W-first is the opposite.
    assert score_z[0] < score_w[0]
    assert score_z[2] > score_w[2]
    assert score_z < score_w

    better_max: Score = (100, 9999, 9999)
    worse_max: Score = (200, 1, 1)
    assert better_max < worse_max


def test_hand_client_route_matches_matrix_and_missing_pair_raises(hand_client, hand_school):
    origin, dest = hand_school.point, HAND_POINTS["W"]
    via_matrix = hand_client.matrix([origin], [dest])[0][0]
    via_route = hand_client.route([origin, dest], datetime(2026, 9, 15, 7, 20)).legs[0]
    assert via_route.travel_time_s == via_matrix == 10
    with pytest.raises(KeyError):
        hand_client.matrix([Point(1.0, 2.0)], [origin])


Z_FIRST_MAX_RIDE_S = 250  # Z-Y-X-W with dwell 40 per stop (3 later dwells + 130 travel)


def test_order_stops_for_bus_empty_and_single_unchanged(hand_school, hand_buses, hand_client):
    travel = _travel(hand_client)
    start = hand_buses["bus1"].start
    school = hand_school.point
    assert order_stops_for_bus([], start, school, travel, SETTINGS) == []
    only = Stop(id="w", point=HAND_POINTS["W"], students=["w"], name="W")
    assert order_stops_for_bus([only], start, school, travel, SETTINGS) == [only]


def test_order_stops_for_bus_from_path_cost_winner_reaches_z_first(
    hand_school, hand_students, hand_buses, hand_client
):
    scenario = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    start_stops = scenario.buses[0].stops
    travel = _travel(hand_client)
    start = hand_buses["bus1"].start
    school = hand_school.point
    result = order_stops_for_bus(start_stops, start, school, travel, SETTINGS)
    start_score = score_bus(start_stops, start, school, travel, SETTINGS)
    result_score = score_bus(result, start, school, travel, SETTINGS)
    assert result_score < start_score
    assert result_score[0] == Z_FIRST_MAX_RIDE_S
    assert _stop_ids(result) == ["z", "y", "x", "w"]


def test_order_stops_for_bus_beats_path_cost_heuristic(
    hand_school, hand_students, hand_buses, hand_client
):
    scenario = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    start_stops = scenario.buses[0].stops
    travel = _travel(hand_client)
    start = hand_buses["bus1"].start
    school = hand_school.point
    points = [start, *[s.point for s in start_stops], school]
    matrix = hand_client.matrix(points, points)
    heuristic = order_stops(list(range(1, 5)), 0, 5, matrix)
    heuristic_stops = [start_stops[i - 1] for i in heuristic]
    solver_stops = order_stops_for_bus(start_stops, start, school, travel, SETTINGS)
    heuristic_score = score_bus(heuristic_stops, start, school, travel, SETTINGS)
    solver_score = score_bus(solver_stops, start, school, travel, SETTINGS)
    assert _stop_ids(heuristic_stops) == ["w", "x", "y", "z"]
    assert heuristic_score[0] > solver_score[0]
    assert solver_score[0] == Z_FIRST_MAX_RIDE_S


def test_optimize_order_reorders_each_bus_independently(
    hand_school, hand_students, hand_buses, hand_client
):
    scenario = _two_buses("split", ["w", "x"], ["y", "z"], hand_students, hand_buses)
    original = {plan.bus_id: {s.id for s in plan.stops} for plan in scenario.buses}
    result = optimize_order(scenario, hand_buses, hand_school, _travel(hand_client), SETTINGS)
    assert {s.id for s in result.buses[0].stops} == original["bus1"]
    assert {s.id for s in result.buses[1].stops} == original["bus2"]
    assert [s.id for s in result.buses[0].stops] == ["x", "w"]
    assert [s.id for s in result.buses[1].stops] == ["y", "z"]
    assert result.ordering == "given"
    assert all(plan.ordering == "given" for plan in result.buses)
    assert scenario.ordering == "given"
    assert [s.id for s in scenario.buses[0].stops] == ["w", "x"]
    assert [s.id for s in scenario.buses[1].stops] == ["y", "z"]


def test_optimize_order_is_idempotent(hand_school, hand_students, hand_buses, hand_client):
    scenario = _given("w-first", ["w", "x", "y", "z"], hand_students, hand_buses)
    travel = _travel(hand_client)
    first = optimize_order(scenario, hand_buses, hand_school, travel, SETTINGS)
    second = optimize_order(first, hand_buses, hand_school, travel, SETTINGS)
    assert [_stop_ids(p.stops) for p in first.buses] == [_stop_ids(p.stops) for p in second.buses]


def test_evaluate_auto_matrix_uses_ride_time_order(
    hand_school, hand_students, hand_buses, hand_client
):
    scenario = load_scenario(
        {
            "name": "auto-hand",
            "ordering": "auto",
            "buses": [{"bus_id": "bus1", "stops": ["w", "x", "y", "z"]}],
        },
        hand_students,
        hand_buses,
    )
    result = evaluate(scenario, hand_school, hand_students, hand_buses, hand_client, SETTINGS)
    assert SETTINGS.ordering == "matrix"
    assert [s.stop.id for s in result.buses[0].stops] == ["z", "y", "x", "w"]
    assert max(result.ride_times_s()) == Z_FIRST_MAX_RIDE_S
