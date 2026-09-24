from dataclasses import replace
from datetime import date, datetime

from busroutes.config import BRUSSELS, Settings
from busroutes.evaluate import evaluate
from busroutes.models import load_scenario
from busroutes.offline import OfflineClient
from busroutes.tomtom import _point_key
from tests.conftest import haversine_m
from tests.test_offline import write_origin_row

SETTINGS = Settings(
    api_key="test",
    cache_dir=None,
    dwell_base_s=30,
    dwell_per_student_s=10,
    reference_date=date(2026, 9, 15),  # a Tuesday
)
FREE_SETTINGS = replace(SETTINGS, ordering="haversine")


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
    result = evaluate(
        given_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    )
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
    # The bus starts at the school, so the empty leg out is not part of the route.
    assert bus1.departure == first_stop.arrival
    assert leg_first > 0

    # ride time = from leaving the stop until arriving at school
    assert last_stop.ride_s == leg_last
    assert first_stop.ride_s == leg_mid + dwell + leg_last
    assert bus1.drive_s == leg_mid + leg_last
    assert bus1.length_m == sum(leg.length_m for leg in bus1.route.legs)
    assert bus1.occupancy == 1.0


def test_summary_metrics(school, students, buses, fake_client):
    result = evaluate(
        given_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    )
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
    evaluate(given_scenario(students, buses), school, students, buses, fake_client, SETTINGS)
    assert fake_client.matrix_calls == []
    assert len(fake_client.route_calls) == 2


def auto_scenario(students, buses):
    return load_scenario(
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


def test_auto_ordering_uses_matrix_and_visits_far_stop_first(school, students, buses, fake_client):
    result = evaluate(
        auto_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    )
    assert SETTINGS.ordering == "matrix", "real travel times are the default"
    assert len(fake_client.matrix_calls) == 2
    assert [s.stop.id for s in result.buses[0].stops] == ["s002", "s001"]
    assert [s.stop.id for s in result.buses[1].stops] == ["s004", "s003"]


def test_haversine_ordering_buys_nothing_from_tomtom(school, students, buses, fake_client):
    result = evaluate(
        auto_scenario(students, buses), school, students, buses, fake_client, FREE_SETTINGS
    )
    assert fake_client.matrix_calls == []
    assert [s.stop.id for s in result.buses[0].stops] == ["s002", "s001"]
    assert [s.stop.id for s in result.buses[1].stops] == ["s004", "s003"]


def test_ordering_strategy_is_recorded_in_metrics(school, students, buses, fake_client):
    scenario = given_scenario(students, buses)
    for settings, expected in ((SETTINGS, "matrix"), (FREE_SETTINGS, "haversine")):
        d = evaluate(scenario, school, students, buses, fake_client, settings).to_dict()
        assert d["settings"]["ordering_strategy"] == expected


def test_to_dict_records_tomtom_mode_for_fake_client(school, students, buses, fake_client):
    d = evaluate(
        given_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    ).to_dict()
    assert d["settings"]["mode"] == "tomtom"
    assert "km_estimated" not in d["settings"]


def test_to_dict_records_offline_mode_and_cell_ride_times(tmp_path, school, students, buses):
    one = {"s001": students["s001"]}
    one_bus = {"bus1": buses["bus1"]}
    scenario = load_scenario(
        {"name": "off", "ordering": "given", "buses": [{"bus_id": "bus1", "stops": ["s001"]}]},
        one,
        one_bus,
    )
    school_pt, student_pt = school.point, one["s001"].point
    write_origin_row(tmp_path, school_pt, {_point_key(student_pt): 400})
    write_origin_row(tmp_path, student_pt, {_point_key(school_pt): 500})
    d = evaluate(scenario, school, one, one_bus, OfflineClient(tmp_path), SETTINGS).to_dict()
    assert d["settings"]["mode"] == "offline"
    assert d["settings"]["km_estimated"] is True
    assert d["students"][0]["ride_min"] == round(500 / 60, 1)


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
    result = evaluate(scenario, school, students, buses, fake_client, SETTINGS)
    d = result.to_dict()
    rides = {s["id"]: s["ride_min"] for s in d["students"]}
    assert rides["s001"] == rides["s002"]
    assert d["buses"][0]["stops"][0]["students"] == ["s001", "s002"]
    # dwell at a 2-student stop is 30 + 2*10
    stop = result.buses[0].stops[0]
    assert (stop.departure - stop.arrival).total_seconds() == 50


def test_unused_bus_is_reported(school, students, buses, fake_client):
    buses["bus3"] = type(buses["bus1"])(id="bus3", capacity=2, start=school.point)
    result = evaluate(
        given_scenario(students, buses), school, students, buses, fake_client, SETTINGS
    )
    assert result.to_dict()["summary"]["buses_unused"] == ["bus3"]


def test_bus_level_ordering_given_keeps_order_while_others_auto(
    school, students, buses, fake_client
):
    scenario = load_scenario(
        {
            "name": "mixed",
            "ordering": "auto",
            "buses": [
                {"bus_id": "bus1", "stops": ["s001", "s002"], "ordering": "given"},
                {"bus_id": "bus2", "stops": ["s003", "s004"]},
            ],
        },
        students,
        buses,
    )
    result = evaluate(scenario, school, students, buses, fake_client, SETTINGS)
    assert [s.stop.id for s in result.buses[0].stops] == ["s001", "s002"]  # kept
    assert [s.stop.id for s in result.buses[1].stops] == ["s004", "s003"]  # auto
    assert len(fake_client.matrix_calls) == 1


def test_distance_home_to_stop_and_long_ride_counts(school, students, buses, fake_client):
    scenario = load_scenario(
        {
            "name": "pp",
            "ordering": "given",
            "buses": [
                {
                    "bus_id": "bus1",
                    "stops": [{"id": "pp", "lat": 50.79, "lon": 4.9, "students": ["s001", "s002"]}],
                },
                {"bus_id": "bus2", "stops": ["s004", "s003"]},
            ],
        },
        students,
        buses,
    )
    d = evaluate(scenario, school, students, buses, fake_client, SETTINGS).to_dict()
    by_id = {s["id"]: s for s in d["students"]}
    assert by_id["s003"]["to_stop_km"] == 0.0  # home stop
    assert 1.0 < by_id["s002"]["to_stop_km"] < 1.5  # s002 is ~1.3 km from the pickup point
    assert d["summary"]["max_to_stop_km"] == by_id["s002"]["to_stop_km"]
    assert d["summary"]["students_with_to_stop_over_1km"] == 1
    assert d["summary"]["rides_over_60_min"] == 0
    assert d["summary"]["rides_over_90_min"] == 0
