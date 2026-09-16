import json
from pathlib import Path

import pytest

from busroutes.cli import main
from busroutes.config import REPO_ROOT, ConfigError, load_settings, resolve_data_dir
from busroutes.datapack import add_points, pack_points
from busroutes.models import Point, ScenarioError, load_data_pack, load_samples
from busroutes.tomtom import _point_key
from tests.conftest import FakeGeoClient
from tests.test_cli import isolate_from_repo_env
from tests.test_offline import write_origin_row


def write_pack(directory: Path, *, pickup_points: bool = True) -> Path:
    (directory / "school.json").write_text(
        json.dumps({"id": "school", "name": "x", "lat": 1.0, "lon": 2.0, "target_arrival": "08:20"})
    )
    (directory / "students.json").write_text(
        json.dumps([{"id": "s001", "lat": 1.1, "lon": 2.1, "zone": "z"}])
    )
    (directory / "buses.json").write_text(
        json.dumps([{"id": "bus1", "capacity": 20, "start": "school"}])
    )
    if pickup_points:
        (directory / "pickup_points.json").write_text(
            json.dumps([{"id": "pp-a", "lat": 1.5, "lon": 2.5, "name": "A"}])
        )
    return directory


def test_load_data_pack_reads_school_students_buses_and_pickup_points(tmp_path):
    write_pack(tmp_path)
    pack = load_data_pack(tmp_path)
    assert pack.path == tmp_path
    assert pack.school.id == "school"
    assert pack.school.target_arrival.hour == 8 and pack.school.target_arrival.minute == 20
    assert pack.students["s001"].zone == "z"
    assert pack.buses["bus1"].start == pack.school.point
    assert pack.pickup_points["pp-a"].name == "A"
    assert pack.pickup_points["pp-a"].point == Point(1.5, 2.5)


def test_load_data_pack_missing_pickup_points_is_empty_dict(tmp_path):
    write_pack(tmp_path, pickup_points=False)
    pack = load_data_pack(tmp_path)
    assert pack.pickup_points == {}


def test_load_data_pack_missing_school_json_raises_with_path_and_layout(tmp_path):
    write_pack(tmp_path)
    (tmp_path / "school.json").unlink()
    with pytest.raises(ScenarioError, match="school.json") as exc:
        load_data_pack(tmp_path)
    message = str(exc.value)
    assert str(tmp_path / "school.json") in message
    assert "students.json" in message
    assert "buses.json" in message
    assert "pickup_points.json" in message


def test_resolve_data_dir_cli_data_wins_over_env_and_default(tmp_path):
    cli = tmp_path / "cli"
    env_dir = tmp_path / "env"
    assert resolve_data_dir(cli_data=cli, env={"BUSROUTES_DATA_DIR": str(env_dir)}) == cli


def test_resolve_data_dir_cli_samples_is_alias_when_data_unset(tmp_path):
    samples = tmp_path / "samples"
    env_dir = tmp_path / "env"
    assert (
        resolve_data_dir(cli_samples=samples, env={"BUSROUTES_DATA_DIR": str(env_dir)}) == samples
    )


def test_resolve_data_dir_env_wins_over_default(tmp_path):
    env_dir = tmp_path / "env"
    assert resolve_data_dir(env={"BUSROUTES_DATA_DIR": str(env_dir)}) == env_dir


def test_resolve_data_dir_empty_env_falls_back_to_docs_samples():
    assert resolve_data_dir(env={"BUSROUTES_DATA_DIR": "  "}) == REPO_ROOT / "docs" / "samples"


def test_resolve_data_dir_default_is_docs_samples():
    assert resolve_data_dir(env={}) == REPO_ROOT / "docs" / "samples"


def test_load_settings_fills_data_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", "k")
    monkeypatch.setenv("BUSROUTES_REFERENCE_DATE", "2026-09-15")
    monkeypatch.setenv("BUSROUTES_DATA_DIR", str(tmp_path))
    settings = load_settings(env_path=tmp_path / "missing.env")
    assert settings.data_dir == tmp_path


def test_load_settings_data_dir_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", "k")
    monkeypatch.setenv("BUSROUTES_REFERENCE_DATE", "2026-09-15")
    monkeypatch.setenv("BUSROUTES_DATA_DIR", str(tmp_path / "env"))
    override = tmp_path / "override"
    settings = load_settings(env_path=tmp_path / "missing.env", data_dir=override)
    assert settings.data_dir == override


def test_load_settings_require_key_false_allows_empty_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.setenv("BUSROUTES_REFERENCE_DATE", "2026-09-15")
    settings = load_settings(env_path=tmp_path / "missing.env", require_key=False)
    assert settings.api_key == ""
    assert settings.reference_date.isoformat() == "2026-09-15"


def test_load_settings_still_requires_key_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.setenv("BUSROUTES_REFERENCE_DATE", "2026-09-15")
    with pytest.raises(ConfigError, match="TOMTOM_API_KEY ontbreekt"):
        load_settings(env_path=tmp_path / "missing.env")


def test_load_settings_require_key_false_still_requires_reference_date(tmp_path, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("BUSROUTES_REFERENCE_DATE", raising=False)
    with pytest.raises(ConfigError, match="referentiedatum ontbreekt"):
        load_settings(env_path=tmp_path / "missing.env", require_key=False)


def test_load_samples_still_returns_three_tuple(tmp_path):
    write_pack(tmp_path)
    pack = load_data_pack(tmp_path)
    school, students, buses = load_samples(tmp_path)
    assert (school, students, buses) == (pack.school, pack.students, pack.buses)


def test_data_status_counts_two_missing_pairs_without_api_key(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    write_pack(tmp_path, pickup_points=False)
    school = Point(1.0, 2.0)
    student = Point(1.1, 2.1)
    write_origin_row(
        tmp_path / "matrix",
        school,
        {_point_key(school): 0, _point_key(student): 10},
    )
    code = main(["data", "status", "--data", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "2" in out
    assert "ontbrek" in out.lower()


def test_data_fetch_matrix_dry_run_works_without_api_key(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    write_pack(tmp_path, pickup_points=False)
    code = main(["data", "fetch-matrix", "--dry-run", "--data", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out
    assert list(tmp_path.joinpath("matrix").rglob("*.json")) == []


def test_add_points_writes_student_snaps_and_fetches_only_new_row_and_column(tmp_path):
    write_pack(tmp_path, pickup_points=False)
    existing = pack_points(load_data_pack(tmp_path))
    client = FakeGeoClient()
    add_points(
        tmp_path,
        [{"id": "s002", "lat": 1.2, "lon": 2.2, "kind": "student", "zone": "z"}],
        client,
    )
    students = json.loads((tmp_path / "students.json").read_text())
    assert {s["id"] for s in students} == {"s001", "s002"}
    assert client.snap_calls == [Point(1.2, 2.2)]
    requested = sum(len(origins) * len(dests) for origins, dests in client.matrix_calls)
    assert 2 * len(existing) <= requested <= 2 * len(existing) + 1


def test_data_add_points_subcommand_exists():
    from busroutes.cli import build_parser

    args = build_parser().parse_args(["data", "add-points", "new.json", "--data", "pack"])
    assert args.json.name == "new.json"
    assert args.data.name == "pack"


def test_data_status_missing_pack_file_is_scenario_error(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    write_pack(tmp_path)
    (tmp_path / "school.json").unlink()
    code = main(["data", "status", "--data", str(tmp_path)])
    assert code == 1
    err = capsys.readouterr().err
    assert "school.json" in err
    assert err.startswith("Fout:")


def test_data_geocode_does_not_exist():
    from busroutes.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["data", "geocode", "addresses.csv"])


def test_data_fetch_matrix_without_dry_run_requires_key(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    monkeypatch.setenv("BUSROUTES_REFERENCE_DATE", "2026-09-15")
    write_pack(tmp_path, pickup_points=False)
    code = main(["data", "fetch-matrix", "--data", str(tmp_path)])
    assert code == 1
    assert "TOMTOM_API_KEY" in capsys.readouterr().err


def test_add_points_uses_original_point_when_snap_returns_none(tmp_path, capsys):
    write_pack(tmp_path, pickup_points=False)

    class NoSnap(FakeGeoClient):
        def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point | None:
            del radius_m
            self.snap_calls.append(point)
            return None

    add_points(
        tmp_path,
        [{"id": "s002", "lat": 1.2, "lon": 2.2, "kind": "student"}],
        NoSnap(),
    )
    student = next(
        s for s in json.loads((tmp_path / "students.json").read_text()) if s["id"] == "s002"
    )
    assert student["lat"] == 1.2 and student["lon"] == 2.2
    assert "straat" in capsys.readouterr().err.lower()


def test_pack_points_includes_bus_start_that_is_not_school(tmp_path):
    write_pack(tmp_path, pickup_points=False)
    buses = json.loads((tmp_path / "buses.json").read_text())
    buses.append({"id": "bus2", "capacity": 10, "start": {"lat": 9.0, "lon": 9.0}})
    (tmp_path / "buses.json").write_text(json.dumps(buses))
    points = pack_points(load_data_pack(tmp_path))
    assert Point(9.0, 9.0) in points
