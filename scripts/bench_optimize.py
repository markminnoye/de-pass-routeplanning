"""Time optimize_assign on an in-memory clustered world. Not part of the test suite.

Run: uv run python scripts/bench_optimize.py --stops 40 --buses 4 --max-seconds 1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from busroutes.optimize import optimize_assign, score_scenario  # noqa: E402
from tests.scale import make_scale_world, mixed_scenario  # noqa: E402
from tests.test_optimize import SETTINGS, _travel  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stops", type=int, required=True)
    parser.add_argument("--buses", type=int, required=True)
    parser.add_argument("--max-seconds", type=float, default=30)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    world = make_scale_world(args.stops, args.buses, args.seed)
    school, _students, buses, client, _clusters = world
    scenario = mixed_scenario(world)
    calls = {"n": 0}
    base = _travel(client)

    def travel(a, b) -> int:
        calls["n"] += 1
        return base(a, b)

    before = score_scenario(scenario, buses, school, travel, SETTINGS)
    calls["n"] = 0
    started = time.perf_counter()
    result = optimize_assign(
        scenario,
        buses,
        school,
        travel,
        SETTINGS,
        seed=args.seed,
        max_seconds=args.max_seconds,
    )
    elapsed = time.perf_counter() - started
    after = score_scenario(result, buses, school, travel, SETTINGS)
    print(
        f"stops={args.stops} buses={args.buses} wall={elapsed:.2f}s "
        f"travel_calls={calls['n']} perturbations={result.perturbations} "
        f"stopped_by={result.stopped_by} score {before} -> {after}"
    )


if __name__ == "__main__":
    main()
