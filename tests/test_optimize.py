"""Score function for the stdlib solver, on the hand-matrix world."""

from datetime import date, datetime

import pytest

from busroutes.config import Settings
from busroutes.evaluate import evaluate, evaluate_bus
from busroutes.models import BusPlan, Point, Scenario, Stop, load_scenario
from busroutes.optimize import Score, score_bus, score_scenario
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
