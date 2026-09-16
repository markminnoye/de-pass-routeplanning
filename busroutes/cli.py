"""Command line: `busroutes evaluate <scenario.json>` and `busroutes compare <metrics.json>...`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from busroutes.config import (
    DEFAULT_ENV_PATH,
    REPO_ROOT,
    ConfigError,
    load_settings,
    read_env_file,
    resolve_data_dir,
)
from busroutes.datapack import add_points, fetch_matrix, pack_status
from busroutes.evaluate import evaluate
from busroutes.models import ScenarioError, load_samples, load_scenario_file
from busroutes.offline import OfflineClient, OfflineError
from busroutes.overpass import load_transit_overlay
from busroutes.render import compare_markdown, render_map_html, to_geojson
from busroutes.tomtom import GeoClient, TomTomClient, TomTomError, usage_report

DEFAULT_OUT = REPO_ROOT / "out"


def cmd_evaluate(args: argparse.Namespace) -> int:
    if args.samples is not None:
        print("Waarschuwing: --samples is verouderd; gebruik --data.", file=sys.stderr)
    overrides: dict[str, object] = {}
    if args.data is not None or args.samples is not None:
        overrides["data_dir"] = resolve_data_dir(args.data, args.samples)
    if args.traffic:
        overrides["traffic"] = args.traffic
    if args.ordering:
        overrides["ordering"] = args.ordering
    if args.reference_date:
        overrides["reference_date"] = args.reference_date
    if args.no_cache:
        overrides["cache_dir"] = None
        print(
            "Let op: --no-cache negeert de cache, dus TomTom én Overpass worden opnieuw opgehaald.",
            file=sys.stderr,
        )
    settings = load_settings(require_key=not args.offline, **overrides)
    data_dir = settings.data_dir
    school, students, buses = load_samples(data_dir)
    scenario = load_scenario_file(args.scenario, students, buses)
    cells_dir = data_dir / "matrix"
    if args.offline:
        client: GeoClient = OfflineClient(cells_dir)
    else:
        client = TomTomClient(
            settings.api_key,
            settings.cache_dir,
            settings.traffic,
            dry_run=args.dry_run,
            cells_dir=cells_dir,
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
    transit, transit_warning = load_transit_overlay(geojson, settings.cache_dir)
    if transit_warning:
        print(
            f"Waarschuwing: OV-haltes niet geladen ({transit_warning}). Kaart zonder overlay.",
            file=sys.stderr,
        )
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "routes.geojson").write_text(json.dumps(geojson) + "\n")
    (out_dir / "transit.geojson").write_text(json.dumps(transit, ensure_ascii=False) + "\n")
    (out_dir / "map.html").write_text(render_map_html(result, geojson, transit_geojson=transit))

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
    print(f"Output: {out_dir}/metrics.json, routes.geojson, transit.geojson, map.html")
    return 0


def _warn_samples(args: argparse.Namespace) -> None:
    if getattr(args, "samples", None) is not None:
        print("Waarschuwing: --samples is verouderd; gebruik --data.", file=sys.stderr)


def _pack_dir(args: argparse.Namespace) -> Path:
    if args.data is not None or args.samples is not None:
        return resolve_data_dir(args.data, args.samples)
    env = {**read_env_file(DEFAULT_ENV_PATH), **os.environ}
    return resolve_data_dir(env=env)


def _data_overrides(args: argparse.Namespace) -> dict[str, object]:
    if args.data is not None or args.samples is not None:
        return {"data_dir": resolve_data_dir(args.data, args.samples)}
    return {}


def _add_data_dir_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", type=Path, help="datapakket (school/students/buses/matrix)")
    parser.add_argument(
        "--samples",
        type=Path,
        default=None,
        help="verouderd: alias van --data",
    )


def cmd_data_status(args: argparse.Namespace) -> int:
    _warn_samples(args)
    print(pack_status(_pack_dir(args)).format(), end="")
    return 0


def cmd_data_fetch_matrix(args: argparse.Namespace) -> int:
    _warn_samples(args)
    data_dir = _pack_dir(args)
    cells_dir = data_dir / "matrix"
    if args.dry_run:
        client: GeoClient = TomTomClient("", None, dry_run=True, cells_dir=cells_dir)
    else:
        settings = load_settings(**_data_overrides(args))
        client = TomTomClient(
            settings.api_key,
            settings.cache_dir,
            settings.traffic,
            cells_dir=cells_dir,
        )
    fetch_matrix(data_dir, client)
    print(usage_report(client.usage, dry_run=args.dry_run))
    return 0


def cmd_data_add_points(args: argparse.Namespace) -> int:
    _warn_samples(args)
    data_dir = _pack_dir(args)
    try:
        entries = json.loads(Path(args.json).read_text())
    except FileNotFoundError as exc:
        raise ScenarioError(f"{args.json}: ontbreekt") from exc
    except (OSError, ValueError) as exc:
        raise ScenarioError(f"{args.json}: ongeldig JSON") from exc
    if not isinstance(entries, list):
        raise ScenarioError(f"{args.json}: verwacht een JSON-lijst van punten")
    settings = load_settings(**_data_overrides(args))
    client = TomTomClient(
        settings.api_key,
        settings.cache_dir,
        settings.traffic,
        cells_dir=data_dir / "matrix",
    )
    add_points(data_dir, entries, client)
    print(usage_report(client.usage))
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
    ev.add_argument("--data", type=Path, help="datapakket (school/students/buses/matrix)")
    ev.add_argument(
        "--samples",
        type=Path,
        default=None,
        help="verouderd: alias van --data",
    )
    ev.add_argument("--out", type=Path, help="outputmap (default: out/<scenario-naam>)")
    ev.add_argument(
        "--traffic", choices=["historical", "live"], help="overschrijft BUSROUTES_TRAFFIC"
    )
    ev.add_argument(
        "--ordering",
        choices=["haversine", "matrix"],
        help="kostenmatrix voor 'auto'-volgorde; overschrijft BUSROUTES_ORDERING "
        "(default matrix = TomTom-reistijden; 'haversine' is gratis maar 4-13%% langere ritten)",
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
    ev.add_argument("--no-cache", action="store_true", help="TomTom- en Overpass-cache negeren")
    ev.add_argument(
        "--offline",
        action="store_true",
        help="reistijden uit de matrix, zonder TomTom-key",
    )
    ev.set_defaults(func=cmd_evaluate)

    cp = sub.add_parser("compare", help="vergelijk metrics.json-bestanden")
    cp.add_argument("metrics", nargs="+", help="metrics.json per scenario")
    cp.add_argument("--out", type=Path, help="schrijf de markdown-tabel ook naar dit bestand")
    cp.set_defaults(func=cmd_compare)

    data = sub.add_parser("data", help="inspecteer of vul een datapakket")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    st = data_sub.add_parser("status", help="tel punten en ontbrekende matrixparen")
    _add_data_dir_flags(st)
    st.set_defaults(func=cmd_data_status)
    fm = data_sub.add_parser("fetch-matrix", help="haal ontbrekende matrixparen op")
    _add_data_dir_flags(fm)
    fm.add_argument(
        "--dry-run",
        action="store_true",
        help="niets ophalen, alleen tellen wat deze run aan TomTom-transacties zou kosten",
    )
    fm.set_defaults(func=cmd_data_fetch_matrix)
    ap = data_sub.add_parser("add-points", help="voeg leerlingen of opstapplaatsen toe")
    ap.add_argument("json", type=Path, help="JSON-lijst met nieuwe punten")
    _add_data_dir_flags(ap)
    ap.set_defaults(func=cmd_data_add_points)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ScenarioError, TomTomError, OfflineError) as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
