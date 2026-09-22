"""Scale and stop-criterion tests for optimize --assign. In-memory matrix."""

from __future__ import annotations

import time

from busroutes.models import Scenario
from busroutes.optimize import (
    _local_search,
    combine_scores,
    optimize_assign,
    optimize_order,
    score_bus,
    score_scenario,
)
from tests.scale import make_scale_world, mixed_scenario
from tests.test_optimize import SETTINGS, _record_perturbations, _travel


def _world_travel(world):
    _school, _students, _buses, client, _clusters = world
    return _travel(client)


def test_combine_scores_matches_score_scenario_on_hand_and_scale(
    hand_school, hand_students, hand_buses, hand_client
):
    from busroutes.models import load_scenario

    scenario = load_scenario(
        {
            "name": "hand",
            "ordering": "given",
            "buses": [
                {"bus_id": "bus1", "stops": ["w", "x"]},
                {"bus_id": "bus2", "stops": ["y", "z"]},
            ],
        },
        hand_students,
        hand_buses,
    )
    travel = _travel(hand_client)
    per_bus = [
        score_bus(plan.stops, hand_buses[plan.bus_id].start, hand_school.point, travel, SETTINGS)
        for plan in scenario.buses
    ]
    assert combine_scores(per_bus) == score_scenario(
        scenario, hand_buses, hand_school, travel, SETTINGS
    )

    world = make_scale_world(20, 3)
    school, _students, buses, _client, _clusters = world
    scaled = mixed_scenario(world)
    travel = _world_travel(world)
    per_bus = [
        score_bus(plan.stops, buses[plan.bus_id].start, school.point, travel, SETTINGS)
        for plan in scaled.buses
    ]
    assert combine_scores(per_bus) == score_scenario(scaled, buses, school, travel, SETTINGS)


def test_local_search_deadline_already_past_returns_valid_scenario():
    world = make_scale_world(60, 4)
    school, students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    started = time.monotonic()
    result = _local_search(
        scenario,
        buses,
        school,
        travel,
        SETTINGS,
        set(),
        deadline=time.monotonic(),
    )
    assert time.monotonic() - started < 0.5
    _assert_feasible(result, students, buses)


def test_optimize_assign_40x4_returns_within_3s():
    world = make_scale_world(40, 4)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    started = time.monotonic()
    optimize_assign(scenario, buses, school, travel, SETTINGS, seed=0, max_seconds=1)
    assert time.monotonic() - started < 3


def test_optimize_assign_140x7_improves_mixed_start_within_35s():
    world = make_scale_world(140, 7)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    before = score_scenario(scenario, buses, school, travel, SETTINGS)
    started = time.monotonic()
    result = optimize_assign(scenario, buses, school, travel, SETTINGS, seed=0, max_seconds=30)
    assert time.monotonic() - started < 35
    assert score_scenario(result, buses, school, travel, SETTINGS) < before


def test_optimize_assign_150x7_improves_mixed_start_within_5min():
    """Product bar is five minutes (`--max-seconds 300`). This run uses 60s so the
    suite stays short; finishing inside 60s is inside that bar."""
    world = make_scale_world(150, 7)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    before = score_scenario(scenario, buses, school, travel, SETTINGS)
    started = time.monotonic()
    result = optimize_assign(scenario, buses, school, travel, SETTINGS, seed=0, max_seconds=60)
    assert time.monotonic() - started < 90
    assert score_scenario(result, buses, school, travel, SETTINGS) < before


def test_optimize_order_140x7_under_1s_in_memory():
    world = make_scale_world(140, 7)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    started = time.perf_counter()
    optimize_order(scenario, buses, school, travel, SETTINGS)
    assert time.perf_counter() - started < 1


def test_optimize_assign_same_seed_and_perturbation_cap_is_byte_identical():
    from busroutes.models import scenario_to_dict

    world = make_scale_world(40, 4)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    travel = _world_travel(world)
    kwargs = dict(
        scenario=scenario,
        buses=buses,
        school=school,
        travel=travel,
        settings=SETTINGS,
        seed=0,
        max_seconds=1000,
        max_perturbations=50,
    )
    first = scenario_to_dict(optimize_assign(**kwargs))
    second = scenario_to_dict(optimize_assign(**kwargs))
    assert first == second


def test_optimize_assign_max_seconds_sets_stopped_by():
    world = make_scale_world(140, 7)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    result = optimize_assign(
        scenario,
        buses,
        school,
        _world_travel(world),
        SETTINGS,
        seed=0,
        max_seconds=0.001,
    )
    assert result.stopped_by == "max_seconds"


def test_optimize_assign_max_perturbations_limits_perturb_calls(monkeypatch):
    world = make_scale_world(40, 4)
    school, _students, buses, _client, _clusters = world
    scenario = mixed_scenario(world)
    trail = _record_perturbations(monkeypatch)
    result = optimize_assign(
        scenario,
        buses,
        school,
        _world_travel(world),
        SETTINGS,
        seed=0,
        max_seconds=1000,
        max_perturbations=5,
    )
    assert result.stopped_by == "max_perturbations"
    assert len(trail) == 5


def _assert_feasible(scenario: Scenario, students: dict, buses: dict) -> None:
    seen: list[str] = []
    for plan in scenario.buses:
        assert len(plan.student_ids) <= buses[plan.bus_id].capacity
        seen.extend(plan.student_ids)
    assert sorted(seen) == sorted(students)
