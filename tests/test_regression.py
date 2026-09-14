"""Regression check against docs/samples/expected/ (DoD 3 + 4).

Needs TomTom (key + network or a warm .cache/tomtom); skipped unless
BUSROUTES_REGRESSION=1. Run: BUSROUTES_REGRESSION=1 uv run pytest tests/test_regression.py
"""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from busroutes.config import REPO_ROOT, load_settings
from busroutes.evaluate import evaluate
from busroutes.models import load_samples, load_scenario_file
from busroutes.tomtom import TomTomClient

SAMPLES = REPO_ROOT / "docs" / "samples"
EXPECTED = sorted((SAMPLES / "expected").glob("*.metrics.json"))

pytestmark = pytest.mark.skipif(
    os.environ.get("BUSROUTES_REGRESSION") != "1", reason="set BUSROUTES_REGRESSION=1"
)


@pytest.mark.parametrize("expected_path", EXPECTED, ids=[p.stem for p in EXPECTED])
def test_scenario_matches_expected(expected_path: Path):
    expected = json.loads(expected_path.read_text())
    reference = date.fromisoformat(expected["settings"]["depart_at_reference"][:10])
    settings = load_settings(reference_date=reference, traffic=expected["settings"]["traffic"])
    school, students, buses = load_samples(SAMPLES)
    scenario = load_scenario_file(
        SAMPLES / "scenarios" / f"{expected['scenario']}.json", students, buses
    )
    client = TomTomClient(settings.api_key, settings.cache_dir, settings.traffic)
    actual = evaluate(scenario, school, buses, client, settings).to_dict()
    assert actual == expected
