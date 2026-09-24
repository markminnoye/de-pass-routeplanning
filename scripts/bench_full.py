"""Order and assignment on one matrix, scored by evaluate --offline.

The sample pack has no cross-bus TomTom cells. scripts/bench_matrix.py fits one
line through the cells that do exist and both axes use that line. pyvroom and
OR-Tools see an open school route (`scenario.direction`, default to_school):
morning ends at the school, afternoon starts there. The tables in
docs/solver-benchmark.md are the closed-loop run of 23/09/2026. Solvers:

- stdlib: optimize --order / optimize --assign (passenger ride)
- pyvroom: minimise route duration, then the tightest max_travel_time that
  still visits every stop
- OR-Tools: time dimension, arc cost = travel + dwell, GlobalSpanCost

Google Route Optimization and the public VROOM demo are not called.

Run from the repo root:

    uv sync --group bench
    uv run python scripts/bench_full.py

Images land in docs/images/. The numeric dump is out/bench/full.json (gitignored).
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import json
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import bench_charts  # noqa: E402
import bench_matrix  # noqa: E402
import bench_solvers  # noqa: E402
import vroom  # noqa: E402
from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # noqa: E402

from busroutes.config import load_settings  # noqa: E402
from busroutes.evaluate import evaluate  # noqa: E402
from busroutes.models import Direction, Scenario, load_data_pack, load_scenario_file  # noqa: E402
from busroutes.optimize import optimize_assign, optimize_order  # noqa: E402
from busroutes.ordering import open_route_matrix  # noqa: E402

SCENARIOS = (
    "regiobus-per-zone",
    "opstapplaatsen",
    "spreiding-gemengd",
)
REFERENCE_DATE = date(2026, 9, 15)
VROOM_EXPLORATION = 5
ASSIGN_SPAN_COST = 100


def _stops(scenario: Scenario):
    return [stop for plan in scenario.buses for stop in plan.stops]


def _dense(client, points) -> list[list[int]]:
    return client.matrix(points, points)


def _check(scenario: Scenario, students: dict, buses: dict) -> None:
    seen: list[str] = []
    for plan in scenario.buses:
        count = sum(len(stop.students) for stop in plan.stops)
        capacity = buses[plan.bus_id].capacity
        if count > capacity:
            raise RuntimeError(f"{plan.bus_id}: {count} leerlingen > capacity {capacity}")
        seen.extend(plan.student_ids)
    if sorted(seen) != sorted(students):
        raise RuntimeError(f"{scenario.name}: niet elke leerling precies één keer")


def _require_open(scenario: Scenario) -> None:
    if scenario.pinned_stops or any(plan.pinned for plan in scenario.buses):
        raise RuntimeError(f"{scenario.name}: benchmark verwacht geen vastgezette bus of stop")


def _require_school_start(scenario, buses, school) -> None:
    school_key = bench_matrix.point_key(school.point)
    for plan in scenario.buses:
        if bench_matrix.point_key(buses[plan.bus_id].start) != school_key:
            raise RuntimeError(f"{plan.bus_id}: start is niet de school")


def _row(axis: str, solver: str, scenario_name: str, result, seconds: float, note: str) -> dict:
    payload = result.to_dict()
    summary = payload["summary"]
    counts = [bus["students"] for bus in payload["buses"]]
    if payload["settings"]["mode"] != "offline":
        raise RuntimeError("score moet via evaluate --offline (OfflineClient)")
    return {
        "axis": axis,
        "scenario": scenario_name,
        "solver": solver,
        "max_ride_min": summary["max_ride_min"],
        "avg_ride_min": summary["avg_ride_min"],
        "rides_over_60_min": summary["rides_over_60_min"],
        "total_km": summary["total_km"],
        "load_imbalance": bench_matrix.load_imbalance(counts),
        "students_per_bus": counts,
        "max_ride_per_bus": [bus["max_ride_min"] for bus in payload["buses"]],
        "seconds": round(seconds, 2),
        "note": note,
    }


def _score(axis, solver, optimized, scored, elapsed, note, students, buses) -> dict:
    _check(optimized, students, buses)
    return _row(axis, solver, optimized.name, scored, elapsed, note)


def _order_external(scenario, school, client, settings, solver: str) -> dict[str, list]:
    orders = {}
    for plan in scenario.buses:
        if len(plan.stops) <= 1:
            orders[plan.bus_id] = list(plan.stops)
            continue
        matrix = _dense(client, [school.point, *[stop.point for stop in plan.stops]])
        dwells = [bench_solvers._dwell_s(stop, settings) for stop in plan.stops]
        if solver == "pyvroom":
            indices = bench_solvers._vroom_tight_order(matrix, dwells, plan.direction)
        elif solver == "ortools":
            indices = bench_solvers._ortools_order(matrix, dwells, plan.direction)
        else:
            raise RuntimeError(solver)
        orders[plan.bus_id] = bench_solvers._orders_from_indices(plan, indices)
    return orders


def _apply_orders(scenario: Scenario, orders: dict, label: str) -> Scenario:
    plans = []
    for plan in scenario.buses:
        plans.append(replace(plan, stops=orders[plan.bus_id], ordering="given"))
    return replace(
        scenario,
        buses=plans,
        ordering="given",
        description=f"{scenario.description} · bench {label}",
    )


def _partition(routes: list[list[int]], n_stops: int, label: str) -> None:
    flat = [index for route in routes for index in route]
    if sorted(flat) != list(range(n_stops)):
        raise RuntimeError(f"{label}: geen partitie van {n_stops} stops ({len(flat)} indices)")


def _apply_routes(scenario: Scenario, routes: list[list[int]], label: str) -> Scenario:
    stops = _stops(scenario)
    _partition(routes, len(stops), label)
    plans = []
    for plan, route in zip(scenario.buses, routes, strict=True):
        plans.append(replace(plan, stops=[stops[i] for i in route], ordering="given"))
    return replace(
        scenario,
        buses=plans,
        ordering="given",
        description=f"{scenario.description} · bench {label}",
    )


def _vroom_once(
    matrix: list[list[int]],
    dwells: list[int],
    demands: list[int],
    capacities: list[int],
    max_travel_time: int | None,
    direction: Direction = "to_school",
) -> tuple[list[list[int]] | None, dict]:
    durations, start, end = open_route_matrix(matrix, direction)
    problem = vroom.Input()
    problem.set_durations_matrix("car", durations)
    for index, capacity in enumerate(capacities, start=1):
        problem.add_vehicle(
            vroom.Vehicle(
                index,
                start=start,
                end=end,
                capacity=[capacity],
                max_travel_time=max_travel_time,
            )
        )
    for index, (dwell, demand) in enumerate(zip(dwells, demands, strict=True), start=1):
        problem.add_job(vroom.Job(index, location=index, default_service=dwell, pickup=[demand]))
    solution = problem.solve(exploration_level=VROOM_EXPLORATION, nb_threads=1)
    payload = solution.to_dict()
    if payload["summary"]["unassigned"]:
        return None, payload
    by_vehicle = {vehicle: [] for vehicle in range(1, len(capacities) + 1)}
    for route in payload["routes"]:
        by_vehicle[route["vehicle"]] = [
            step["id"] - 1 for step in route["steps"] if step["type"] == "job"
        ]
    routes = [by_vehicle[vehicle] for vehicle in range(1, len(capacities) + 1)]
    return routes, payload


def _vroom_assign(
    matrix: list[list[int]],
    dwells: list[int],
    demands: list[int],
    capacities: list[int],
    direction: Direction = "to_school",
) -> list[list[int]]:
    """Tightest max_travel_time that still visits every stop; else the loose tour."""
    loose, payload = _vroom_once(matrix, dwells, demands, capacities, None, direction)
    if loose is None:
        raise RuntimeError("pyvroom laat stops onbezet zonder reistijdlimiet")
    durations = [int(route["duration"]) for route in payload["routes"]]
    hi = max(durations, default=1)
    capped, _payload = _vroom_once(matrix, dwells, demands, capacities, hi, direction)
    while capped is None:
        hi = max(hi + 1, hi * 2)
        if hi > 24 * 3600:
            return loose
        capped, _payload = _vroom_once(matrix, dwells, demands, capacities, hi, direction)
    best = capped
    lo = 0
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        routes, _payload = _vroom_once(matrix, dwells, demands, capacities, mid, direction)
        if routes is not None:
            best = routes
            hi = mid
        else:
            lo = mid
    return best


def _ortools_assign(
    matrix: list[list[int]],
    dwells: list[int],
    demands: list[int],
    capacities: list[int],
    seconds: float,
    direction: Direction = "to_school",
) -> list[list[int]]:
    durations, start, end = open_route_matrix(matrix, direction)
    dummy = len(matrix)
    n_vehicles = len(capacities)
    manager = pywrapcp.RoutingIndexManager(
        len(durations), n_vehicles, [start] * n_vehicles, [end] * n_vehicles
    )
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index: int, to_index: int) -> int:
        origin = manager.IndexToNode(from_index)
        dest = manager.IndexToNode(to_index)
        service = dwells[origin - 1] if 0 < origin < dummy else 0
        return int(durations[origin][dest]) + service

    def demand_at(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        if not 0 < node < dummy:
            return 0
        return demands[node - 1]

    transit_cb = routing.RegisterTransitCallback(transit)
    demand_cb = routing.RegisterUnaryTransitCallback(demand_at)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)
    routing.SetFixedCostOfAllVehicles(0)
    routing.AddDimension(transit_cb, 0, 10_000_000, True, "Time")
    routing.GetDimensionOrDie("Time").SetGlobalSpanCostCoefficient(ASSIGN_SPAN_COST)
    routing.AddDimensionWithVehicleCapacity(demand_cb, 0, capacities, True, "Capacity")
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromMilliseconds(int(seconds * 1000))
    params.log_search = False
    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise RuntimeError("OR-Tools vond geen toewijzing")
    routes: list[list[int]] = []
    for vehicle in range(n_vehicles):
        index = routing.Start(vehicle)
        route: list[int] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if 0 < node < dummy:
                route.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        routes.append(route)
    return routes


def _run_order(scenario, students, buses, school, client, travel, settings) -> list[dict]:
    _require_school_start(scenario, buses, school)
    rows = []
    print(f"  order stdlib {scenario.name}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    ordered = optimize_order(scenario, buses, school, travel, settings)
    elapsed = time.perf_counter() - started
    scored = evaluate(ordered, school, students, buses, client, settings)
    rows.append(_score("order", "stdlib", ordered, scored, elapsed, "", students, buses))

    for solver in ("pyvroom", "ortools"):
        print(f"  order {solver} {scenario.name}", file=sys.stderr, flush=True)
        started = time.perf_counter()
        optimized = _apply_orders(
            scenario, _order_external(scenario, school, client, settings, solver), solver
        )
        elapsed = time.perf_counter() - started
        scored = evaluate(optimized, school, students, buses, client, settings)
        note = ""
        if solver == "ortools":
            note = f"{bench_solvers.ORTOOLS_SECONDS_PER_BUS}s per bus"
        rows.append(_score("order", solver, optimized, scored, elapsed, note, students, buses))
    return rows


def _run_assign(
    scenario,
    students,
    buses,
    school,
    client,
    travel,
    settings,
    *,
    stdlib_seconds: float,
    stdlib_perturbations: int,
    ortools_seconds: float,
    seed: int,
    order_rows: list[dict],
) -> list[dict]:
    _require_open(scenario)
    _require_school_start(scenario, buses, school)
    rows = []
    baseline = next(
        row for row in order_rows if row["scenario"] == scenario.name and row["solver"] == "stdlib"
    )
    rows.append(
        {
            **baseline,
            "axis": "assign",
            "solver": "stdlib --order",
            "note": "baseline: zelfde run als --order, geen herverdeling",
        }
    )

    print(f"  assign stdlib {scenario.name}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    assigned = optimize_assign(
        scenario,
        buses,
        school,
        travel,
        settings,
        seed=seed,
        max_seconds=stdlib_seconds,
        max_perturbations=stdlib_perturbations,
    )
    elapsed = time.perf_counter() - started
    scored = evaluate(assigned.scenario, school, students, buses, client, settings)
    note = f"perturbaties={assigned.perturbations}, gestopt door {assigned.stopped_by}"
    rows.append(
        _score(
            "assign",
            "stdlib --assign",
            assigned.scenario,
            scored,
            elapsed,
            note,
            students,
            buses,
        )
    )

    stops = _stops(scenario)
    dwells = [bench_solvers._dwell_s(stop, settings) for stop in stops]
    demands = [len(stop.students) for stop in stops]
    capacities = [buses[plan.bus_id].capacity for plan in scenario.buses]
    if any(demand > max(capacities) for demand in demands):
        raise RuntimeError(f"{scenario.name}: een stop past op geen enkele bus")
    matrix = _dense(client, [school.point, *[stop.point for stop in stops]])

    print(f"  assign pyvroom {scenario.name}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    routes = _vroom_assign(matrix, dwells, demands, capacities, scenario.direction)
    optimized = _apply_routes(scenario, routes, "pyvroom")
    elapsed = time.perf_counter() - started
    scored = evaluate(optimized, school, students, buses, client, settings)
    rows.append(_score("assign", "pyvroom", optimized, scored, elapsed, "", students, buses))

    print(f"  assign ortools {scenario.name}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    routes = _ortools_assign(
        matrix, dwells, demands, capacities, ortools_seconds, scenario.direction
    )
    optimized = _apply_routes(scenario, routes, "ortools")
    elapsed = time.perf_counter() - started
    scored = evaluate(optimized, school, students, buses, client, settings)
    rows.append(
        _score(
            "assign",
            "ortools",
            optimized,
            scored,
            elapsed,
            f"{ortools_seconds:g}s zoektijd",
            students,
            buses,
        )
    )
    return rows


def _markdown(rows: list[dict]) -> str:
    header = (
        "| As | Scenario | Solver | max rit (min) | gem. rit (min) "
        "| ritten > 60 | km | onevenwicht | rekentijd (s) |"
    )
    sep = "|---|---|---|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for row in rows:
        lines.append(
            "| {axis} | {scenario} | {solver} | {max_ride_min} | {avg_ride_min} | "
            "{rides_over_60_min} | {total_km} | {load_imbalance} | {seconds} |".format(**row)
        )
    notes = [f"- {row['scenario']} / {row['solver']}: {row['note']}" for row in rows if row["note"]]
    body = "\n".join(lines)
    if notes:
        body += "\n\n" + "\n".join(notes)
    return body + "\n"


def _package_report() -> list[dict]:
    report = []
    for dist, module_name in (
        ("ortools", "ortools"),
        ("pyvroom", "vroom"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("matplotlib", "matplotlib"),
    ):
        module = sys.modules.get(module_name)
        if module is None:
            module = __import__(module_name)
        root = Path(module.__file__).resolve().parent
        size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        report.append(
            {
                "distribution": dist,
                "version": importlib_metadata.version(dist),
                "mib": round(size / (1024 * 1024), 1),
            }
        )
    return report


def _loc(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def _loc_report() -> dict[str, int]:
    files = {
        "busroutes/optimize.py": REPO / "busroutes" / "optimize.py",
        "scripts/bench_solvers.py": REPO / "scripts" / "bench_solvers.py",
        "scripts/bench_matrix.py": REPO / "scripts" / "bench_matrix.py",
        "scripts/bench_charts.py": REPO / "scripts" / "bench_charts.py",
        "scripts/bench_full.py": REPO / "scripts" / "bench_full.py",
    }
    return {name: _loc(path) for name, path in files.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Order + assign benchmark on one matrix.")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--stdlib-seconds", type=float, default=180)
    parser.add_argument("--stdlib-perturbations", type=int, default=200)
    parser.add_argument("--ortools-seconds", type=float, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--images", type=Path, default=REPO / "docs" / "images")
    parser.add_argument("--json", type=Path, default=REPO / "out" / "bench" / "full.json")
    args = parser.parse_args()
    names = [name.strip() for name in args.scenarios.split(",") if name.strip()]

    settings = load_settings(
        require_key=False,
        reference_date=REFERENCE_DATE,
        data_dir=REPO / "docs" / "samples",
    )
    pack = load_data_pack(settings.data_dir)
    model = bench_matrix.fit_travel_model(settings.data_dir / "matrix")
    client = bench_matrix.SpeedMatrixClient(model)
    scenarios = [
        load_scenario_file(
            settings.data_dir / "scenarios" / f"{name}.json",
            pack.students,
            pack.buses,
        )
        for name in names
    ]
    points = [pack.school.point]
    for scenario in scenarios:
        for plan in scenario.buses:
            points.append(pack.buses[plan.bus_id].start)
            points.extend(stop.point for stop in plan.stops)
    travel = bench_matrix.freeze_travel(client, points)

    rows: list[dict] = []
    for scenario in scenarios:
        print(f"scenario {scenario.name}", file=sys.stderr, flush=True)
        order_rows = _run_order(
            scenario, pack.students, pack.buses, pack.school, client, travel, settings
        )
        rows.extend(order_rows)
        rows.extend(
            _run_assign(
                scenario,
                pack.students,
                pack.buses,
                pack.school,
                client,
                travel,
                settings,
                stdlib_seconds=args.stdlib_seconds,
                stdlib_perturbations=args.stdlib_perturbations,
                ortools_seconds=args.ortools_seconds,
                seed=args.seed,
                order_rows=order_rows,
            )
        )

    subtitle = (
        f"zelfde matrix · {model.alpha_s:.0f} s + {model.beta_s_per_m * 1000:.0f} s/km"
        f" · R² {model.r2:.2f} · {REFERENCE_DATE.isoformat()}"
    )
    images = bench_charts.write_benchmark_charts(args.images, rows, names, subtitle)
    report = _markdown(rows)
    payload = {
        "reference_date": REFERENCE_DATE.isoformat(),
        "model": {
            "alpha_s": model.alpha_s,
            "beta_s_per_m": model.beta_s_per_m,
            "n_cells": model.n_cells,
            "r2": model.r2,
            "median_abs_pct": model.median_abs_pct,
            "median_speed_m_s": model.median_speed_m_s,
        },
        "parameters": {
            "scenarios": names,
            "seed": args.seed,
            "stdlib_seconds": args.stdlib_seconds,
            "stdlib_perturbations": args.stdlib_perturbations,
            "ortools_assign_seconds": args.ortools_seconds,
            "ortools_order_seconds_per_bus": bench_solvers.ORTOOLS_SECONDS_PER_BUS,
            "vroom_exploration": VROOM_EXPLORATION,
            "vroom_threads": 1,
            "assign_span_cost": ASSIGN_SPAN_COST,
        },
        "packages": _package_report(),
        "loc": _loc_report(),
        "images": [
            path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)
            for path in images
        ],
        "rows": rows,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2) + "\n")
    print(report, end="")
    print(f"json: {args.json}", file=sys.stderr)
    for path in images:
        print(f"figuur: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
