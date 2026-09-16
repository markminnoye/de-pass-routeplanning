"""Stdlib solver scoring: lexicographic (max ride, sum ride, total drive)."""

from __future__ import annotations

from busroutes.config import Settings
from busroutes.models import Bus, Point, Scenario, School, Stop

Score = tuple[int, int, int]  # (max_ride_s, sum_ride_s, total_drive_s)


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


def score_scenario(
    scenario: Scenario,
    buses: dict[str, Bus],
    school: School,
    travel,
    settings: Settings,
) -> Score:
    max_ride = 0
    sum_ride = 0
    total_drive = 0
    for plan in scenario.buses:
        bus_max, bus_sum, bus_drive = score_bus(
            plan.stops, buses[plan.bus_id].start, school.point, travel, settings
        )
        max_ride = max(max_ride, bus_max)
        sum_ride += bus_sum
        total_drive += bus_drive
    return (max_ride, sum_ride, total_drive)
