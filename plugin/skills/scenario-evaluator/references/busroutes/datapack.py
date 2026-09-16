"""Datapakket-operaties: status, matrix vullen, punten toevoegen."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from busroutes.models import (
    DataPack,
    PickupPoint,
    Point,
    ScenarioError,
    Student,
    load_data_pack,
)
from busroutes.tomtom import (
    MATRIX_OPTIONS,
    _digest,
    _point_key,
    _read_json,
    _unique,
    _write_json,
    plan_blocks,
    plan_cost,
)


class MatrixClient(Protocol):
    def matrix(self, origins: list[Point], destinations: list[Point]) -> list[list[int]]: ...


class PackGeoClient(MatrixClient, Protocol):
    def snap_to_street(self, point: Point, radius_m: int = 1000) -> Point | None: ...


def pack_points(pack: DataPack) -> list[Point]:
    """Unique matrix points: school, students, pickups, non-school bus starts."""
    return _unique(
        [
            pack.school.point,
            *(student.point for student in pack.students.values()),
            *(pickup.point for pickup in pack.pickup_points.values()),
            *(bus.start for bus in pack.buses.values()),
        ]
    )


def _cells_path(cells_dir: Path, origin: Point) -> Path:
    return cells_dir / _digest(MATRIX_OPTIONS)[:16] / f"{_point_key(origin)}.json"


def _read_row(cells_dir: Path, origin: Point) -> dict:
    payload = _read_json(_cells_path(cells_dir, origin))
    return payload if isinstance(payload, dict) else {}


def _missing_gaps(points: list[Point], cells_dir: Path) -> dict[int, set[int]]:
    dest_keys = [_point_key(p) for p in points]
    missing: dict[int, set[int]] = {}
    for i, origin in enumerate(points):
        row = _read_row(cells_dir, origin)
        gaps = {j for j, key in enumerate(dest_keys) if key not in row}
        if gaps:
            missing[i] = gaps
    return missing


@dataclass(frozen=True)
class PackStatus:
    path: Path
    students: int
    pickup_points: int
    buses: int
    points: int
    present_pairs: int
    missing_pairs: int
    estimated_transactions: int

    def format(self) -> str:
        total = self.present_pairs + self.missing_pairs
        return (
            f"Datapakket: {self.path}\n"
            f"Leerlingen: {self.students}\n"
            f"Opstapplaatsen: {self.pickup_points}\n"
            f"Bussen: {self.buses}\n"
            f"Matrixpunten: {self.points}\n"
            f"Aanwezige paren: {self.present_pairs}/{total}\n"
            f"Ontbrekende paren: {self.missing_pairs}\n"
            f"Raming om te vervolledigen: {self.estimated_transactions} transacties\n"
        )


def pack_status(data_dir: Path) -> PackStatus:
    pack = load_data_pack(data_dir)
    points = pack_points(pack)
    gaps = _missing_gaps(points, Path(data_dir) / "matrix")
    missing = sum(len(g) for g in gaps.values())
    total = len(points) * len(points)
    return PackStatus(
        path=pack.path,
        students=len(pack.students),
        pickup_points=len(pack.pickup_points),
        buses=len(pack.buses),
        points=len(points),
        present_pairs=total - missing,
        missing_pairs=missing,
        estimated_transactions=plan_cost(plan_blocks(gaps)) if gaps else 0,
    )


def fetch_matrix(data_dir: Path, client: MatrixClient) -> None:
    pack = load_data_pack(data_dir)
    points = pack_points(pack)
    if points:
        client.matrix(points, points)


def _new_id(kind: str) -> str:
    raw = uuid.uuid4().hex
    return f"pp-{raw}" if kind == "pickup_point" else f"s{raw}"


def _student_payload(student: Student) -> dict:
    payload: dict = {"id": student.id, "lat": student.point.lat, "lon": student.point.lon}
    if student.zone is not None:
        payload["zone"] = student.zone
    return payload


def _pickup_payload(pickup: PickupPoint) -> dict:
    return {
        "id": pickup.id,
        "lat": pickup.point.lat,
        "lon": pickup.point.lon,
        "name": pickup.name,
    }


def _parse_point(entry: dict, where: str) -> Point:
    try:
        return Point(float(entry["lat"]), float(entry["lon"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioError(f"{where}: 'lat'/'lon' ontbreken of zijn ongeldig") from exc


def _snap(client: PackGeoClient, point: Point, where: str, warn: TextIO) -> Point:
    snapped = client.snap_to_street(point)
    if snapped is None:
        print(
            f"Waarschuwing: {where}: geen straat gevonden, oorspronkelijk punt gebruikt",
            file=warn,
        )
        return point
    return snapped


def _fill_new_rows_and_columns(
    client: PackGeoClient, existing: list[Point], new_points: list[Point]
) -> None:
    if not new_points:
        return
    all_points = _unique([*existing, *new_points])
    client.matrix(list(new_points), all_points)
    if existing:
        client.matrix(list(existing), list(new_points))


def add_points(
    data_dir: Path,
    entries: list[dict],
    client: PackGeoClient,
    *,
    warn: TextIO | None = None,
) -> None:
    if warn is None:
        warn = sys.stderr
    pack = load_data_pack(data_dir)
    existing_points = pack_points(pack)
    students = dict(pack.students)
    pickups = dict(pack.pickup_points)
    new_points: list[Point] = []
    for i, entry in enumerate(entries, start=1):
        kind = entry.get("kind")
        if kind not in ("student", "pickup_point"):
            raise ScenarioError(f"punt {i}: kind moet 'student' of 'pickup_point' zijn")
        ident = str(entry.get("id") or _new_id(kind))
        where = f"{kind} {ident}"
        point = _snap(client, _parse_point(entry, where), where, warn)
        if kind == "student":
            if ident in students:
                raise ScenarioError(f"students.json: dubbele leerling-id {ident}")
            students[ident] = Student(id=ident, point=point, zone=entry.get("zone"))
        else:
            if ident in pickups:
                raise ScenarioError(f"pickup_points.json: dubbele id {ident}")
            pickups[ident] = PickupPoint(
                id=ident, point=point, name=str(entry.get("name") or ident)
            )
        new_points.append(point)
    data_dir = Path(data_dir)
    _write_json(data_dir / "students.json", [_student_payload(s) for s in students.values()])
    pickup_path = data_dir / "pickup_points.json"
    if pickups or pickup_path.exists():
        _write_json(pickup_path, [_pickup_payload(p) for p in pickups.values()])
    _fill_new_rows_and_columns(client, existing_points, new_points)
