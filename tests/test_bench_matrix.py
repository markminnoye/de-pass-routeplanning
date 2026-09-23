"""The completed benchmark matrix is a pure function of the sample cells."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from busroutes.config import load_settings
from busroutes.evaluate import evaluate
from busroutes.geo import haversine_m
from busroutes.models import Point, load_samples, load_scenario_file
from busroutes.offline import OfflineClient

ROOT = Path(__file__).resolve().parents[1]


def _bench_matrix():
    path = ROOT / "scripts" / "bench_matrix.py"
    spec = importlib.util.spec_from_file_location("bench_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_travel_model_is_stable_on_the_sample_matrix():
    module = _bench_matrix()
    model = module.fit_travel_model(ROOT / "docs" / "samples" / "matrix")
    assert model.n_cells == 4956
    assert model.alpha_s == pytest.approx(277.8, abs=0.1)
    assert model.beta_s_per_m == pytest.approx(0.075533, rel=1e-4)
    assert model.r2 == pytest.approx(0.868, abs=0.005)
    assert 5 < model.median_speed_m_s < 10


def test_speed_client_is_symmetric_offline_and_matches_the_line():
    module = _bench_matrix()
    model = module.fit_travel_model(ROOT / "docs" / "samples" / "matrix")
    client = module.SpeedMatrixClient(model)
    assert isinstance(client, OfflineClient)
    origin = Point(50.78, 4.90)
    dest = Point(50.90, 5.02)
    meters = haversine_m(origin, dest)
    assert client.pair_seconds(origin, dest) == model.seconds(meters)
    assert client.pair_seconds(origin, dest) == client.pair_seconds(dest, origin)
    assert client.pair_seconds(origin, origin) == 0
    travel = module.freeze_travel(client, [origin, dest])
    assert travel(origin, dest) == client.matrix([origin], [dest])[0][0]


def test_load_imbalance_counts_empty_buses():
    module = _bench_matrix()
    assert module.load_imbalance([10, 30, 0]) == 30
    assert module.load_imbalance([]) == 0


def test_speed_client_evaluates_regiobus_offline():
    module = _bench_matrix()
    data = ROOT / "docs" / "samples"
    model = module.fit_travel_model(data / "matrix")
    client = module.SpeedMatrixClient(model)
    settings = load_settings(require_key=False, reference_date=date(2026, 9, 15), data_dir=data)
    school, students, buses = load_samples(data)
    scenario = load_scenario_file(data / "scenarios" / "regiobus-per-zone.json", students, buses)
    result = evaluate(scenario, school, students, buses, client, settings)
    summary = result.to_dict()
    assert summary["settings"]["mode"] == "offline"
    assert summary["settings"]["km_estimated"] is True
    assert summary["summary"]["students"] == 140
    assert summary["summary"]["max_ride_min"] > 0
