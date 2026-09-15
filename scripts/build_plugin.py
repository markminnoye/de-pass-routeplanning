"""Assemble the Cowork plugin tree and zip it. No network, no API keys."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "de-pass-routeplanning"
_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BuildError(RuntimeError):
    pass


def parse_version(s: str) -> tuple[int, int, int]:
    raw = s.strip()
    if raw.startswith("v") or raw.startswith("V"):
        raw = raw[1:]
    parts = raw.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"ongeldige semver: {s}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def is_kebab_case(name: str) -> bool:
    return bool(_KEBAB.fullmatch(name))


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def skill_src(self) -> Path:
        return self.root / "skills" / "scenario-evaluator"

    @property
    def busroutes_src(self) -> Path:
        return self.root / "busroutes"

    @property
    def plugin(self) -> Path:
        return self.root / "plugin"

    @property
    def skill_dst(self) -> Path:
        return self.plugin / "skills" / "scenario-evaluator"

    @property
    def plugin_json(self) -> Path:
        return self.plugin / ".claude-plugin" / "plugin.json"

    @property
    def pyproject(self) -> Path:
        return self.root / "pyproject.toml"

    @property
    def default_zip(self) -> Path:
        return self.root / "dist" / f"{PLUGIN_NAME}.zip"


def read_project_version(paths: Paths) -> str:
    if not paths.pyproject.is_file():
        raise BuildError(f"ontbreekt: {paths.pyproject}")
    with paths.pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    try:
        version = data["project"]["version"]
    except KeyError as exc:
        raise BuildError("pyproject.toml heeft geen project.version") from exc
    parse_version(version)
    return version


def _skip(path: Path) -> bool:
    return path.name == ".DS_Store" or "__pycache__" in path.parts or path.suffix == ".pyc"


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise BuildError(f"ontbreekt: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if _skip(item):
            continue
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def _file_tree(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if path.is_dir() or _skip(path):
            continue
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def expected_skill_tree(paths: Paths) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="plugin-expected-") as tmp:
        tmp_path = Path(tmp)
        _copy_tree(paths.skill_src, tmp_path)
        _copy_tree(paths.busroutes_src, tmp_path / "references" / "busroutes")
        return _file_tree(tmp_path)


def sync(paths: Paths) -> None:
    with tempfile.TemporaryDirectory(prefix="plugin-skill-") as tmp:
        tmp_path = Path(tmp)
        _copy_tree(paths.skill_src, tmp_path)
        _copy_tree(paths.busroutes_src, tmp_path / "references" / "busroutes")
        dest = paths.skill_dst
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(tmp_path, dest)


def stamp_version(paths: Paths) -> str:
    version = read_project_version(paths)
    if not paths.plugin_json.is_file():
        raise BuildError(f"ontbreekt: {paths.plugin_json}")
    data = json.loads(paths.plugin_json.read_text())
    data["version"] = version
    paths.plugin_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return version


def check(paths: Paths) -> None:
    expected = expected_skill_tree(paths)
    actual = _file_tree(paths.skill_dst)
    if expected != actual:
        raise BuildError("plugin/skills/scenario-evaluator is stale; run scripts/build_plugin.py")
    if not paths.plugin_json.is_file():
        raise BuildError(f"ontbreekt: {paths.plugin_json}")
    data = json.loads(paths.plugin_json.read_text())
    name = data.get("name", "")
    if not is_kebab_case(name):
        raise BuildError(f"plugin.json name is niet kebab-case: {name}")
    want = read_project_version(paths)
    got = data.get("version")
    if got != want:
        raise BuildError(f"plugin.json version {got!r} wijkt af van pyproject {want!r}")


def zip_plugin(paths: Paths, out: Path | None = None) -> Path:
    dest = out or paths.default_zip
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths.plugin.rglob("*"):
            if path.is_dir() or _skip(path):
                continue
            zf.write(path, path.relative_to(paths.plugin).as_posix())
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the de-pass-routeplanning Cowork plugin.")
    parser.add_argument("--check", action="store_true", help="fail if plugin/ is stale")
    parser.add_argument(
        "--out",
        type=Path,
        help="zip destination (default: dist/de-pass-routeplanning.zip)",
    )
    parser.add_argument(
        "--verify-tag",
        metavar="TAG",
        help="exit 0 iff TAG matches pyproject version",
    )
    args = parser.parse_args(argv)
    paths = Paths(REPO_ROOT)
    try:
        if args.verify_tag is not None:
            version = read_project_version(paths)
            if parse_version(args.verify_tag) != parse_version(version):
                print(
                    f"tag {args.verify_tag} wijkt af van pyproject version {version}",
                    file=sys.stderr,
                )
                return 1
            return 0
        if args.check:
            check(paths)
            return 0
        sync(paths)
        stamp_version(paths)
        zip_plugin(paths, args.out)
        return 0
    except (BuildError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"build_plugin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
