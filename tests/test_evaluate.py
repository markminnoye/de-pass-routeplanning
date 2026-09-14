from datetime import date, datetime

from busroutes.config import BRUSSELS, Settings
from busroutes.evaluate import evaluate
from busroutes.models import load_scenario
from tests.conftest import haversine_m

SETTINGS = Settings(
    api_key="test",
    cache_dir=None,
    dwell_base_s=30,
    dwell_per_student_s=10,
    reference_date=date(2026, 9, 15),  # a Tuesday
)


def given_scenario(students, buses):
    return load_scenario(
        {
            "name": "given",
            "ordering": "given",
            "buses": [
                {"bus_id": "bus1", "stops": ["s002", "s001"]},
                {"bus_id": "bus2", "stops": ["s004", "s003"]},
            ],
        },
        students,
        buses,
    )


def test_schedule_is_backwards_from_target_arrival(school, students, buses, fake_client):
    result = evaluate(given_scenario(students, buses), school, buses, fake_client, SETTINGS)
    bus1 = result.buses[0]
    arrival = datetime(2026, 9, 15, 8, 20, tzinfo=BRUSSELS)
    assert bus1.arrival == arrival

    leg_last = round(haversine_m(students["s001"].point, school.point) / 10)
    leg_mid = round(haversine_m(students["s002"].point, students["s001"].point) / 10)
    leg_first = round(haversine_m(school.point, students["s002"].point) / 10)
    dwell = 30 + 10

    last_stop = bus1.stops[-1]
    assert (arrival - last_stop.departure).total_seconds() == leg_last
    assert (last_stop.departure - last_stop.arrival).total_seconds() == dwell
    first_stop = bus1.stops[0]
    assert (last_stop.arrival - first_stop.departure).total_seconds() == leg_mid
    assert (first_stop.arrival - bus1.departure).total_seconds() == leg_first

    # ride time = from leaving the stop until arriving at school
    assert last_stop.ride_s == leg_last
    assert first_stop.ride_s == leg_mid + dwell + leg_last
    assert bus1.drive_s == leg_first + leg_mid + leg_last
    assert bus1.length_m == sum(leg.length_m for leg in bus1.route.legs)
    assert bus1.occupancy == 1.0


def test_summary_metrics(school, students, buses, fake_client):
    result = evaluate(given_scenario(students, buses), school, buses, fake_client, SETTINGS)
    rides = sorted(result.ride_times_s())
    assert len(rides) == 4
    d = result.to_dict()
    assert d["summary"]["students"] == 4
    assert d["summary"]["max_ride_min"] == round(rides[-1] / 60, 1)
    assert d["summary"]["avg_ride_min"] == round(sum(rides) / 4 / 60, 1)
    assert d["summary"]["total_km"] == round(sum(b.length_m for b in result.buses) / 1000, 1)
    assert {s["id"] for s in d["students"]} == set(students)
    assert d["buses"][0]["stops"][0]["arrival"].count(":") == 1  # HH:MM


def test_given_ordering_does_not_touch_matrix(school, students, buses, fake_client):
    evaluate(given_scenario(students, buses), school, buses, fake_client, SETTINGS)
    assert fake_client.matrix_calls == []
    assert len(fake_client.route_calls) == 2


def test_auto_ordering_uses_matrix_and_visits_far_stop_first(school, students, buses, fake_client):
    scenario = load_scenario(
        {
            "name": "auto",
            "ordering": "auto",
            "buses": [
                {"bus_id": "bus1", "stops": ["s001", "s002"]},  # s002 is farther out
                {"bus_id": "bus2", "stops": ["s003", "s004"]},  # s004 is farther out
            ],
        },
        students,
        buses,
    )
    result = evaluate(scenario, school, buses, fake_client, SETTINGS)
    assert len(fake_client.matrix_calls) == 2
    assert [s.stop.id for s in result.buses[0].stops] == ["s002", "s001"]
    assert [s.stop.id for s in result.buses[1].stops] == ["s004", "s003"]


def test_pickup_point_ride_times_apply_to_all_riders(school, students, buses, fake_client):
    scenario = load_scenario(
        {
            "name": "pp",
            "ordering": "given",
            "buses": [
                {
                    "bus_id": "bus1",
                    "stops": [
                        {
                            "id": "pp",
                            "lat": 50.79,
                            "lon": 4.9,
                            "name": "P",
                            "students": ["s001", "s002"],
                        }
                    ],
                },
                {"bus_id": "bus2", "stops": ["s004", "s003"]},
            ],
        },
        students,
        buses,
    )
    result = evaluate(scenario, school, buses, fake_client, SETTINGS)
    d = result.to_dict()
    rides = {s["id"]: s["ride_min"] for s in d["students"]}
    assert rides["s001"] == rides["s002"]
    assert d["buses"][0]["stops"][0]["students"] == ["s001", "s002"]
    # dwell at a 2-student stop is 30 + 2*10
    stop = result.buses[0].stops[0]
    assert (stop.departure - stop.arrival).total_seconds() == 50


def test_unused_bus_is_reported(school, students, buses, fake_client):
    buses["bus3"] = type(buses["bus1"])(id="bus3", capacity=2, start=school.point)
    result = evaluate(given_scenario(students, buses), school, buses, fake_client, SETTINGS)
    assert result.to_dict()["summary"]["buses_unused"] == ["bus3"]
