import json

import pytest

from busroutes.models import (
    Point,
    ScenarioError,
    load_data_pack,
    load_samples,
    load_scenario,
    scenario_to_dict,
)


def scenario_dict(**overrides):
    base = {
        "name": "t",
        "description": "",
        "ordering": "given",
        "buses": [
            {"bus_id": "bus1", "stops": ["s001", "s002"]},
            {"bus_id": "bus2", "stops": ["s003", "s004"]},
        ],
    }
    base.update(overrides)
    return base


def test_string_stop_resolves_to_student_point(students, buses):
    scenario = load_scenario(scenario_dict(), students, buses)
    stop = scenario.buses[0].stops[0]
    assert stop.id == "s001"
    assert stop.point == students["s001"].point
    assert stop.students == ["s001"]


def test_pickup_point_stop_keeps_own_location(students, buses):
    d = scenario_dict(
        buses=[
            {
                "bus_id": "bus1",
                "stops": [
                    {
                        "id": "pp-x",
                        "lat": 50.8,
                        "lon": 4.9,
                        "name": "X",
                        "students": ["s001", "s002"],
                    }
                ],
            },
            {"bus_id": "bus2", "stops": ["s003", "s004"]},
        ]
    )
    scenario = load_scenario(d, students, buses)
    stop = scenario.buses[0].stops[0]
    assert stop.point == Point(50.8, 4.9)
    assert stop.name == "X"
    assert stop.students == ["s001", "s002"]


@pytest.mark.parametrize(
    ("buses_field", "message"),
    [
        (
            [{"bus_id": "bus1", "stops": ["s001", "s002"]}, {"bus_id": "bus2", "stops": ["s003"]}],
            "s004",  # not assigned
        ),
        (
            [
                {"bus_id": "bus1", "stops": ["s001", "s002"]},
                {"bus_id": "bus2", "stops": ["s003", "s004", "s001"]},
            ],
            "s001",  # assigned twice
        ),
        (
            [
                {"bus_id": "bus1", "stops": ["s001", "s002", "s003"]},
                {"bus_id": "bus2", "stops": ["s004"]},
            ],
            "capacity",
        ),
        (
            [
                {"bus_id": "bus9", "stops": ["s001", "s002"]},
                {"bus_id": "bus2", "stops": ["s003", "s004"]},
            ],
            "bus9",
        ),
        (
            [
                {"bus_id": "bus1", "stops": ["s001", "nope"]},
                {"bus_id": "bus2", "stops": ["s003", "s004"]},
            ],
            "nope",
        ),
    ],
)
def test_validation_errors(students, buses, buses_field, message):
    with pytest.raises(ScenarioError, match=message):
        load_scenario(scenario_dict(buses=buses_field), students, buses)


def test_unknown_ordering_rejected(students, buses):
    with pytest.raises(ScenarioError, match="ordering"):
        load_scenario(scenario_dict(ordering="random"), students, buses)


def test_load_samples_reads_repo_samples(tmp_path):
    (tmp_path / "school.json").write_text(
        json.dumps({"id": "school", "name": "x", "lat": 1.0, "lon": 2.0, "target_arrival": "08:20"})
    )
    (tmp_path / "students.json").write_text(
        json.dumps([{"id": "s001", "lat": 1.1, "lon": 2.1, "zone": "z"}])
    )
    (tmp_path / "buses.json").write_text(
        json.dumps(
            [
                {"id": "bus1", "capacity": 20, "start": "school"},
                {"id": "bus2", "capacity": 20, "start": {"lat": 1.5, "lon": 2.5}},
            ]
        )
    )
    school, students, buses = load_samples(tmp_path)
    assert school.target_arrival.hour == 8 and school.target_arrival.minute == 20
    assert students["s001"].zone == "z"
    assert buses["bus1"].start == school.point
    assert buses["bus2"].start == Point(1.5, 2.5)
    pack = load_data_pack(tmp_path)
    assert (school, students, buses) == (pack.school, pack.students, pack.buses)
    assert pack.pickup_points == {}


def test_bus_level_ordering_overrides_scenario(students, buses):
    d = scenario_dict(ordering="auto")
    d["buses"][0]["ordering"] = "given"
    scenario = load_scenario(d, students, buses)
    assert scenario.buses[0].ordering == "given"
    assert scenario.buses[1].ordering == "auto"


def test_bus_level_ordering_validated(students, buses):
    d = scenario_dict()
    d["buses"][0]["ordering"] = "whatever"
    with pytest.raises(ScenarioError, match="ordering"):
        load_scenario(d, students, buses)


def test_ordering_defaults_to_auto(students, buses):
    d = scenario_dict()
    del d["ordering"]
    assert load_scenario(d, students, buses).ordering == "auto"


def test_pinned_true_on_bus1_defaults_false_on_bus2(students, buses):
    d = scenario_dict()
    d["buses"][0]["pinned"] = True
    scenario = load_scenario(d, students, buses)
    assert scenario.buses[0].pinned is True
    assert scenario.buses[1].pinned is False


def test_pinned_false_is_false(students, buses):
    d = scenario_dict()
    d["buses"][0]["pinned"] = False
    scenario = load_scenario(d, students, buses)
    assert scenario.buses[0].pinned is False


@pytest.mark.parametrize("value", ["yes", 1])
def test_pinned_non_bool_raises(students, buses, value):
    d = scenario_dict()
    d["buses"][0]["pinned"] = value
    with pytest.raises(ScenarioError, match="pinned"):
        load_scenario(d, students, buses)


def test_pinned_stops_keeps_known_ids_in_json_order(students, buses):
    scenario = load_scenario(scenario_dict(pinned_stops=["s004", "s001"]), students, buses)
    assert scenario.pinned_stops == ("s004", "s001")


def test_missing_pinned_stops_is_empty(students, buses):
    scenario = load_scenario(scenario_dict(), students, buses)
    assert scenario.pinned_stops == ()


def test_pinned_bus_does_not_imply_pinned_stops(students, buses):
    d = scenario_dict()
    d["buses"][0]["pinned"] = True
    scenario = load_scenario(d, students, buses)
    assert scenario.buses[0].pinned is True
    assert scenario.pinned_stops == ()


def test_unknown_pinned_stop_id_raises(students, buses):
    with pytest.raises(ScenarioError, match="ghost"):
        load_scenario(scenario_dict(pinned_stops=["ghost"]), students, buses)


@pytest.mark.parametrize("value", ["s001", [1]])
def test_pinned_stops_wrong_type_raises(students, buses, value):
    with pytest.raises(ScenarioError, match="pinned_stops"):
        load_scenario(scenario_dict(pinned_stops=value), students, buses)


def _pickup_and_pinned_scenario():
    return scenario_dict(
        pinned_stops=["pp-x", "s003"],
        buses=[
            {
                "bus_id": "bus1",
                "pinned": True,
                "stops": [
                    {
                        "id": "pp-x",
                        "lat": 50.8,
                        "lon": 4.9,
                        "name": "X",
                        "students": ["s001", "s002"],
                    }
                ],
            },
            {"bus_id": "bus2", "stops": ["s003", "s004"]},
        ],
    )


def test_scenario_to_dict_round_trip(students, buses):
    loaded = load_scenario(_pickup_and_pinned_scenario(), students, buses)
    dumped = scenario_to_dict(loaded)
    reloaded = load_scenario(dumped, students, buses)
    assert [b.bus_id for b in reloaded.buses] == [b.bus_id for b in loaded.buses]
    assert [[s.id for s in b.stops] for b in reloaded.buses] == [
        [s.id for s in b.stops] for b in loaded.buses
    ]
    assert [b.pinned for b in reloaded.buses] == [True, False]
    assert reloaded.pinned_stops == ("pp-x", "s003")
    assert reloaded.buses[0].stops[0].point == Point(50.8, 4.9)
    assert reloaded.buses[1].stops[0].point == students["s003"].point
    assert reloaded.buses[1].stops[1].point == students["s004"].point


def test_scenario_to_dict_omits_false_pinned_and_empty_pinned_stops(students, buses):
    dumped = scenario_to_dict(load_scenario(scenario_dict(), students, buses))
    assert "pinned_stops" not in dumped
    assert all("pinned" not in bus for bus in dumped["buses"])
    assert dumped["buses"][0]["stops"] == ["s001", "s002"]


def test_scenario_to_dict_dumps_stored_ordering(students, buses):
    d = scenario_dict()
    del d["ordering"]
    dumped = scenario_to_dict(load_scenario(d, students, buses))
    assert dumped["ordering"] == "auto"


def test_scenario_to_dict_writes_pickup_object_and_pinned_true(students, buses):
    dumped = scenario_to_dict(load_scenario(_pickup_and_pinned_scenario(), students, buses))
    assert dumped["buses"][0]["pinned"] is True
    assert "pinned" not in dumped["buses"][1]
    assert dumped["pinned_stops"] == ["pp-x", "s003"]
    assert dumped["buses"][0]["stops"] == [
        {"id": "pp-x", "lat": 50.8, "lon": 4.9, "name": "X", "students": ["s001", "s002"]}
    ]
    assert dumped["buses"][1]["stops"] == ["s003", "s004"]
    assert dumped["ordering"] == "given"
