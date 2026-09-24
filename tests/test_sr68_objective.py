"""SR-68: passenger ride time versus path-cost ordering. No default change.

The ticket stop ids are twelve Hoegaarden-centrum students in docs/samples.
A classic TSP on bus length is not what `optimize` minimizes.
"""

from datetime import date
from pathlib import Path

from busroutes.config import Settings
from busroutes.evaluate import evaluate
from busroutes.geo import haversine_m
from busroutes.models import BusPlan, Scenario, Stop, load_samples
from busroutes.offline import OfflineClient
from busroutes.optimize import order_stops_for_bus, score_bus
from busroutes.ordering import _nearest_neighbour, order_stops
from busroutes.travel import travel_from_matrix

ROOT = Path(__file__).resolve().parents[1]
TICKET = [
    "s014",
    "s013",
    "s008",
    "s003",
    "s010",
    "s001",
    "s006",
    "s004",
    "s002",
    "s009",
    "s007",
    "s005",
]
TIENEN = [f"s0{n}" for n in range(61, 71)]
SPEED_M_S = 40_000 / 3600

SETTINGS = Settings(
    api_key="",
    reference_date=date(2026, 9, 24),
    ordering="haversine",
    cache_dir=None,
)


def _stops(students, ids: list[str]) -> list[Stop]:
    return [Stop(id=sid, point=students[sid].point, students=[sid]) for sid in ids]


def _max_ride(school, students, buses, client, stops: list[Stop], ordering: str, strategy: str):
    plan = BusPlan(bus_id="bus3", stops=stops, ordering=ordering)
    scenario = Scenario(name="sr68", description="", ordering=ordering, buses=[plan])
    result = evaluate(
        scenario,
        school,
        students,
        buses,
        client,
        Settings(
            api_key="",
            reference_date=SETTINGS.reference_date,
            ordering=strategy,
            cache_dir=None,
        ),
    )
    summary = result.to_dict()["summary"]
    return summary["max_ride_min"], [s.stop.id for s in result.buses[0].stops]


def test_matrix_order_beats_ticket_and_haversine_on_sample_stops():
    school, students, buses = load_samples(ROOT / "docs" / "samples")
    for sid in TICKET:
        assert students[sid].zone == "hoegaarden-centrum"
    client = OfflineClient(ROOT / "docs" / "samples" / "matrix")
    stops = _stops(students, TICKET)

    ticket_max, ticket_order = _max_ride(
        school, students, buses, client, stops, "given", "haversine"
    )
    haversine_max, _ = _max_ride(school, students, buses, client, stops, "auto", "haversine")
    matrix_max, matrix_order = _max_ride(school, students, buses, client, stops, "auto", "matrix")

    assert ticket_order == TICKET
    assert ticket_max == 37.1
    assert haversine_max == 33.4
    assert matrix_max == 22.1
    assert matrix_max < haversine_max < ticket_max
    assert matrix_order[0] != ticket_order[0]


def test_path_cost_order_raises_max_ride_on_tienen_plus_near_school():
    """10 Tienen stops plus the two Hoegaarden points closest to school.

    `order_stops` shortens the bus and puts the near-school stops first.
    `order_stops_for_bus` on the same haversine seconds keeps the long ride shorter.
    """
    school, students, buses = load_samples(ROOT / "docs" / "samples")
    del buses
    ranked = sorted(
        (sid for sid, student in students.items() if student.zone == "hoegaarden-centrum"),
        key=lambda sid: haversine_m(students[sid].point, school.point),
    )
    near: list[str] = []
    seen: set[tuple[float, float]] = set()
    for sid in ranked:
        key = (students[sid].point.lat, students[sid].point.lon)
        if key in seen:
            continue
        seen.add(key)
        near.append(sid)
        if len(near) == 2:
            break
    assert near == ["s023", "s009"]

    ids = TIENEN + near
    stops = _stops(students, ids)
    points = [school.point, *[stop.point for stop in stops], school.point]
    seconds = [[round(haversine_m(a, b) / SPEED_M_S) for b in points] for a in points]
    travel = travel_from_matrix(points, seconds)

    stop_idx = list(range(1, len(points) - 1))
    nn_idx = _nearest_neighbour(stop_idx, 0, len(points) - 1, seconds)
    path_idx = order_stops(stop_idx, 0, len(points) - 1, seconds)
    nn = [stops[i - 1] for i in nn_idx]
    path = [stops[i - 1] for i in path_idx]
    passenger = order_stops_for_bus(stops, school.point, school.point, travel, SETTINGS)

    nn_score = score_bus(nn, school.point, school.point, travel, SETTINGS)
    path_score = score_bus(path, school.point, school.point, travel, SETTINGS)
    passenger_score = score_bus(passenger, school.point, school.point, travel, SETTINGS)

    assert [stop.id for stop in nn[-2:]] == ["s009", "s023"]
    assert [stop.id for stop in path[:2]] == ["s009", "s023"]
    assert passenger[0].id not in near
    assert passenger[-1].id in near
    assert nn_score == (1288, 8689, 1203)
    assert path_score == (1619, 11011, 1195)
    assert passenger_score == (1281, 8545, 1280)
    assert passenger_score[0] < nn_score[0] < path_score[0]
    assert path_score[2] < nn_score[2]
