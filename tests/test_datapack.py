import json
from pathlib import Path

import pytest

from busroutes.config import REPO_ROOT, ConfigError, load_settings, resolve_data_dir
from busroutes.models import Point, ScenarioError, load_data_pack, load_samples


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
