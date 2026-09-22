# Cowork-plugin: build, GitHub-distributie en versie-melding

Datum: 2026-09-15
Status: goedgekeurd ontwerp (brainstorming)
Versie van de plugin: **0.1.0** (geen bump voor dit werk)

## Probleem

De scenario-evaluator bestaat als Python-package in deze repo en als Claude Code-skill (`.claude/skills/scenario-evaluator/`). Daarnaast is er een handmatig gebouwde Claude Cowork-plugin (`.plugin`-zip) die schoolgebruikers in Cowork installeren. Die zip wordt niet automatisch gebouwd, niet verspreid, en merkt geen nieuwere versie.

Doel: dezelfde evaluator als downloadbare Cowork-plugin publiceren via GitHub, met een build-script, CI, en een versie-check die een update **meldt** (niet zelf installeert). ChatGPT/Mistral later; de skill-kern is daarop voorbereid.

## Beslissingen

| Vraag | Keuze |
|---|---|
| Doelgroep | School (Cowork) én ontwikkelaar (Claude Code) |
| Skill-vorm | Generieke kern + Claude-wrapper nu; andere runtimes later |
| Cowork-update | Melden + downloadlink; gebruiker herinstalleert |
| GitHub | Deze repo, publiek: Releases voor Cowork, `marketplace.json` voor Claude Code |
| Wanneer een school-versie | Alleen git-tags. Elke `main`-push bouwt een test-artefact |
| Plugin in git | Ja: `plugin/`-boom, script synchroniseert en zipt |
| Semver nu | Blijft `0.1.0`; eerste Release is `v0.1.0` |

## Architectuur

Drie lagen, één repo:

1. **Bronnen (één keer onderhouden)**
   - `busroutes/` — evaluator (stdlib, geen runtime-deps).
   - `skills/scenario-evaluator/` — generieke skill: wanneer gebruiken, scenario-JSON, `python3 -m busroutes.cli`, schema, privacy, versie-check. Geen `uv`, geen fictieve testset.
   - `.claude/skills/scenario-evaluator/` — **repo-skill**, ongewijzigd in rol: `uv run`, `docs/samples/`, geen echte adressen. Geen GitHub-versie-check (werkt vanaf git).

2. **Claude-verpakking (gecommit)**
   - `plugin/` — Cowork/Code-plugin, zelfde boom als de bestaande bijlage:
     - `.claude-plugin/plugin.json`
     - `README.md` (school: installatie, TomTom-sleutel, privacy)
     - `skills/scenario-evaluator/` ← sync van de generieke skill + `references/busroutes/`
   - `.claude-plugin/marketplace.json` in de **repowortel**, `source`: `./plugin`.

3. **Build en publicatie**
   - `scripts/build_plugin.py` — sync, versie-stamp, zip.
   - CI: tests + zip als workflow-artefact op `main`; GitHub Release alleen op tag `vX.Y.Z`.

Claude Code installeert via marketplace `owner/repo`. Cowork installeert het `.plugin`-bestand van Releases. Cowork’s eigen plugin-update-UI is onbetrouwbaar; we steunen daar niet op.

Toekomstige ChatGPT/Mistral-wrappers lezen dezelfde generieke skill + `busroutes/`; ze horen niet in deze implementatie.

## Componenten

### `scripts/build_plugin.py`

Verantwoordelijkheid: `plugin/` in sync houden met de bronnen en een installatiebare zip maken.

- **Sync** — vervang alleen `plugin/skills/scenario-evaluator/` (skill, `references/data-schema.md`, `references/busroutes/`). Laat `plugin/.claude-plugin/plugin.json` en `plugin/README.md` staan; stamp raakt enkel het `version`-veld. Geen testdata, geen `.env`, geen `docs/samples/`, geen `__pycache__`.
- **Stamp** — lees `version` uit `pyproject.toml`, schrijf die naar `plugin/.claude-plugin/plugin.json`. `marketplace.json` heeft **geen** eigen `version` (Claude Code leest `plugin.json`; dubbele velden lopen uiteen).
- **Zip** — inhoud van `plugin/` → `dist/de-pass-routeplanning.plugin` (`dist/` in `.gitignore`). Bestandsnaam **zonder** versie, zodat  
  `https://github.com/<owner>/<repo>/releases/latest/download/de-pass-routeplanning.plugin`  
  stabiel blijft. Sluit `.DS_Store` uit. Optioneel argument `--out <pad>` overschrijft de bestemming (CI gebruikt dat om het artefact te publiceren).
- **`--check`** — geen schrijven: exit 0 als `plugin/skills/scenario-evaluator/` en het `version`-veld in `plugin.json` exact overeenkomen met een verse sync+stamp; anders exit ≠ 0.

Atomaire sync: schrijf naar een temp-map, vervang `plugin/skills/scenario-evaluator/` pas als de kopie klaar is. Ontbrekende bron of onleesbare `pyproject.toml` → exit ≠ 0, één duidelijke regel op stderr.

### Manifesten

`plugin/.claude-plugin/plugin.json`:

- `name`: `de-pass-routeplanning` (kebab-case)
- `version`: uit `pyproject.toml` (nu `0.1.0`)
- `description`, `author` zoals de bijlage
- `repository` (en optioneel `homepage`): publieke GitHub-URL, nodig voor de versie-check. Ontbreekt het veld (repo nog niet op GitHub) → check is stil, geen fout.

`.claude-plugin/marketplace.json` in de repowortel: marketplace-naam `de-pass-routeplanning`, owner Mark Minnoye, één plugin-entry `source: "./plugin"`.

### Generieke skill

Nieuwe map `skills/scenario-evaluator/`, inhoud gebaseerd op de Cowork-bijlage (werkmap, `python3 -m busroutes.cli`, gebruiker levert schooldata, schema in `references/data-schema.md`), plus de versie-check hieronder. De korte TomTom-connector-tabel uit dit ontwerp is op 22/09/2026 (WP5) uit de skill gehaald; de CLI-tabel is de enige weg.

### Repo-skill

`.claude/skills/scenario-evaluator/SKILL.md` blijft de ontwikkelskill. Niet vervangen door de generieke tekst.

## Versie-check (Cowork)

In de generieke `SKILL.md`, verplicht aan het begin van een sessie waarin de evaluator speelt, en op verzoek (“welke versie?”, “is er een update?”). Eén check per sessie.

1. Lees lokale versie uit `plugin.json` (in deze repo: `pyproject.toml`).
2. GET `https://api.github.com/repos/<owner>/<repo>/releases/latest` — owner/repo uit het `repository`-veld.
3. Vergelijk semver: tag `v0.1.0` = `0.1.0`.
4. Release **nieuwere** → één alinea: nieuwe versie, download-URL hierboven, instructie plugin in Cowork verwijderen en het nieuwe bestand installeren. Daarna pas het scenario.
5. Gelijk, of nog geen Release → niets zeggen, doorwerken.

Fouten (geen netwerk, 404, GitHub down, ontbrekend `repository`): **stil doorgaan**. Niet blokkeren, niet gissen. Pre-releases en drafts tellen niet (`/releases/latest` slaat ze over).

Claude overschrijft de geïnstalleerde plugin niet, pakt de zip niet uit over de skill-map, en vraagt niet bij elke follow-up opnieuw.

Er komt **geen** extra Python-tool voor deze check; het is skill-instructie. Pytest test de GitHub-API niet (geen netwerk).

## Publicatie

**Push naar `main`:** bestaande DoD (`ruff check`, `ruff format --check`, `pytest`, inclusief `--check` van de plugin-build). Daarna zip als GitHub Actions-artefact van de run. Geen Release, geen school-melding.

**Tag `vX.Y.Z`:** tag zonder `v` moet gelijk zijn aan `pyproject.toml` `version`. Mismatch → job faalt, geen Release. Match → GitHub Release met asset `de-pass-routeplanning.plugin`. Dat is wat de skill als “laatste versie” ziet.

Eerste officiële download: tag `v0.1.0` nadat `plugin/` in git staat en de repo publiek op GitHub hangt. Het aanmaken van die GitHub-remote is een handmatige stap (de Cursor-origin blijft tot die tijd de ontwikkelremote).

Claude Code-updates: `/plugin marketplace update` + plugin-update. Onafhankelijk van de Cowork-melding.

## Testen

Bestaande evaluator-tests blijven. Nieuw:

- `--check` groen op een verse sync; rood als `busroutes/` of de generieke skill wijzigt zonder sync, of als `plugin.json` een andere versie heeft dan `pyproject.toml`.
- Zip bevat `.claude-plugin/plugin.json`, `skills/scenario-evaluator/SKILL.md`, `references/busroutes/`, `README.md`. Zip bevat geen `.env`, `docs/samples/`, `.cache/`, `tests/`.
- Semver-functies in `scripts/build_plugin.py` (`parse_version`, `is_newer`): `v0.1.0` → `0.1.0`; `0.2.0` is nieuwere dan `0.1.0`. Pytest importeert die functies. De skill beschrijft dezelfde regel in prose; geen GitHub-API in tests.
- `plugin.json` `name` is kebab-case; `marketplace.json` wijst naar `./plugin`.

CI op tags: geen Release bij versie-mismatch.

## Buiten scope

- Cowork auto-update via Browse Plugins / Personal-tab
- ChatGPT-, Mistral- of andere runtime-packages
- Versiebump naar 0.2.0
- Live GitHub-API in de testsuite
- Wijziging van de evaluator-doelfunctie of OR-Tools
- Echte leerlingdata in de plugin (privacy: gebruiker levert data in de Cowork-werkmap)

## Definition of Done

1. `uv run ruff check . && uv run ruff format --check . && uv run pytest` groen.
2. `python scripts/build_plugin.py --check` groen na een sync; `python scripts/build_plugin.py` schrijft `dist/de-pass-routeplanning.plugin` met dezelfde structuur als de bijlage.
3. Generieke skill bevat de versie-check-instructie; repo-skill niet.
4. Workflow: artefact op `main`; Release-job gedocumenteerd/aanwezig voor tags (eerste echte Release = `v0.1.0` wanneer de GitHub-remote er is).
5. Reproduceerbaar: zelfde bron → zelfde `plugin/`-inhoud (modulo zip-metadata).
