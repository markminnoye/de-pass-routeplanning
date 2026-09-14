#!/usr/bin/env python3
"""Generate the fictional test set in docs/samples/.

Deterministic (fixed seed): the same script always produces the same files, so
scenario results stay reproducible. Points are scattered around real village
centres in the region and then snapped to the nearest normal street with TomTom
reverse geocoding (otherwise routing snaps them to footpaths/field tracks and the
travel times become nonsense). Snapping is cached in .cache/tomtom, so rerunning
is free; it needs TOMTOM_API_KEY only the first time. No point is a real address
and there are no names.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from busroutes.config import DEFAULT_CACHE_DIR, ConfigError, load_key
from busroutes.models import Point
from busroutes.tomtom import TomTomClient

SEED = 20260914
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "samples"

SCHOOL = {
    "id": "school",
    "name": "de pass (Hoegaarden)",
    "lat": 50.77815986077964,
    "lon": 4.8959997390197705,
    "target_arrival": "08:20",
}

# zone -> (centre lat, centre lon, scatter radius in km, number of students)
ZONES: dict[str, tuple[float, float, float, int]] = {
    "hoegaarden-centrum": (50.7756, 4.8894, 0.9, 30),
    "meldert": (50.7622, 4.8836, 0.5, 10),
    "outgaarden": (50.7590, 4.9200, 0.5, 8),
    "hoksem": (50.7885, 4.9151, 0.4, 6),
    "jodoigne": (50.7240, 4.8690, 0.8, 6),
    "tienen": (50.8073, 4.9375, 1.3, 24),
    "kumtich": (50.8160, 4.8950, 0.5, 6),
    "boutersem": (50.8330, 4.8340, 0.7, 10),
    "bierbeek": (50.8280, 4.7600, 0.6, 6),
    "leuven": (50.8790, 4.7010, 1.5, 14),
    "landen": (50.7520, 5.0800, 0.9, 10),
    "linter": (50.8340, 5.0350, 0.6, 6),
    "zoutleeuw": (50.8330, 5.1050, 0.6, 4),
}

BUS_COUNT = 7
BUS_CAPACITY = 20

PICKUP_POINTS = {
    "pp-tienen-station": {"lat": 50.8085, "lon": 4.9245, "name": "Tienen station"},
    "pp-tienen-markt": {"lat": 50.8071, "lon": 4.9376, "name": "Tienen Grote Markt"},
    "pp-leuven-station": {"lat": 50.8813, "lon": 4.7156, "name": "Leuven station"},
}


def scatter(rng: random.Random, lat: float, lon: float, radius_km: float) -> tuple[float, float]:
    """Uniform random point inside a disc around (lat, lon)."""
    r = radius_km * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111.32
    dlon = (r * math.sin(theta)) / (111.32 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def snap(client: TomTomClient, lat: float, lon: float, label: str) -> tuple[float, float]:
    snapped = client.snap_to_street(Point(lat, lon))
    if snapped is None:
        print(f"waarschuwing: geen straat binnen 1 km van {label}; punt blijft ongewijzigd")
        return lat, lon
    return round(snapped.lat, 6), round(snapped.lon, 6)


def generate_students(client: TomTomClient) -> list[dict]:
    rng = random.Random(SEED)
    students = []
    for zone, (lat, lon, radius, count) in ZONES.items():
        for _ in range(count):
            sid = f"s{len(students) + 1:03d}"
            plat, plon = snap(client, *scatter(rng, lat, lon, radius), sid)
            students.append({"id": sid, "lat": plat, "lon": plon, "zone": zone})
    return students


def snapped_pickup_points(client: TomTomClient) -> dict[str, dict]:
    result = {}
    for pp_id, pp in PICKUP_POINTS.items():
        lat, lon = snap(client, pp["lat"], pp["lon"], pp_id)
        result[pp_id] = {**pp, "lat": lat, "lon": lon}
    return result


def generate_buses() -> list[dict]:
    return [
        {"id": f"bus{i}", "capacity": BUS_CAPACITY, "start": "school"}
        for i in range(1, BUS_COUNT + 1)
    ]


def by_zone(students: list[dict]) -> dict[str, list[str]]:
    zones: dict[str, list[str]] = {}
    for s in students:
        zones.setdefault(s["zone"], []).append(s["id"])
    return zones


def scenario_spreiding_gemengd(students: list[dict]) -> dict:
    """Negative reference: students dealt round-robin over the buses, zones mixed."""
    rng = random.Random(SEED + 1)
    ids = [s["id"] for s in students]
    rng.shuffle(ids)
    buses = [{"bus_id": f"bus{i + 1}", "stops": []} for i in range(BUS_COUNT)]
    for i, sid in enumerate(ids):
        buses[i % BUS_COUNT]["stops"].append(sid)
    return {
        "name": "spreiding-gemengd",
        "description": "Referentie zonder logica: leerlingen willekeurig over de bussen verdeeld, "
        "zones gemengd. Verwacht: lange individuele ritten.",
        "ordering": "auto",
        "buses": buses,
    }


def zone_clusters(z: dict[str, list[str]]) -> list[list[str]]:
    """Seven geographic clusters of at most 20 students each."""
    return [
        z["hoegaarden-centrum"][:20],
        z["hoegaarden-centrum"][20:] + z["meldert"],
        z["outgaarden"] + z["hoksem"] + z["jodoigne"],
        z["tienen"][:20],
        z["tienen"][20:] + z["kumtich"] + z["boutersem"],
        z["bierbeek"] + z["leuven"],
        z["landen"] + z["linter"] + z["zoutleeuw"],
    ]


def scenario_regiobus_per_zone(students: list[dict]) -> dict:
    clusters = zone_clusters(by_zone(students))
    return {
        "name": "regiobus-per-zone",
        "description": "Elke bus bedient één streek (bus6 = regiobus Leuven/Bierbeek, "
        "bus7 = Landen/Linter/Zoutleeuw). Ophalen aan huis.",
        "ordering": "auto",
        "buses": [
            {"bus_id": f"bus{i + 1}", "stops": cluster} for i, cluster in enumerate(clusters)
        ],
    }


def scenario_opstapplaatsen(students: list[dict], pickup_points: dict[str, dict]) -> dict:
    z = by_zone(students)
    clusters = zone_clusters(z)
    tienen = z["tienen"]
    leuven = z["leuven"]

    def pp(pp_id: str, riders: list[str]) -> dict:
        return {"id": pp_id, **pickup_points[pp_id], "students": riders}

    buses = [{"bus_id": f"bus{i + 1}", "stops": cluster} for i, cluster in enumerate(clusters)]
    # bus4: the first 20 Tienen students board at two fixed pickup points
    buses[3]["stops"] = [pp("pp-tienen-station", tienen[:10]), pp("pp-tienen-markt", tienen[10:20])]
    # bus6: Leuven students board at the station, Bierbeek stays door-to-door
    buses[5]["stops"] = z["bierbeek"] + [pp("pp-leuven-station", leuven)]
    return {
        "name": "opstapplaatsen",
        "description": "Zoals regiobus-per-zone, maar Tienen en Leuven via vaste opstapplaatsen "
        "(station/markt) in plaats van aan huis.",
        "ordering": "auto",
        "buses": buses,
    }


def dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        client = TomTomClient(load_key(), DEFAULT_CACHE_DIR)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    students = generate_students(client)
    pickup_points = snapped_pickup_points(client)
    dump(SAMPLES_DIR / "school.json", SCHOOL)
    dump(SAMPLES_DIR / "students.json", students)
    dump(SAMPLES_DIR / "buses.json", generate_buses())
    dump(SAMPLES_DIR / "pickup_points.json", [{"id": k, **v} for k, v in pickup_points.items()])
    for scenario in (
        scenario_spreiding_gemengd(students),
        scenario_regiobus_per_zone(students),
        scenario_opstapplaatsen(students, pickup_points),
    ):
        dump(SAMPLES_DIR / "scenarios" / f"{scenario['name']}.json", scenario)
    print(f"{len(students)} students, {BUS_COUNT} buses, 3 scenarios -> {SAMPLES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
