"""Evaluate a scenario: order stops (optionally), fetch routes, schedule backwards
from the target arrival and compute the metrics from the project brief."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median

from busroutes.config import Settings
from busroutes.geo import haversine_m
from busroutes.models import Bus, BusPlan, Point, Scenario, School, Stop, Student
from busroutes.offline import OfflineClient
from busroutes.ordering import Matrix, OrderingStrategy, order_stops
from busroutes.tomtom import GeoClient, RouteResult


@dataclass
class StopResult:
    stop: Stop
    arrival: datetime  # bus arrives at the stop
    departure: datetime  # bus leaves the stop (after dwell)
    ride_s: int  # from departure until arrival at school, for every rider at this stop


@dataclass
class BusResult:
    bus: Bus
    route: RouteResult
    stops: list[StopResult]
    departure: datetime
    arrival: datetime

    @property
    def drive_s(self) -> int:
        return self.route.travel_time_s

    @property
    def length_m(self) -> int:
        return self.route.length_m

    @property
    def student_count(self) -> int:
        return sum(len(s.stop.students) for s in self.stops)

    @property
    def occupancy(self) -> float:
        return self.student_count / self.bus.capacity if self.bus.capacity else 0.0


@dataclass
class ScenarioResult:
    scenario: Scenario
    school: School
    settings: Settings
    depart_at_reference: datetime
    students: dict[str, Student]
    buses: list[BusResult] = field(default_factory=list)
    unused_buses: list[str] = field(default_factory=list)
    mode: str = "tomtom"

    def ride_times_s(self) -> list[int]:
        return [s.ride_s for b in self.buses for s in b.stops for _ in s.stop.students]

    def to_stop_km(self, student_id: str, stop: Stop) -> float:
        """Straight-line distance from the student's home to the stop (0 for a home stop)."""
        return round(haversine_m(self.students[student_id].point, stop.point) / 1000, 2)

    def to_dict(self) -> dict:
        rides = self.ride_times_s()
        used = [b for b in self.buses if b.stops]
        to_stop = [
            self.to_stop_km(sid, s.stop)
            for b in self.buses
            for s in b.stops
            for sid in s.stop.students
        ]
        settings_d: dict = {
            "traffic": self.settings.traffic,
            "ordering_strategy": self.settings.ordering,
            "depart_at_reference": self.depart_at_reference.isoformat(timespec="minutes"),
            "target_arrival": _hhmm(self.school.target_arrival),
            "dwell_base_s": self.settings.dwell_base_s,
            "dwell_per_student_s": self.settings.dwell_per_student_s,
            "mode": self.mode,
        }
        if self.mode == "offline":
            settings_d["km_estimated"] = True
        return {
            "scenario": self.scenario.name,
            "description": self.scenario.description,
            "ordering": self.scenario.ordering,
            "settings": settings_d,
            "summary": {
                "students": len(rides),
                "buses_used": len(used),
                "buses_unused": list(self.unused_buses),
                "max_ride_min": _minutes(max(rides)) if rides else 0.0,
                "avg_ride_min": _minutes(mean(rides)) if rides else 0.0,
                "median_ride_min": _minutes(median(rides)) if rides else 0.0,
                "rides_over_60_min": sum(r > 60 * 60 for r in rides),
                "rides_over_90_min": sum(r > 90 * 60 for r in rides),
                "max_to_stop_km": max(to_stop, default=0.0),
                "students_with_to_stop_over_1km": sum(d > 1.0 for d in to_stop),
                "total_drive_min": _minutes(sum(b.drive_s for b in used)),
                "total_km": round(sum(b.length_m for b in used) / 1000, 1),
                "avg_occupancy_pct": round(100 * mean(b.occupancy for b in used), 1)
                if used
                else 0.0,
                "earliest_departure": _hhmm(min(b.departure for b in used)) if used else None,
                "arrival": _hhmm(self.school.target_arrival),
            },
            "buses": [
                {
                    "bus_id": b.bus.id,
                    "students": b.student_count,
                    "capacity": b.bus.capacity,
                    "occupancy_pct": round(100 * b.occupancy, 1),
                    "departure": _hhmm(b.departure),
                    "arrival": _hhmm(b.arrival),
                    "drive_min": _minutes(b.drive_s),
                    "km": round(b.length_m / 1000, 1),
                    "max_ride_min": _minutes(max((s.ride_s for s in b.stops), default=0)),
                    "stops": [
                        {
                            "id": s.stop.id,
                            "name": s.stop.name,
                            "lat": s.stop.point.lat,
                            "lon": s.stop.point.lon,
                            "students": list(s.stop.students),
                            "arrival": _hhmm(s.arrival),
                            "departure": _hhmm(s.departure),
                            "ride_min": _minutes(s.ride_s),
                        }
                        for s in b.stops
                    ],
                }
                for b in self.buses
            ],
            "students": [
                {
                    "id": sid,
                    "bus_id": b.bus.id,
                    "stop_id": s.stop.id,
                    "pickup": _hhmm(s.arrival),
                    "ride_min": _minutes(s.ride_s),
                    "to_stop_km": self.to_stop_km(sid, s.stop),
                }
                for b in self.buses
                for s in b.stops
                for sid in s.stop.students
            ],
        }


def _minutes(seconds: float) -> float:
    return round(seconds / 60, 1)


def _hhmm(t) -> str:
    return t.strftime("%H:%M")


def _dwell(stop: Stop, settings: Settings) -> timedelta:
    return timedelta(
        seconds=settings.dwell_base_s + settings.dwell_per_student_s * len(stop.students)
    )


def _cost_matrix(points: list[Point], client: GeoClient, strategy: OrderingStrategy) -> Matrix:
    """Cost between every pair of points, only ever used to pick a visiting order.

    "haversine" is straight-line metres and free; "matrix" buys TomTom travel times,
    which is by far the most expensive call the evaluator makes.
    """
    if strategy == "matrix":
        return client.matrix(points, points)
    return [[round(haversine_m(a, b)) for b in points] for a in points]


def _ordered_stops(
    plan: BusPlan, bus: Bus, school: School, client: GeoClient, strategy: OrderingStrategy
) -> list[Stop]:
    if plan.ordering == "given" or len(plan.stops) <= 1:
        return list(plan.stops)
    points = [bus.start, *[s.point for s in plan.stops], school.point]
    matrix = _cost_matrix(points, client, strategy)
    start, end = 0, len(points) - 1
    order = order_stops(list(range(1, end)), start, end, matrix)
    return [plan.stops[i - 1] for i in order]


def evaluate_bus(
    plan: BusPlan,
    bus: Bus,
    school: School,
    scenario: Scenario,
    client: GeoClient,
    settings: Settings,
    arrival: datetime,
    depart_at: datetime,
) -> BusResult:
    stops = _ordered_stops(plan, bus, school, client, settings.ordering)
    if not stops:
        return BusResult(
            bus=bus, route=RouteResult(legs=[]), stops=[], departure=arrival, arrival=arrival
        )
    points = [bus.start, *[s.point for s in stops], school.point]
    route = client.route(points, depart_at)
    if len(route.legs) != len(points) - 1:
        raise RuntimeError(
            f"{bus.id}: {len(route.legs)} legs voor {len(points)} punten "
            f"(verwacht {len(points) - 1})"
        )

    # walk backwards from the school: leg k connects points[k] -> points[k+1]
    results: list[StopResult] = []
    t = arrival
    for k in range(len(stops) - 1, -1, -1):
        leg_after = route.legs[k + 1]
        departure = t - timedelta(seconds=leg_after.travel_time_s)
        stop_arrival = departure - _dwell(stops[k], settings)
        results.append(
            StopResult(
                stop=stops[k],
                arrival=stop_arrival,
                departure=departure,
                ride_s=int((arrival - departure).total_seconds()),
            )
        )
        t = stop_arrival
    results.reverse()
    bus_departure = results[0].arrival - timedelta(seconds=route.legs[0].travel_time_s)
    return BusResult(bus=bus, route=route, stops=results, departure=bus_departure, arrival=arrival)


def evaluate(
    scenario: Scenario,
    school: School,
    students: dict[str, Student],
    buses: dict[str, Bus],
    client: GeoClient,
    settings: Settings,
) -> ScenarioResult:
    arrival = settings.reference_arrival(school.target_arrival)
    depart_at = settings.reference_departure(school.target_arrival)
    result = ScenarioResult(
        scenario=scenario,
        school=school,
        settings=settings,
        depart_at_reference=depart_at,
        students=students,
        mode="offline" if isinstance(client, OfflineClient) else "tomtom",
    )
    for plan in scenario.buses:
        result.buses.append(
            evaluate_bus(
                plan, buses[plan.bus_id], school, scenario, client, settings, arrival, depart_at
            )
        )
    used = {plan.bus_id for plan in scenario.buses}
    result.unused_buses = sorted(b for b in buses if b not in used)
    return result
