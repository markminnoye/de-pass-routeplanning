"""CLI: evaluate --offline, --data, and --samples deprecation. No TomTom key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from busroutes.cli import build_parser, main
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


def test_no_cache_help_mentions_route_cache_and_overpass_not_matrix():
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    help_text = sub.choices["evaluate"].format_help()
    lowered = help_text.lower()
    assert "routecache" in lowered or "route-cache" in lowered
    assert "overpass" in lowered
    assert "tomtom-cache" not in lowered
    assert "TomTom- en Overpass-cache" not in help_text


def test_no_cache_warning_mentions_route_cache_and_overpass_not_matrix(
    tmp_path, monkeypatch, capsys
):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    out = tmp_path / "out"
    code = main(evaluate_argv(pack, out, "--offline", "--no-cache"))
    assert code == 0
    err = capsys.readouterr().err.lower()
    assert "routecache" in err or "route-cache" in err
    assert "overpass" in err
    assert "matrix" not in err
    assert "negeert de cache" not in err


def optimize_argv(pack: Path, *extra: str) -> list[str]:
    return [
        "optimize",
        str(pack / "scenario.json"),
        "--data",
        str(pack),
        "--reference-date",
        "2026-09-15",
        *extra,
    ]


def test_optimize_order_writes_given_json_without_api_key(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    code = main(optimize_argv(pack, "--order"))
    assert code == 0
    out_path = pack / "mini-optimized.json"
    assert out_path.is_file()
    payload = json.loads(out_path.read_text())
    assert payload["ordering"] == "given"
    assert "geoptimaliseerd (order" in payload["description"]
    assert " · geoptimaliseerd (order, seed 0)" in payload["description"]
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Fout:" not in captured.err
    assert "TOMTOM_API_KEY" not in combined
    assert "max_ride_min" in captured.out
    assert "avg_ride_min" in captured.out
    assert "total_drive_min" in captured.out


NEAR = {"id": "s001", "lat": 50.7900, "lon": 4.9000, "zone": "test"}
FAR = {"id": "s002", "lat": 50.8000, "lon": 4.9100, "zone": "test"}


def write_auto_pack(directory: Path) -> Path:
    """Two stops, scenario ordering=auto, file order near-then-far (the worse order).

    Cells (with the 0-diagonal TomTom also stores): school→near 300, school→far 600,
    near↔far 300, near→school 300, far→school 600. Near-first: rides 300+40+600 = 940 s
    (near) and 600 s (far). Far-first: 300+40+300 = 640 s (far) and 300 s (near), so
    niveau A flips the file order and 'vóór' must already reflect that.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "school.json").write_text(json.dumps(SCHOOL))
    (directory / "students.json").write_text(json.dumps([NEAR, FAR]))
    (directory / "buses.json").write_text(json.dumps([BUS]))
    (directory / "scenario.json").write_text(
        json.dumps(
            {
                "name": "auto",
                "ordering": "auto",
                "buses": [{"bus_id": "bus1", "stops": ["s001", "s002"]}],
            }
        )
    )
    school = Point(SCHOOL["lat"], SCHOOL["lon"])
    near = Point(NEAR["lat"], NEAR["lon"])
    far = Point(FAR["lat"], FAR["lon"])
    cells = directory / "matrix"
    s, n, f = _point_key(school), _point_key(near), _point_key(far)
    write_origin_row(cells, school, {s: 0, n: 300, f: 600})
    write_origin_row(cells, near, {n: 0, f: 300, s: 300})
    write_origin_row(cells, far, {f: 0, n: 300, s: 600})
    return directory


def _printed_before_after(stdout: str, key: str) -> tuple[float, float]:
    line = next(line for line in stdout.splitlines() if line.startswith(f"{key} "))
    before, after = line[len(key) + 1 :].split(" → ")
    return float(before), float(after)


def test_optimize_before_figures_match_evaluate_offline(tmp_path, monkeypatch, capsys):
    """'Vóór' is what evaluate --offline reports for the input scenario, not the
    file order forced to 'given'; for an ordering=auto scenario --order is a no-op
    in the numbers and must print equal before/after."""
    isolate_from_repo_env(monkeypatch)
    pack = write_auto_pack(tmp_path / "pack")
    out_dir = tmp_path / "out"
    assert main(evaluate_argv(pack, out_dir, "--offline")) == 0
    evaluated = json.loads((out_dir / "metrics.json").read_text())["summary"]
    capsys.readouterr()

    assert main(optimize_argv(pack, "--order", "--out", str(tmp_path / "opt.json"))) == 0
    out = capsys.readouterr().out
    for key in ("max_ride_min", "avg_ride_min", "total_drive_min"):
        before, after = _printed_before_after(out, key)
        assert before == evaluated[key], key
        assert after == evaluated[key], key


def test_optimize_assign_seed_zero_is_deterministic(tmp_path, monkeypatch):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    out1 = tmp_path / "first.json"
    out2 = tmp_path / "second.json"
    assert main(optimize_argv(pack, "--assign", "--seed", "0", "--out", str(out1))) == 0
    assert main(optimize_argv(pack, "--assign", "--seed", "0", "--out", str(out2))) == 0
    assert out1.read_text() == out2.read_text()


def test_optimize_rejects_order_and_assign_together(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["optimize", "scenario.json", "--order", "--assign"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "--order" in err and "--assign" in err


def test_optimize_requires_order_or_assign(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["optimize", "scenario.json"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "--order" in err and "--assign" in err


def test_optimize_missing_pair_exits_with_fetch_matrix(tmp_path, monkeypatch, capsys):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack", complete=False)
    code = main(optimize_argv(pack, "--order"))
    assert code == 1
    err = capsys.readouterr().err
    assert "fetch-matrix" in err
    assert err.startswith("Fout:")


def test_optimize_out_writes_to_given_path(tmp_path, monkeypatch):
    isolate_from_repo_env(monkeypatch)
    pack = write_mini_pack(tmp_path / "pack")
    out = tmp_path / "custom" / "result.json"
    code = main(optimize_argv(pack, "--order", "--out", str(out)))
    assert code == 0
    assert out.is_file()
    assert not (pack / "mini-optimized.json").exists()
    payload = json.loads(out.read_text())
    assert payload["ordering"] == "given"
