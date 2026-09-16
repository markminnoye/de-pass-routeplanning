"""Always-on offline regression against docs/samples/expected/offline/. No TomTom key."""

from __future__ import annotations

import json
from datetime import date

import pytest

from busroutes.config import REPO_ROOT, load_settings
from busroutes.evaluate import evaluate
from busroutes.models import load_samples, load_scenario_file
from busroutes.offline import OfflineClient
from tests.test_cli import isolate_from_repo_env

SAMPLES = REPO_ROOT / "docs" / "samples"
SCENARIOS = ("opstapplaatsen", "regiobus-per-zone", "spreiding-gemengd")


@pytest.mark.parametrize("name", SCENARIOS)
def test_offline_evaluate_matches_expected(name: str, monkeypatch):
    isolate_from_repo_env(monkeypatch)
    expected_path = SAMPLES / "expected" / "offline" / f"{name}.metrics.json"
    expected = json.loads(expected_path.read_text())
    reference = date.fromisoformat(expected["settings"]["depart_at_reference"][:10])
    settings = load_settings(
        require_key=False,
        reference_date=reference,
        traffic=expected["settings"]["traffic"],
        ordering=expected["settings"]["ordering_strategy"],
        data_dir=SAMPLES,
    )
    school, students, buses = load_samples(SAMPLES)
    scenario = load_scenario_file(SAMPLES / "scenarios" / f"{name}.json", students, buses)
    actual = evaluate(
        scenario, school, students, buses, OfflineClient(SAMPLES / "matrix"), settings
    ).to_dict()
    assert actual == expected
