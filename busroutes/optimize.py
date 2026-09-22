"""Stdlib solver: lexicographic ride-time score, per-bus order search, and assignment search."""

from __future__ import annotations

import random
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from busroutes.config import Settings
from busroutes.models import Bus, BusPlan, Point, Scenario, School, Stop

Score = tuple[int, int, int]  # (max_ride_s, sum_ride_s, total_drive_s)
StopReason = Literal["stall", "max_perturbations", "max_seconds", "none"]


def _dwell_s(stop: Stop, settings: Settings) -> int:
    return settings.dwell_base_s + settings.dwell_per_student_s * len(stop.students)


def score_bus(
    stops: list[Stop],
    start: Point,
    school: Point,
    travel,
    settings: Settings,
) -> Score:
    if not stops:
        return (0, 0, 0)
    points = [start, *[s.point for s in stops], school]
    legs = [travel(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total_drive = sum(legs)
    dwells = [_dwell_s(s, settings) for s in stops]
    rides: list[int] = []
    for k, stop in enumerate(stops):
        ride = sum(legs[k + 1 :]) + sum(dwells[k + 1 :])
        rides.extend([ride] * len(stop.students))
    if not rides:
        return (0, 0, total_drive)
    return (max(rides), sum(rides), total_drive)


def combine_scores(scores: Iterable[Score]) -> Score:
    """Lexicographic scenario score from per-bus scores: max, then sums."""
    max_ride = 0
    sum_ride = 0
    total_drive = 0
    for bus_max, bus_sum, bus_drive in scores:
        if bus_max > max_ride:
            max_ride = bus_max
        sum_ride += bus_sum
        total_drive += bus_drive
    return (max_ride, sum_ride, total_drive)


def score_scenario(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> Score:
    return combine_scores(
        score_bus(plan.stops, buses[plan.bus_id].start, school.point, travel, settings)
        for plan in scenario.buses
    )


def order_stops_for_bus(
    stops: list[Stop],
    start: Point,
    school: Point,
    travel,
    settings: Settings,
) -> list[Stop]:
    """Improve the given visiting order with 2-opt and or-opt on score_bus."""
    if len(stops) <= 1:
        return list(stops)
    best = list(stops)
    best_score = score_bus(best, start, school, travel, settings)
    improved = True
    while improved:
        improved = False
        n = len(best)
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                cand_score = score_bus(candidate, start, school, travel, settings)
                if cand_score < best_score:
                    best = candidate
                    best_score = cand_score
                    improved = True
        for length in (1, 2, 3):
            for i in range(n - length + 1):
                segment = best[i : i + length]
                remaining = best[:i] + best[i + length :]
                for pos in range(len(remaining) + 1):
                    if pos == i:
                        continue
                    candidate = remaining[:pos] + segment + remaining[pos:]
                    cand_score = score_bus(candidate, start, school, travel, settings)
                    if cand_score < best_score:
                        best = candidate
                        best_score = cand_score
                        improved = True
    return best


def optimize_order(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> Scenario:
    """Reorder stops on each unpinned bus; assignment is unchanged. Result is ordering=given."""
    plans = [_apply_order(plan, buses, school, travel, settings) for plan in scenario.buses]
    return _with_plans(scenario, plans)


def _student_count(stops: list[Stop]) -> int:
    return sum(len(stop.students) for stop in stops)


def _clone_plans(plans: list[BusPlan]) -> list[BusPlan]:
    return [_frozen(plan) for plan in plans]


def _frozen(plan: BusPlan) -> BusPlan:
    """Copy with the stop list materialised as 'given'.

    A pinned bus is left untouched, ordering included: if it was 'auto' it stays
    'auto', so evaluate keeps ordering it the same way before and after.
    """
    if plan.pinned:
        return replace(plan, stops=list(plan.stops))
    return replace(plan, stops=list(plan.stops), ordering="given")


def _with_plans(scenario: Scenario, plans: list[BusPlan]) -> Scenario:
    return replace(scenario, buses=plans, ordering="given")


def _apply_order(
    plan: BusPlan,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> BusPlan:
    if plan.pinned:
        return _frozen(plan)
    ordered = order_stops_for_bus(
        plan.stops, buses[plan.bus_id].start, school.point, travel, settings
    )
    return replace(plan, stops=ordered, ordering="given")


def _best_insert(
    stop: Stop,
    dest: list[Stop],
    start: Point,
    school: Point,
    travel,
    settings: Settings,
) -> list[Stop]:
    best: list[Stop] | None = None
    best_score: Score | None = None
    for pos in range(len(dest) + 1):
        candidate = dest[:pos] + [stop] + dest[pos:]
        scored = score_bus(candidate, start, school, travel, settings)
        if best_score is None or scored < best_score:
            best = candidate
            best_score = scored
    assert best is not None
    return best


def _past(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() > deadline


def _plan_score(
    plan: BusPlan,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> Score:
    return score_bus(plan.stops, buses[plan.bus_id].start, school.point, travel, settings)


def _score_plans(
    plans: list[BusPlan],
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> list[Score]:
    return [_plan_score(plan, buses, school, travel, settings) for plan in plans]


def _with_replaced(scores: list[Score], replacements: dict[int, Score]) -> Score:
    merged = [replacements.get(i, score) for i, score in enumerate(scores)]
    return combine_scores(merged)


def _commit_move(
    scenario: Scenario,
    plans: list[BusPlan],
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    scores: list[Score],
    touched: tuple[int, ...],
) -> Scenario:
    new_plans = list(plans)
    for index in touched:
        new_plans[index] = _apply_order(new_plans[index], buses, school, travel, settings)
        scores[index] = _plan_score(new_plans[index], buses, school, travel, settings)
    return _with_plans(scenario, new_plans)


def _first_improving_relocate(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    pinned_stops: set[str],
    deadline: float | None,
    scores: list[Score],
) -> Scenario | None:
    plans = scenario.buses
    current_score = combine_scores(scores)
    for src_i, src in enumerate(plans):
        if src.pinned:
            continue
        src_start = buses[src.bus_id].start
        for stop_i, stop in enumerate(src.stops):
            if _past(deadline):
                return None
            if stop.id in pinned_stops:
                continue
            src_stops = src.stops[:stop_i] + src.stops[stop_i + 1 :]
            src_score = score_bus(src_stops, src_start, school.point, travel, settings)
            for dst_i, dst in enumerate(plans):
                if dst_i == src_i or dst.pinned:
                    continue
                if _student_count(dst.stops) + len(stop.students) > buses[dst.bus_id].capacity:
                    continue
                inserted = _best_insert(
                    stop,
                    dst.stops,
                    buses[dst.bus_id].start,
                    school.point,
                    travel,
                    settings,
                )
                dst_score = score_bus(
                    inserted, buses[dst.bus_id].start, school.point, travel, settings
                )
                estimate = _with_replaced(scores, {src_i: src_score, dst_i: dst_score})
                if estimate < current_score:
                    new_plans = list(plans)
                    new_plans[src_i] = replace(src, stops=src_stops, ordering="given")
                    new_plans[dst_i] = replace(dst, stops=inserted, ordering="given")
                    return _commit_move(
                        scenario,
                        new_plans,
                        buses,
                        school,
                        travel,
                        settings,
                        scores,
                        (src_i, dst_i),
                    )
    return None


def _first_improving_swap(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    pinned_stops: set[str],
    deadline: float | None,
    scores: list[Score],
) -> Scenario | None:
    plans = scenario.buses
    current_score = combine_scores(scores)
    for i, plan_i in enumerate(plans):
        if plan_i.pinned:
            continue
        start_i = buses[plan_i.bus_id].start
        for a, stop_a in enumerate(plan_i.stops):
            if _past(deadline):
                return None
            if stop_a.id in pinned_stops:
                continue
            for j in range(i + 1, len(plans)):
                plan_j = plans[j]
                if plan_j.pinned:
                    continue
                start_j = buses[plan_j.bus_id].start
                for b, stop_b in enumerate(plan_j.stops):
                    if stop_b.id in pinned_stops:
                        continue
                    cap_i = (
                        _student_count(plan_i.stops) - len(stop_a.students) + len(stop_b.students)
                    )
                    cap_j = (
                        _student_count(plan_j.stops) - len(stop_b.students) + len(stop_a.students)
                    )
                    if cap_i > buses[plan_i.bus_id].capacity:
                        continue
                    if cap_j > buses[plan_j.bus_id].capacity:
                        continue
                    rest_i = plan_i.stops[:a] + plan_i.stops[a + 1 :]
                    rest_j = plan_j.stops[:b] + plan_j.stops[b + 1 :]
                    inserted_i = _best_insert(
                        stop_b, rest_i, start_i, school.point, travel, settings
                    )
                    inserted_j = _best_insert(
                        stop_a, rest_j, start_j, school.point, travel, settings
                    )
                    score_i = score_bus(inserted_i, start_i, school.point, travel, settings)
                    score_j = score_bus(inserted_j, start_j, school.point, travel, settings)
                    estimate = _with_replaced(scores, {i: score_i, j: score_j})
                    if estimate < current_score:
                        new_plans = list(plans)
                        new_plans[i] = replace(plan_i, stops=inserted_i, ordering="given")
                        new_plans[j] = replace(plan_j, stops=inserted_j, ordering="given")
                        return _commit_move(
                            scenario,
                            new_plans,
                            buses,
                            school,
                            travel,
                            settings,
                            scores,
                            (i, j),
                        )
    return None


def _local_search(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    pinned_stops: set[str],
    deadline: float | None = None,
    scores: list[Score] | None = None,
) -> Scenario:
    if _past(deadline):
        return scenario
    if scores is None:
        scores = _score_plans(scenario.buses, buses, school, travel, settings)
    current = scenario
    while True:
        if _past(deadline):
            return current
        neighbor = _first_improving_relocate(
            current, buses, school, travel, settings, pinned_stops, deadline, scores
        )
        if neighbor is None and not _past(deadline):
            neighbor = _first_improving_swap(
                current, buses, school, travel, settings, pinned_stops, deadline, scores
            )
        if neighbor is None:
            return current
        current = neighbor


def _plan_index(plans: list[BusPlan], stop_id: str) -> int:
    for i, plan in enumerate(plans):
        if any(stop.id == stop_id for stop in plan.stops):
            return i
    raise KeyError(stop_id)


def _perturb(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    pinned_stops: set[str],
    rng: random.Random,
    scores: list[Score] | None = None,
) -> Scenario:
    plans = _clone_plans(scenario.buses)
    movable = [
        stop
        for plan in plans
        if not plan.pinned
        for stop in plan.stops
        if stop.id not in pinned_stops
    ]
    k = min(3, len(movable))
    if k == 0:
        return _with_plans(scenario, plans)
    affected: set[int] = set()
    for stop in rng.sample(movable, k):
        src_i = _plan_index(plans, stop.id)
        dests = [
            j
            for j, plan in enumerate(plans)
            if j != src_i
            and not plan.pinned
            and _student_count(plan.stops) + len(stop.students) <= buses[plan.bus_id].capacity
        ]
        if not dests:
            continue
        dst_i = rng.choice(dests)
        plans[src_i] = replace(
            plans[src_i],
            stops=[s for s in plans[src_i].stops if s.id != stop.id],
            ordering="given",
        )
        plans[dst_i] = replace(
            plans[dst_i], stops=list(plans[dst_i].stops) + [stop], ordering="given"
        )
        affected.update((src_i, dst_i))
    for i in sorted(affected):
        plans[i] = _apply_order(plans[i], buses, school, travel, settings)
        if scores is not None:
            scores[i] = _plan_score(plans[i], buses, school, travel, settings)
    return _with_plans(scenario, plans)


@dataclass(frozen=True)
class OptimizeResult:
    """Assignment search outcome. Attribute access forwards to the scenario."""

    scenario: Scenario
    perturbations: int
    stopped_by: StopReason

    def __getattr__(self, name: str):
        return getattr(self.scenario, name)


def optimize_assign(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
    *,
    seed: int = 0,
    max_seconds: float = 30.0,
    max_perturbations: int = 1000,
) -> OptimizeResult:
    """Reassign unpinned stops across unpinned buses, then reorder with order_stops_for_bus.

    The search starts from niveau A of the input (every unpinned bus reordered), which
    is exactly what evaluate reports for an ordering=auto scenario, so the result is
    never worse than the 'vóór' figure the CLI prints.

    Candidates are scored by best insertion. Niveau A runs only after a move is accepted.
    The perturbation loop stops at 200 stalls or max_perturbations (reproducible).
    max_seconds is an emergency brake: when it trips, stopped_by is "max_seconds".
    max_seconds <= 0 runs the initial search only and does not enter the loop.
    """
    pinned_stops = set(scenario.pinned_stops)
    rng = random.Random(seed)
    started = time.monotonic()
    deadline = None if max_seconds <= 0 else started + max_seconds
    current = optimize_order(scenario, buses, school, travel, settings)
    scores = _score_plans(current.buses, buses, school, travel, settings)
    current = _local_search(
        current, buses, school, travel, settings, pinned_stops, deadline, scores
    )
    if max_seconds <= 0:
        return OptimizeResult(current, 0, "none")
    if _past(deadline):
        return OptimizeResult(current, 0, "max_seconds")
    best = current
    best_score = combine_scores(scores)
    stall = 0
    perturbations = 0
    stopped_by: StopReason = "stall"
    while stall < 200 and perturbations < max_perturbations:
        if _past(deadline):
            stopped_by = "max_seconds"
            break
        perturbations += 1
        saved = list(scores)
        perturbed = _perturb(best, buses, school, travel, settings, pinned_stops, rng, scores)
        perturbed = _local_search(
            perturbed, buses, school, travel, settings, pinned_stops, deadline, scores
        )
        scored = combine_scores(scores)
        if scored < best_score:
            best = perturbed
            best_score = scored
            stall = 0
        else:
            stall += 1
            scores[:] = saved
        if _past(deadline):
            stopped_by = "max_seconds"
            break
    else:
        stopped_by = "max_perturbations" if perturbations >= max_perturbations else "stall"
    return OptimizeResult(best, perturbations, stopped_by)
