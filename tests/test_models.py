import json

import pytest

from busroutes.models import Point, ScenarioError, load_data_pack, load_samples, load_scenario


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
