"""Compare stop-order solvers on the real per-bus TomTom cells, scored by evaluate --offline.

Assignment is out of scope here: docs/samples/matrix covers each reference bus
(school + that bus's stops) but not cross-bus pairs. The order-and-assign
comparison on one completed matrix is scripts/bench_full.py. Google Route
Optimization and the public VROOM demo are not called (no GCP project; the
demo uses OSRM, not this matrix).

Run from the repo root, with the bench group installed:

    uv sync --group bench
    BUSROUTES_REFERENCE_DATE=2026-09-15 uv run python scripts/bench_solvers.py
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date
from pathlib import Path

import vroom
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from busroutes.config import load_settings
from busroutes.evaluate import evaluate
from busroutes.models import (
    Bus,
    BusPlan,
    Direction,
    Scenario,
    School,
    Stop,
    load_samples,
    load_scenario_file,
)
from busroutes.offline import OfflineClient
from busroutes.optimize import optimize_order
from busroutes.ordering import open_route_matrix

REPO = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "regiobus-per-zone",
    "opstapplaatsen",
    "spreiding-gemengd",
)
REFERENCE_DATE = date(2026, 9, 15)
ORTOOLS_SECONDS_PER_BUS = 1


def _dwell_s(stop: Stop, settings) -> int:
    return settings.dwell_base_s + settings.dwell_per_student_s * len(stop.students)


def _matrix(client: OfflineClient, plan: BusPlan, bus: Bus, school: School) -> list[list[int]]:
    """Node 0 is the school (also every sample bus's start). Nodes 1..n are stops."""
    nodes = [school.point, *[stop.point for stop in plan.stops]]
    if (bus.start.lat, bus.start.lon) != (school.point.lat, school.point.lon):
        raise RuntimeError(f"{bus.id}: start is not the school; this bench assumes depot = school")
    return client.matrix(nodes, nodes)


def _vroom_order(
    matrix: list[list[int]],
    dwells: list[int],
    max_travel_time: int | None,
    direction: Direction = "to_school",
) -> list[int]:
    """Open route: to_school ends at the school, from_school starts there."""
    durations, start, end = open_route_matrix(matrix, direction)
    problem = vroom.Input()
    problem.set_durations_matrix("car", durations)
    problem.add_vehicle(vroom.Vehicle(1, start=start, end=end, max_travel_time=max_travel_time))
    for i, dwell in enumerate(dwells, start=1):
        problem.add_job(vroom.Job(i, location=i, default_service=dwell))
    solution = problem.solve(exploration_level=5, nb_threads=1)
    if solution.summary.unassigned:
        return []
    steps = solution.to_dict()["routes"][0]["steps"]
    return [step["id"] - 1 for step in steps if step["type"] == "job"]


def _vroom_tight_order(
    matrix: list[list[int]], dwells: list[int], direction: Direction = "to_school"
) -> list[int]:
    """Lowest max_travel_time that still visits every stop; falls back to unconstrained."""
    loose = _vroom_order(matrix, dwells, None, direction)
    if not loose:
        return loose
    # Duration of the loose tour is an upper bound. Search the smallest cap
    # that remains feasible. On one vehicle this usually keeps the same tour:
    # the cap cannot trade a longer route for a shorter passenger ride.
    hi = 1
    while not _vroom_order(matrix, dwells, hi, direction):
        hi *= 2
        if hi > 24 * 3600:
            return loose
    lo = 0
    best = loose
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        order = _vroom_order(matrix, dwells, mid, direction)
        if order:
            best = order
            hi = mid
        else:
            lo = mid
    return best


def _ortools_order(
    matrix: list[list[int]], dwells: list[int], direction: Direction = "to_school"
) -> list[int]:
    """Open route with the same end as evaluate: school for to_school, no return."""
    durations, start, end = open_route_matrix(matrix, direction)
    dummy = len(matrix)
    manager = pywrapcp.RoutingIndexManager(len(durations), 1, [start], [end])
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index: int, to_index: int) -> int:
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        service = dwells[i - 1] if 0 < i < dummy else 0
        return int(durations[i][j]) + service

    callback = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    routing.AddDimension(callback, 0, 100_000_000, True, "Time")
    routing.GetDimensionOrDie("Time").SetGlobalSpanCostCoefficient(100)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(ORTOOLS_SECONDS_PER_BUS)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return []
    order: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if 0 < node < dummy:
            order.append(node - 1)
        index = solution.Value(routing.NextVar(index))
    return order


def _apply(scenario: Scenario, orders: dict[str, list[Stop]], label: str) -> Scenario:
    plans = []
    for plan in scenario.buses:
        stops = orders.get(plan.bus_id, list(plan.stops))
        plans.append(replace(plan, stops=stops, ordering="given", pinned=plan.pinned))
    return replace(
        scenario,
        buses=plans,
        ordering="given",
        description=f"{scenario.description} · bench {label}",
    )


def _orders_from_indices(plan: BusPlan, indices: list[int]) -> list[Stop]:
    if sorted(indices) != list(range(len(plan.stops))):
        raise RuntimeError(f"{plan.bus_id}: solver gaf geen permutatie: {indices}")
    return [plan.stops[i] for i in indices]


def _external_orders(
    scenario, buses, school, client, settings, solver: str
) -> dict[str, list[Stop]]:
    orders: dict[str, list[Stop]] = {}
    for plan in scenario.buses:
        if plan.pinned or len(plan.stops) <= 1:
            orders[plan.bus_id] = list(plan.stops)
            continue
        matrix = _matrix(client, plan, buses[plan.bus_id], school)
        dwells = [_dwell_s(stop, settings) for stop in plan.stops]
        if solver == "pyvroom":
            indices = _vroom_tight_order(matrix, dwells, plan.direction)
        elif solver == "ortools":
            indices = _ortools_order(matrix, dwells, plan.direction)
        else:
            raise RuntimeError(solver)
        orders[plan.bus_id] = _orders_from_indices(plan, indices)
    return orders


def _summary_row(label: str, scenario_name: str, result, seconds: float) -> dict:
    summary = result.to_dict()["summary"]
    return {
        "scenario": scenario_name,
        "solver": label,
        "max_ride_min": summary["max_ride_min"],
        "avg_ride_min": summary["avg_ride_min"],
        "rides_over_60_min": summary["rides_over_60_min"],
        "total_km": summary["total_km"],
        "seconds": round(seconds, 2),
    }


def _stdlib_row(scenario, students, buses, school, client, settings) -> dict:
    matrices = {
        plan.bus_id: _matrix(client, plan, buses[plan.bus_id], school) for plan in scenario.buses
    }
    # optimize_order calls travel(point, point) with no bus id. One map over
    # every coordinate this scenario uses. Per-bus matrices agree on the school.
    index_matrix: dict[tuple[float, float], dict[tuple[float, float], int]] = {}
    for plan in scenario.buses:
        matrix = matrices[plan.bus_id]
        points = [school.point, *[stop.point for stop in plan.stops]]
        for i, origin in enumerate(points):
            row = index_matrix.setdefault((origin.lat, origin.lon), {})
            for j, dest in enumerate(points):
                row[(dest.lat, dest.lon)] = matrix[i][j]

    def travel(a, b) -> int:
        return index_matrix[(a.lat, a.lon)][(b.lat, b.lon)]

    started = time.perf_counter()
    optimized = optimize_order(scenario, buses, school, travel, settings)
    elapsed = time.perf_counter() - started
    scored = evaluate(optimized, school, students, buses, client, settings)
    return _summary_row("stdlib", scenario.name, scored, elapsed)


def _external_row(scenario, students, buses, school, client, settings, solver: str) -> dict:
    started = time.perf_counter()
    orders = _external_orders(scenario, buses, school, client, settings, solver)
    optimized = _apply(scenario, orders, solver)
    elapsed = time.perf_counter() - started
    scored = evaluate(optimized, school, students, buses, client, settings)
    return _summary_row(solver, scenario.name, scored, elapsed)


def _markdown(rows: list[dict]) -> str:
    header = (
        "| Scenario | Solver | max rit (min) | gem. rit (min) "
        "| ritten > 60 min | km | rekentijd (s) |"
    )
    sep = "|---|---|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for row in rows:
        lines.append(
            "| {scenario} | {solver} | {max_ride_min} | {avg_ride_min} | "
            "{rides_over_60_min} | {total_km} | {seconds} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    settings = load_settings(
        require_key=False,
        reference_date=REFERENCE_DATE,
        data_dir=REPO / "docs" / "samples",
    )
    school, students, buses = load_samples(settings.data_dir)
    client = OfflineClient(settings.data_dir / "matrix")
    rows: list[dict] = []
    for name in SCENARIOS:
        scenario = load_scenario_file(
            settings.data_dir / "scenarios" / f"{name}.json", students, buses
        )
        rows.append(_stdlib_row(scenario, students, buses, school, client, settings))
        rows.append(_external_row(scenario, students, buses, school, client, settings, "pyvroom"))
        rows.append(_external_row(scenario, students, buses, school, client, settings, "ortools"))
    report = _markdown(rows)
    out = REPO / "out" / "bench" / "order.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(report, end="")
    print(f"geschreven: {out}")


if __name__ == "__main__":
    main()
