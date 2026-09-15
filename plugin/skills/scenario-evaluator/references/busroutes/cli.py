"""Command line: `busroutes evaluate <scenario.json>` and `busroutes compare <metrics.json>...`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from busroutes.config import REPO_ROOT, ConfigError, load_settings
from busroutes.evaluate import evaluate
from busroutes.models import ScenarioError, load_samples, load_scenario_file
from busroutes.render import compare_markdown, render_map_html, to_geojson
from busroutes.tomtom import TomTomClient, TomTomError, usage_report

DEFAULT_SAMPLES = REPO_ROOT / "docs" / "samples"
DEFAULT_OUT = REPO_ROOT / "out"


def cmd_evaluate(args: argparse.Namespace) -> int:
    overrides: dict[str, object] = {}
    if args.traffic:
        overrides["traffic"] = args.traffic
    if args.ordering:
        overrides["ordering"] = args.ordering
    if args.reference_date:
        overrides["reference_date"] = args.reference_date
    if args.no_cache:
        overrides["cache_dir"] = None
        print(
            "Let op: --no-cache negeert de cache, dus TomTom rekent alles opnieuw aan.",
            file=sys.stderr,
        )
    settings = load_settings(**overrides)
    school, students, buses = load_samples(args.samples)
    scenario = load_scenario_file(args.scenario, students, buses)
    client = TomTomClient(
        settings.api_key, settings.cache_dir, settings.traffic, dry_run=args.dry_run
    )

    result = evaluate(scenario, school, students, buses, client, settings)
    print(f"Referentiedatum {settings.reference_date} · ordening '{settings.ordering}'")
    if args.dry_run:
        print(usage_report(client.usage, dry_run=True))
        return 0

    metrics = result.to_dict()
    geojson = to_geojson(result)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / scenario.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "routes.geojson").write_text(json.dumps(geojson) + "\n")
    (out_dir / "map.html").write_text(render_map_html(result, geojson))

    print(compare_markdown([metrics]), end="")
    print()
    print("| Bus | Leerlingen | Vertrek | Rijtijd (min) | Km | Langste rit (min) |")
    print("|---|---|---|---|---|---|")
    for b in metrics["buses"]:
        print(
            f"| {b['bus_id']} | {b['students']}/{b['capacity']} | {b['departure']} | "
            f"{b['drive_min']} | {b['km']} | {b['max_ride_min']} |"
        )
    print(f"\n{usage_report(client.usage)}")
    print(f"Output: {out_dir}/metrics.json, routes.geojson, map.html")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    metrics = [json.loads(Path(p).read_text()) for p in args.metrics]
    md = compare_markdown(metrics)
    print(md, end="")
    if args.out:
        Path(args.out).write_text(md)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="busroutes", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate", help="reken één scenario door")
    ev.add_argument("scenario", type=Path, help="pad naar scenario.json")
    ev.add_argument(
        "--samples", type=Path, default=DEFAULT_SAMPLES, help="map met school/students/buses"
    )
    ev.add_argument("--out", type=Path, help="outputmap (default: out/<scenario-naam>)")
    ev.add_argument(
        "--traffic", choices=["historical", "live"], help="overschrijft BUSROUTES_TRAFFIC"
    )
    ev.add_argument(
        "--ordering",
        choices=["haversine", "matrix"],
        help="kostenmatrix voor 'auto'-volgorde; overschrijft BUSROUTES_ORDERING "
        "(default haversine, gratis; 'matrix' koopt TomTom-reistijden)",
    )
    ev.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="schooldag waarop departAt vastligt; overschrijft BUSROUTES_REFERENCE_DATE",
    )
    ev.add_argument(
        "--dry-run",
        action="store_true",
        help="niets ophalen, alleen tellen wat deze run aan TomTom-transacties zou kosten",
    )
    ev.add_argument("--no-cache", action="store_true", help="TomTom-cache negeren")
    ev.set_defaults(func=cmd_evaluate)

    cp = sub.add_parser("compare", help="vergelijk metrics.json-bestanden")
    cp.add_argument("metrics", nargs="+", help="metrics.json per scenario")
    cp.add_argument("--out", type=Path, help="schrijf de markdown-tabel ook naar dit bestand")
    cp.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ScenarioError, TomTomError) as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
