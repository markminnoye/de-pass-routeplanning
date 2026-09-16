"""Data model: school, students, buses and scenarios (see docs/samples/README.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Literal

Ordering = Literal["given", "auto"]


class ScenarioError(ValueError):
    """A scenario or sample file violates the rules; message explains what and where."""


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class Student:
    id: str
    point: Point
    zone: str | None = None


@dataclass(frozen=True)
class Bus:
    id: str
    capacity: int
    start: Point


@dataclass(frozen=True)
class School:
    id: str
    name: str
    point: Point
    target_arrival: time


@dataclass(frozen=True)
class PickupPoint:
    id: str
    point: Point
    name: str


@dataclass
class DataPack:
    path: Path
    school: School
    students: dict[str, Student]
    buses: dict[str, Bus]
    pickup_points: dict[str, PickupPoint]


@dataclass(frozen=True)
class Stop:
    """A location where one or more students board."""

    id: str
    point: Point
    students: list[str]
    name: str | None = None

    @property
    def is_pickup_point(self) -> bool:
        return self.name is not None or len(self.students) != 1 or self.students[0] != self.id


@dataclass
class BusPlan:
    bus_id: str
    stops: list[Stop]
    ordering: Ordering = "auto"  # resolved: bus-level override, else the scenario's

    @property
    def student_ids(self) -> list[str]:
        return [sid for stop in self.stops for sid in stop.students]


@dataclass
class Scenario:
    name: str
    description: str
    ordering: Ordering
    buses: list[BusPlan] = field(default_factory=list)


def _point(d: dict, where: str) -> Point:
    try:
        return Point(float(d["lat"]), float(d["lon"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioError(f"{where}: 'lat'/'lon' ontbreken of zijn ongeldig") from exc


_PACK_LAYOUT = "school.json, students.json, buses.json, optioneel pickup_points.json"


def _read_pack_json(path: Path, *, required: bool) -> object | None:
    if not required and not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ScenarioError(f"{path}: ontbreekt. Verwachte layout: {_PACK_LAYOUT}") from exc
    except (OSError, ValueError) as exc:
        raise ScenarioError(f"{path}: ongeldig. Verwachte layout: {_PACK_LAYOUT}") from exc


def _as_object(raw: object, path: Path) -> dict:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{path}: ongeldig. Verwachte layout: {_PACK_LAYOUT}")
    return raw


def _as_list(raw: object, path: Path) -> list:
    if not isinstance(raw, list):
        raise ScenarioError(f"{path}: ongeldig. Verwachte layout: {_PACK_LAYOUT}")
    return raw


def _parse_pack(path: Path, parse):
    try:
        return parse()
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, ScenarioError):
            raise
        raise ScenarioError(f"{path}: ongeldig. Verwachte layout: {_PACK_LAYOUT}") from exc


def load_data_pack(data_dir: Path) -> DataPack:
    data_dir = Path(data_dir)
    school_path = data_dir / "school.json"
    school_d = _as_object(_read_pack_json(school_path, required=True), school_path)

    def _school() -> School:
        hh, mm = school_d["target_arrival"].split(":")
        return School(
            id=school_d["id"],
            name=school_d.get("name", school_d["id"]),
            point=_point(school_d, "school.json"),
            target_arrival=time(int(hh), int(mm)),
        )

    school = _parse_pack(school_path, _school)

    students_path = data_dir / "students.json"
    students_raw = _as_list(_read_pack_json(students_path, required=True), students_path)

    def _students() -> dict[str, Student]:
        out: dict[str, Student] = {}
        for s in students_raw:
            if s["id"] in out:
                raise ScenarioError(f"students.json: dubbele leerling-id {s['id']}")
            out[s["id"]] = Student(
                id=s["id"], point=_point(s, f"student {s['id']}"), zone=s.get("zone")
            )
        return out

    students = _parse_pack(students_path, _students)

    buses_path = data_dir / "buses.json"
    buses_raw = _as_list(_read_pack_json(buses_path, required=True), buses_path)

    def _buses() -> dict[str, Bus]:
        out: dict[str, Bus] = {}
        for b in buses_raw:
            start = b.get("start", "school")
            start_point = (
                school.point if start == "school" else _point(start, f"bus {b['id']} start")
            )
            out[b["id"]] = Bus(id=b["id"], capacity=int(b["capacity"]), start=start_point)
        return out

    buses = _parse_pack(buses_path, _buses)

    pickup_path = data_dir / "pickup_points.json"
    pickup_raw = _read_pack_json(pickup_path, required=False)
    pickup_points: dict[str, PickupPoint] = {}
    if pickup_raw is not None:
        pickup_list = _as_list(pickup_raw, pickup_path)

        def _pickups() -> dict[str, PickupPoint]:
            out: dict[str, PickupPoint] = {}
            for pp in pickup_list:
                pid = pp["id"]
                if pid in out:
                    raise ScenarioError(f"pickup_points.json: dubbele id {pid}")
                out[pid] = PickupPoint(
                    id=pid,
                    point=_point(pp, f"pickup_points.json {pid}"),
                    name=str(pp.get("name") or pid),
                )
            return out

        pickup_points = _parse_pack(pickup_path, _pickups)

    return DataPack(
        path=data_dir,
        school=school,
        students=students,
        buses=buses,
        pickup_points=pickup_points,
    )


def load_samples(samples_dir: Path) -> tuple[School, dict[str, Student], dict[str, Bus]]:
    pack = load_data_pack(samples_dir)
    return pack.school, pack.students, pack.buses


def _parse_stop(raw: str | dict, students: dict[str, Student], where: str) -> Stop:
    if isinstance(raw, str):
        student = students.get(raw)
        if student is None:
            raise ScenarioError(f"{where}: onbekende leerling '{raw}'")
        return Stop(id=raw, point=student.point, students=[raw])
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where}: stop moet een leerling-id of een opstapplaats-object zijn")
    riders = raw.get("students")
    if not isinstance(riders, list) or not riders:
        raise ScenarioError(f"{where}: opstapplaats '{raw.get('id')}' heeft geen 'students'")
    for sid in riders:
        if sid not in students:
            raise ScenarioError(f"{where}: onbekende leerling '{sid}'")
    return Stop(
        id=str(raw.get("id") or f"pp-{where}"),
        point=_point(raw, f"{where} opstapplaats {raw.get('id')}"),
        students=list(riders),
        name=raw.get("name") or str(raw.get("id")),
    )


def load_scenario(data: dict, students: dict[str, Student], buses: dict[str, Bus]) -> Scenario:
    """Build and validate a Scenario from its JSON form. Raises ScenarioError on any violation."""
    ordering = data.get("ordering", "auto")
    if ordering not in ("given", "auto"):
        raise ScenarioError(f"ordering moet 'given' of 'auto' zijn, niet '{ordering}'")

    plans: list[BusPlan] = []
    seen: dict[str, str] = {}
    for i, raw_bus in enumerate(data.get("buses", [])):
        bus_id = raw_bus.get("bus_id")
        if bus_id not in buses:
            raise ScenarioError(f"bus '{bus_id}' bestaat niet in buses.json")
        stops = [
            _parse_stop(raw, students, f"{bus_id} stop {j + 1}")
            for j, raw in enumerate(raw_bus.get("stops", []))
        ]
        bus_ordering = raw_bus.get("ordering", ordering)
        if bus_ordering not in ("given", "auto"):
            raise ScenarioError(
                f"{bus_id}: ordering moet 'given' of 'auto' zijn, niet '{bus_ordering}'"
            )
        plan = BusPlan(bus_id=bus_id, stops=stops, ordering=bus_ordering)
        for sid in plan.student_ids:
            if sid in seen:
                raise ScenarioError(f"leerling {sid} zit op {seen[sid]} én op {bus_id}")
            seen[sid] = bus_id
        if len(plan.student_ids) > buses[bus_id].capacity:
            raise ScenarioError(
                f"{bus_id}: {len(plan.student_ids)} leerlingen > capacity {buses[bus_id].capacity}"
            )
        if i and plan.bus_id in {p.bus_id for p in plans}:
            raise ScenarioError(f"bus '{bus_id}' komt twee keer voor")
        plans.append(plan)

    missing = sorted(set(students) - set(seen))
    if missing:
        raise ScenarioError(f"niet toegewezen: {', '.join(missing)}")

    return Scenario(
        name=data.get("name", "scenario"),
        description=data.get("description", ""),
        ordering=ordering,
        buses=plans,
    )


def load_scenario_file(path: Path, students: dict[str, Student], buses: dict[str, Bus]) -> Scenario:
    return load_scenario(json.loads(Path(path).read_text()), students, buses)
