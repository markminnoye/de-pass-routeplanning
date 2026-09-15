"""Build-script for the Cowork plugin zip (no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_build_plugin():
    path = ROOT / "scripts" / "build_plugin.py"
    spec = importlib.util.spec_from_file_location("build_plugin", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_version_strips_v_prefix():
    bp = load_build_plugin()
    assert bp.parse_version("v0.1.0") == (0, 1, 0)
    assert bp.parse_version("0.1.0") == (0, 1, 0)


def test_is_newer_compares_semver():
    bp = load_build_plugin()
    assert bp.is_newer("0.2.0", "0.1.0") is True
    assert bp.is_newer("v0.1.0", "0.1.0") is False
    assert bp.is_newer("0.1.0", "0.2.0") is False


def test_parse_version_rejects_garbage():
    bp = load_build_plugin()
    with pytest.raises(ValueError):
        bp.parse_version("latest")


def _mini_repo(root: Path, *, version: str = "0.1.0") -> None:
    (root / "skills" / "scenario-evaluator" / "references").mkdir(parents=True)
    (root / "skills" / "scenario-evaluator" / "SKILL.md").write_text("# skill\n")
    schema = root / "skills" / "scenario-evaluator" / "references" / "data-schema.md"
    schema.write_text("# schema\n")
    (root / "busroutes").mkdir()
    (root / "busroutes" / "__init__.py").write_text('"""pkg"""\n')
    (root / "busroutes" / "__pycache__").mkdir()
    (root / "busroutes" / "__pycache__" / "x.pyc").write_bytes(b"nope")
    (root / "plugin" / ".claude-plugin").mkdir(parents=True)
    (root / "plugin" / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "de-pass-routeplanning", "version": "0.0.0", "author": {"name": "Mark"}}\n'
    )
    (root / "plugin" / "README.md").write_text("# readme\n")
    (root / "pyproject.toml").write_text(f'[project]\nname = "busroutes"\nversion = "{version}"\n')


def test_sync_copies_skill_and_busroutes_skips_pycache(tmp_path: Path):
    _mini_repo(tmp_path)
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    bp.sync(paths)
    dst = tmp_path / "plugin" / "skills" / "scenario-evaluator"
    assert (dst / "SKILL.md").read_text() == "# skill\n"
    assert (dst / "references" / "data-schema.md").read_text() == "# schema\n"
    assert (dst / "references" / "busroutes" / "__init__.py").read_text() == '"""pkg"""\n'
    assert not (dst / "references" / "busroutes" / "__pycache__").exists()
    assert (tmp_path / "plugin" / "README.md").read_text() == "# readme\n"


def test_stamp_version_writes_pyproject_version_only(tmp_path: Path):
    _mini_repo(tmp_path, version="0.1.0")
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    assert bp.stamp_version(paths) == "0.1.0"
    data = json.loads((tmp_path / "plugin" / ".claude-plugin" / "plugin.json").read_text())
    assert data["version"] == "0.1.0"
    assert data["name"] == "de-pass-routeplanning"


def test_check_passes_after_sync_and_stamp(tmp_path: Path):
    _mini_repo(tmp_path)
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    bp.sync(paths)
    bp.stamp_version(paths)
    bp.check(paths)


def test_check_fails_when_skill_stale(tmp_path: Path):
    _mini_repo(tmp_path)
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    bp.sync(paths)
    bp.stamp_version(paths)
    (tmp_path / "skills" / "scenario-evaluator" / "SKILL.md").write_text("# changed\n")
    with pytest.raises(bp.BuildError, match="stale"):
        bp.check(paths)


def test_check_fails_when_plugin_json_version_differs(tmp_path: Path):
    _mini_repo(tmp_path)
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    bp.sync(paths)
    bp.stamp_version(paths)
    (tmp_path / "plugin" / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "de-pass-routeplanning", "version": "9.9.9"}\n'
    )
    with pytest.raises(bp.BuildError, match="version"):
        bp.check(paths)


def test_zip_contains_plugin_layout_not_samples(tmp_path: Path):
    _mini_repo(tmp_path)
    (tmp_path / "docs" / "samples").mkdir(parents=True)
    (tmp_path / "docs" / "samples" / "students.json").write_text("[]\n")
    (tmp_path / ".env").write_text("TOMTOM_API_KEY=secret\n")
    bp = load_build_plugin()
    paths = bp.Paths(tmp_path)
    bp.sync(paths)
    bp.stamp_version(paths)
    zpath = bp.zip_plugin(paths)
    assert zpath == tmp_path / "dist" / "de-pass-routeplanning.plugin"
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    assert ".claude-plugin/plugin.json" in names
    assert "skills/scenario-evaluator/SKILL.md" in names
    assert "skills/scenario-evaluator/references/busroutes/__init__.py" in names
    assert "README.md" in names
    assert not any("students.json" in n for n in names)
    assert not any(n.endswith(".env") or "/.env" in n for n in names)
    assert not any("__pycache__" in n for n in names)


def test_main_verify_tag_matches_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _mini_repo(tmp_path)
    bp = load_build_plugin()
    monkeypatch.setattr(bp, "REPO_ROOT", tmp_path)
    assert bp.main(["--verify-tag", "v0.1.0"]) == 0
    assert bp.main(["--verify-tag", "v0.2.0"]) == 1


def test_plugin_name_is_kebab_case():
    bp = load_build_plugin()
    assert bp.is_kebab_case("de-pass-routeplanning")
    assert not bp.is_kebab_case("De pass")


def test_marketplace_points_at_plugin_without_version():
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = data["plugins"][0]
    assert entry["source"] == "./plugin"
    assert "version" not in entry
    assert "version" not in data


def test_plugin_json_name_and_version():
    bp = load_build_plugin()
    data = json.loads((ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text())
    assert bp.is_kebab_case(data["name"])
    assert data["version"] == bp.read_project_version(bp.Paths(ROOT))
    assert "repository" not in data


def test_generic_skill_has_version_check_repo_skill_does_not():
    generic = (ROOT / "skills" / "scenario-evaluator" / "SKILL.md").read_text()
    repo = (ROOT / ".claude" / "skills" / "scenario-evaluator" / "SKILL.md").read_text()
    assert "releases/latest" in generic
    assert "releases/latest" not in repo


def test_check_passes_on_this_repo():
    bp = load_build_plugin()
    bp.check(bp.Paths(ROOT))
