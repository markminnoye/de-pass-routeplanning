# Cowork-plugin packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Spec: `docs/superpowers/specs/2026-09-15-cowork-plugin-packaging-design.md`.

**Goal:** Build-script + gecommitte Claude-plugin (`plugin/`) + GitHub Actions zodat v0.1.0 als `.plugin` te downloaden is; de generieke skill meldt een nieuwere GitHub Release.

**Architecture:** Generieke skill in `skills/scenario-evaluator/` en `busroutes/` zijn de bron. `scripts/build_plugin.py` synchroniseert naar `plugin/skills/scenario-evaluator/`, stampt de versie uit `pyproject.toml` in `plugin.json`, en zipt naar `dist/de-pass-routeplanning.plugin`. Marketplace in de repowortel wijst naar `./plugin`. Repo-skill `.claude/skills/` blijft ongewijzigd.

**Tech Stack:** Python 3.13 stdlib (`tomllib`, `zipfile`, `pathlib`), pytest, ruff, GitHub Actions, uv.

## Global Constraints

- Pluginversie blijft **0.1.0** (geen bump).
- Geen runtime-deps; `TOMTOM_API_KEY` niet hardcoden; geen `.env` of `docs/samples/` in de zip.
- `marketplace.json` heeft geen `version`-veld; `plugin.json` wel (uit pyproject).
- `repository` in `plugin.json` weglaten tot er een publieke GitHub-remote is (versie-check dan stil).
- `dist/` in `.gitignore`. Ruff sluit `plugin/` uit (gegenereerde kopie).
- Functies in `scripts/build_plugin.py` nemen een `Paths` met `root: Path` zodat tests `tmp_path` gebruiken.

## Status: ✅ Klaar (15/09/2026)

Uitgevoerd: `scripts/build_plugin.py`, generieke skill, `plugin/`-boom, marketplace, CI (artefact op `main`, Release op tag `v*`). Versie blijft 0.1.0. Eerste school-download = tag `v0.1.0` zodra de repo publiek op GitHub hangt en `plugin.json` een `repository`-veld krijgt.


### Task 1: Semver-helpers

**Files:**
- Create: `scripts/build_plugin.py` (eerst alleen `parse_version` / `is_newer`)
- Test: `tests/test_build_plugin.py`

**Interfaces:**
- Produces: `parse_version(s: str) -> tuple[int, int, int]`; `is_newer(candidate: str, current: str) -> bool`

TDD: failing tests → implementatie → groen.

### Task 2: Sync, stamp, check, zip

**Files:**
- Modify: `scripts/build_plugin.py`
- Test: `tests/test_build_plugin.py`

**Interfaces:**
- `Paths(root: Path)` met properties `skill_src`, `busroutes_src`, `plugin`, `skill_dst`, `plugin_json`, `pyproject`, `default_zip`
- `read_project_version(paths: Paths) -> str`
- `sync(paths: Paths) -> None` — atomair, geen `__pycache__` / `.DS_Store`
- `stamp_version(paths: Paths) -> str` — alleen `version` in plugin.json
- `check(paths: Paths) -> None` — SystemExit/BuildError als stale of versie mismatch
- `zip_plugin(paths: Paths, out: Path | None = None) -> Path`
- `main(argv: list[str] | None = None) -> int` — `--check`, `--out`, `--verify-tag`

Tests op `tmp_path`-fixture (geen mutatie van de echte `plugin/` tot die bestaat).

### Task 3: Generieke skill + plugin-skeleton + marketplace

**Files:**
- Create: `skills/scenario-evaluator/SKILL.md` (bijlage + versie-check)
- Create: `skills/scenario-evaluator/references/data-schema.md`
- Create: `plugin/.claude-plugin/plugin.json`, `plugin/README.md`
- Create: `.claude-plugin/marketplace.json`
- Modify: `.gitignore` (`dist/`), `pyproject.toml` (`extend-exclude = ["plugin"]`)
- Modify: `.claude/skills/scenario-evaluator/SKILL.md` — geen versie-check toevoegen

Daarna `sync` + `--check` op de echte repo.

### Task 4: CI

**Files:**
- Create: `.github/workflows/ci.yml` — ruff + pytest op push/PR; zip-artefact op `main`; Release op tag `v*` na `--verify-tag`

### Task 5: Plan-index + DoD

**Files:**
- Modify: `.agent/plans/INDEX.md`
- Verify: `uv run ruff check . && uv run ruff format --check . && uv run pytest` en `python scripts/build_plugin.py --check`
