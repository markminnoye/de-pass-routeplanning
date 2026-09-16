"""CLI: evaluate --offline, --data, and --samples deprecation. No TomTom key."""

from __future__ import annotations

import json
from pathlib import Path

from busroutes.cli import main
from busroutes.config import read_env_file
from busroutes.models import Point
from busroutes.tomtom import _point_key
from tests.test_offline import write_origin_row

SCHOOL = {
    "id": "school",
    "name": "de pass",
    "lat": 50.7782,
    "lon": 4.8960,
    "target_arrival": "08:20",
}
STUDENT = {"id": "s001", "lat": 50.7900, "lon": 4.9000, "zone": "test"}
BUS = {"id": "bus1", "capacity": 20, "start": "school"}
SCENARIO = {
    "name": "mini",
    "ordering": "given",
    "buses": [{"bus_id": "bus1", "stops": ["s001"]}],
}

CELL_TO_STOP_S = 400
CELL_TO_SCHOOL_S = 500  # ride time; FakeGeoClient would be ~haversine/10 ≈ 134s


def isolate_from_repo_env(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("BUSROUTES_DATA_DIR", raising=False)
    monkeypatch.delenv("BUSROUTES_REFERENCE_DATE", raising=False)
    monkeypatch.setattr("busroutes.config.read_env_file", lambda path: {})


def write_mini_pack(directory: Path, *, matrix: bool = True, complete: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "school.json").write_text(json.dumps(SCHOOL))
    (directory / "students.json").write_text(json.dumps([STUDENT]))
    (directory / "buses.json").write_text(json.dumps([BUS]))
    (directory / "scenario.json").write_text(json.dumps(SCENARIO))
    if matrix:
        school = Point(SCHOOL["lat"], SCHOOL["lon"])
        student = Point(STUDENT["lat"], STUDENT["lon"])
        cells = directory / "matrix"
        write_origin_row(cells, school, {_point_key(student): CELL_TO_STOP_S})
        if complete:
            write_origin_row(cells, student, {_point_key(school): CELL_TO_SCHOOL_S})
    return directory


def evaluate_argv(pack: Path, out: Path, *extra: str) -> list[str]:
    return [
        "evaluate",
        str(pack / "scenario.json"),
        "--data",
        str(pack),
        "--out",
        str(out),
        "--reference-date",
        "2026-09-15",
        *extra,
    ]


def test_evaluate_offline_writes_metrics_from_cells_without_api_key(tmp_path, monkeypatch):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    out = tmp_path / "out"
    code = main(evaluate_argv(pack, out, "--offline"))
    assert code == 0
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["settings"]["mode"] == "offline"
    assert metrics["settings"]["km_estimated"] is True
    assert metrics["students"][0]["ride_min"] == round(CELL_TO_SCHOOL_S / 60, 1)
    html = (out / "map.html").read_text()
    assert "Offline-schatting: tijden uit de matrix, rechte lijnen, km geschat" in html


def test_evaluate_offline_missing_pair_exits_with_fetch_matrix(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack", complete=False)
    out = tmp_path / "out"
    code = main(evaluate_argv(pack, out, "--offline"))
    assert code == 1
    err = capsys.readouterr().err
    assert "fetch-matrix" in err
    assert err.startswith("Fout:")


def test_evaluate_samples_flag_prints_deprecation_and_uses_that_dir(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    out = tmp_path / "out"
    code = main(
        [
            "evaluate",
            str(pack / "scenario.json"),
            "--samples",
            str(pack),
            "--out",
            str(out),
            "--reference-date",
            "2026-09-15",
            "--offline",
        ]
    )
    assert code == 0
    err = capsys.readouterr().err
    assert "verouderd" in err.lower() or "deprecated" in err.lower() or "--data" in err
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["settings"]["mode"] == "offline"


def test_evaluate_offline_uses_data_dir_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("BUSROUTES_DATA_DIR", raising=False)
    monkeypatch.delenv("BUSROUTES_REFERENCE_DATE", raising=False)
    pack = write_mini_pack(tmp_path / "pack")
    env_file = tmp_path / ".env"
    env_file.write_text(f"BUSROUTES_DATA_DIR={pack}\n")
    monkeypatch.setattr("busroutes.config.read_env_file", lambda path: read_env_file(env_file))
    out = tmp_path / "out"
    code = main(
        [
            "evaluate",
            str(pack / "scenario.json"),
            "--out",
            str(out),
            "--reference-date",
            "2026-09-15",
            "--offline",
        ]
    )
    assert code == 0
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["summary"]["students"] == 1
    assert metrics["settings"]["mode"] == "offline"
