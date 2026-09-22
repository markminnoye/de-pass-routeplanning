"""In-memory school with geographic clusters, for assign-scale tests. No disk."""

from __future__ import annotations

import json
import math
import random
from datetime import time
from pathlib import Path

from busroutes.geo import haversine_m
from busroutes.models import Bus, Point, School, Student, load_scenario, scenario_to_dict
from busroutes.tomtom import _point_key
from tests.conftest import HandMatrixClient


def make_scale_world(n_stops: int, n_buses: int, seed: int = 0):
    """School in the centre, stops in `n_buses` clusters, full asymmetric matrix.

    Returns (school, students, buses, client, clusters). `clusters[b]` is the
    stop ids that belong together geographically.
    """
    if n_stops < n_buses:
        raise ValueError("need at least one stop per bus")
    rng = random.Random(seed)
    school_point = Point(50.78, 4.90)
    points = [school_point]
    students: dict[str, Student] = {}
    counts = [n_stops // n_buses] * n_buses
    for extra in range(n_stops % n_buses):
        counts[extra] += 1
    clusters: list[list[str]] = []
    sid_n = 1
    for bus_i, count in enumerate(counts):
        angle = 2 * math.pi * bus_i / n_buses
        centre_lat = 50.78 + 0.08 * math.cos(angle)
        centre_lon = 4.90 + 0.12 * math.sin(angle)
        ids: list[str] = []
        for _ in range(count):
            point = Point(
                centre_lat + rng.gauss(0, 0.004),
                centre_lon + rng.gauss(0, 0.006),
            )
            sid = f"s{sid_n:03d}"
            sid_n += 1
            points.append(point)
            students[sid] = Student(id=sid, point=point, zone=f"c{bus_i}")
            ids.append(sid)
        clusters.append(ids)
    n = len(points)
    seconds: dict[tuple[str, str], int] = {}
    keys = [_point_key(point) for point in points]
    for i in range(n):
        for j in range(n):
            if i == j:
                seconds[(keys[i], keys[j])] = 0
                continue
            base = haversine_m(points[i], points[j]) / 10.0
            factor = 1.05 if (i * 7 + j * 3) % 2 == 0 else 0.95
            bump = (i * 7 + j * 3) % 11
            seconds[(keys[i], keys[j])] = max(1, round(base * factor) + bump)
    capacity = math.ceil(n_stops / n_buses) + 2
    buses = {
        f"bus{i + 1}": Bus(id=f"bus{i + 1}", capacity=capacity, start=school_point)
        for i in range(n_buses)
    }
    school = School(
        id="school",
        name="scale",
        point=school_point,
        target_arrival=time(8, 30),
    )
    return school, students, buses, HandMatrixClient(seconds), clusters


def mixed_scenario(world):
    """Round-robin stops across buses, so each bus mixes several clusters."""
    school, students, buses, _client, clusters = world
    flat = [sid for ids in clusters for sid in ids]
    n_buses = len(buses)
    plans = []
    for i in range(n_buses):
        plans.append(
            {"bus_id": f"bus{i + 1}", "stops": [flat[k] for k in range(i, len(flat), n_buses)]}
        )
    return load_scenario(
        {"name": "mixed", "ordering": "given", "buses": plans},
        students,
        buses,
    )


def write_scale_pack(directory: Path, n_stops: int, n_buses: int, seed: int = 0) -> Path:
    """Dump make_scale_world as a data pack with a complete matrix, mixed scenario."""
    from tests.test_offline import write_origin_row

    world = make_scale_world(n_stops, n_buses, seed)
    school, students, buses, client, _clusters = world
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "school.json").write_text(
        json.dumps(
            {
                "id": school.id,
                "name": school.name,
                "lat": school.point.lat,
                "lon": school.point.lon,
                "target_arrival": school.target_arrival.strftime("%H:%M"),
            }
        )
    )
    (directory / "students.json").write_text(
        json.dumps(
            [
                {
                    "id": student.id,
                    "lat": student.point.lat,
                    "lon": student.point.lon,
                    "zone": student.zone,
                }
                for student in students.values()
            ]
        )
    )
    (directory / "buses.json").write_text(
        json.dumps(
            [{"id": bus.id, "capacity": bus.capacity, "start": "school"} for bus in buses.values()]
        )
    )
    scenario = mixed_scenario(world)
    (directory / "scenario.json").write_text(
        json.dumps(scenario_to_dict(scenario), indent=2) + "\n"
    )
    points = [school.point, *[student.point for student in students.values()]]
    cells = directory / "matrix"
    for origin in points:
        row = {_point_key(dest): client.matrix([origin], [dest])[0][0] for dest in points}
        write_origin_row(cells, origin, row)
    return directory
