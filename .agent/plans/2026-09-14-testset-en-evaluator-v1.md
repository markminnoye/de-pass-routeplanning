---
title: Testset + scenario-evaluator v1
status: "🔄"
date: 2026-09-14
---

# Plan: testset + scenario-evaluator v1 (Claude-skill + Python)

## Context

De projectfundering staat er: [AGENTS.md](AGENTS.md), [docs/project-brief.md](docs/project-brief.md), [docs/data-en-tooling-opties.md](docs/data-en-tooling-opties.md), een TomTom Matrix-smoke-test ([scripts/verify_matrix_routing.py](scripts/verify_matrix_routing.py)) en een werkende `TOMTOM_API_KEY` in `.env` (smoke-test bevestigd OK door Mark). Maar:

- **Niets is gecommit** — de enige commit (`b45144e Initialize project`) is leeg; AGENTS.md, docs/, scripts/, .gitignore, .env.example zijn allemaal untracked.
- `docs/samples/` (testset) en `.agent/plans/` (planbeheer volgens AGENTS.md) bestaan nog niet.
- Stap 1 uit de actielijst ("TomTom-connector activeren") is de facto anders opgelost: rechtstreekse REST-call met eigen key. Dat staat nog niet in de docs.
- Er is nog geen Python-projectstructuur (geen pyproject, geen tests, geen linter). `uv` en `pytest` zijn beschikbaar, `ruff` en `ortools` niet. Python is 3.14 (OR-Tools-wheels lopen meestal achter → later pinnen op 3.12/3.13 via uv).

Beslissingen uit dit gesprek: vorm = **Claude-skill + Python-scripts**; eerste slice = **fictieve testset + evaluator v1** (manueel scenario doorrekenen via TomTom → metrics + Leaflet-kaart). OR-Tools komt in een volgend plan.

**TomTom-laag = hybride** (beslist 14/09/2026 na analyse van `tomtom-international/tomtom-mcp`, hosted op `https://mcp.tomtom.com/maps`, public preview):
- De officiële TomTom MCP-connector heeft 11 tools (geocode, reverse-geocode, fuzzy/poi/nearby search, routing, waypoint-routing met `departAt`/`traffic`/`computeBestOrder`, reachable-range, traffic, static-map, dynamic-map) maar **geen Matrix Routing**, stript standaard de routegeometrie (`response_detail: compact`), en laat alle data door de conversatiecontext lopen — ongeschikt als motor voor de batch-evaluator (7 routes × 140 kinderen, cache, reproduceerbaarheid).
- Officiële documentatie (bij te houden in de docs): [TomTom Maps MCP — overview](https://docs.tomtom.com/tomtom-maps-mcp/documentation/overview), met subpagina's [quick-setup](https://docs.tomtom.com/tomtom-maps-mcp/documentation/quick-setup), [tools](https://docs.tomtom.com/tomtom-maps-mcp/documentation/tools) en [Claude Desktop-integratie](https://docs.tomtom.com/tomtom-maps-mcp/documentation/integration-guides/claude-desktop). Authenticatie = API-key (dezelfde `TOMTOM_API_KEY`), remote endpoint aanbevolen, geen limieten/prijzen gedocumenteerd op de overview.
- → **MCP-connector** voor interactief verkennen (geocoding, snelle routechecks "Leuven → school om 7u30", kaartbeelden, scenario-ideeën aftoetsen); **Python/REST** (Matrix v2 + calculateRoute) voor de evaluator. Mark's voorkeur voor bestaande MCP-diensten boven eigen code blijft het uitgangspunt waar de tool het werk dekt.

## Stap 0 — Huishouden (klein, eerst)

1. `git add` + commit van de bestaande fundering (docs, AGENTS.md, scripts, .gitignore, .env.example). `.env` blijft buiten git (staat al in .gitignore).
2. **Plannen leven in de repo.** `.agent/plans/INDEX.md` aanmaken en dit plan **volledig** kopiëren naar `.agent/plans/2026-09-14-testset-en-evaluator-v1.md` (status 🔄). Vanaf dan is die repo-kopie de canonieke versie: voortgang, afwijkingen en een eventuele `## Status: Paused`-handoff worden dáár bijgehouden en meegecommit. Het bestand in `~/.claude/plans/` is enkel Claude Code's werkkopie van de planmodus en wordt niet verder onderhouden. Toekomstige plannen worden meteen als `.agent/plans/YYYY-MM-DD-naam.md` aangemaakt en in de index geregistreerd.
3. Amendement in [docs/data-en-tooling-opties.md](docs/data-en-tooling-opties.md): in de geodata-tabel de TomTom-rij aanvullen met de link naar de [MCP-documentatie](https://docs.tomtom.com/tomtom-maps-mcp/documentation/overview) (+ tools/quick-setup/Claude-Desktop-subpagina's en de GitHub-repo); sectie "Beslissingen": hybride TomTom-inzet — MCP-connector (toollijst, geen matrix, compact-trimming, hosted endpoint) voor verkennen; REST + eigen API-key voor de evaluator; Matrix Routing v2 smoke-test OK op 14/09/2026. Actielijst-stap 1 herformuleren: connector activeren (Mark, via claude.ai-connectorinstellingen of `claude mcp add` met `npx @tomtom-org/tomtom-mcp@latest` + `TOMTOM_API_KEY`) — dit kan ik niet zelf in deze sessie.
4. Python-project opzetten met `uv`: `pyproject.toml` (package `busroutes`, deps: geen runtime-deps nodig behalve stdlib voor v1 — `urllib` volstaat zoals in het smoke-script; dev-deps: `pytest`, `ruff`). DoD in AGENTS.md verwijst dan naar `ruff check`, `ruff format --check`, `pytest`.

## Stap 1 — Fictieve testset (`docs/samples/`)

Alles deterministisch gegenereerd (vaste seed) en gecommit, zodat scenario-output reproduceerbaar is en er nooit echte kinderadressen in de repo staan.

- `scripts/generate_testset.py` — genereert ±140 fictieve leerlingpunten rond echte dorpskernen in de regio (Hoegaarden-centrum, Meldert, Outgaarden, Hoksem, Tienen, Kumtich, Boutersem, Bierbeek, Leuven, Landen, Jodoigne, Linter/Zoutleeuw), met jitter rond de kern zodat zone-scenario's (Leuven-bus, opstapplaats Tienen) zinvol zijn. Enkel coördinaten + zone-label, **geen adressen en geen namen** (geocoding is pas nodig bij echte data en is een aparte, privacygevoelige stap).
- Output:
  - `docs/samples/school.json` — "de pass", coördinaten uit het smoke-script (50.77816, 4.89600), `target_arrival: "08:20"` (aanname; bel-tijd nog te bevestigen door de school).
  - `docs/samples/students.json` — `[{id, lat, lon, zone}]`, ±140 stuks.
  - `docs/samples/buses.json` — 7 bussen, `capacity: 20`, `start` = school (aanname: bus vertrekt aan de school; rittijd per kind is hier onafhankelijk van, totale km/rijtijd niet — instelbaar per bus).
  - `docs/samples/scenarios/` — drie voorbeeldscenario's in het formaat van stap 2: `baseline-zones.json` (indeling per zone), `regiobus-leuven.json`, `opstapplaatsen-tienen.json`.
  - `docs/samples/README.md` — schema + hoe te regenereren.

## Stap 2 — Evaluator v1 (Python-package `busroutes/`)

Doel: een **manueel/door de agent bedacht scenario** doorrekenen en de evaluatiecriteria uit de brief opleveren. Geen solver.

### Scenario-formaat (`scenarios/*.json`)

```json
{
  "name": "regiobus-leuven",
  "description": "Bus 3 haalt alle kinderen uit zone Leuven op",
  "ordering": "given" | "auto",
  "buses": [
    {"bus_id": "bus3", "stops": [
      "s017",                                  // thuisstop = leerling-id
      {"id": "pp-leuven-station", "lat": 50.88, "lon": 4.715, "students": ["s020","s021"]}  // vaste opstapplaats
    ]}
  ]
}
```
Een stop is dus altijd `locatie + lijst instappende leerlingen`; een thuisadres is een stop met één leerling. Dat dekt alle drie de scenario-types uit de brief met één datamodel.

### Modules

- `busroutes/config.py` — `.env`-loader + fail-fast op ontbrekende `TOMTOM_API_KEY` (verplaats `load_key()` uit [scripts/verify_matrix_routing.py](scripts/verify_matrix_routing.py) hierheen; script importeert het voortaan). Instelbaar: `departAt`-weekdag/uur, `traffic: historical|live` (default **historical** → reproduceerbaar; live is opt-in), dwell-tijd per stop (bv. 30 s + 10 s/kind).
- `busroutes/tomtom.py` — dunne client met twee calls, achter een `Protocol` zodat tests een fake kunnen injecteren:
  - `route(points, depart_at)` → **Routing API `calculateRoute`** met waypoints, per bus één call: geeft per leg tijd/afstand **én** de polyline-geometrie. Dit is de autoritatieve bron voor de metrics.
  - `matrix(points, depart_at)` → **Matrix Routing v2** (bestaat al in het smoke-script), enkel nodig voor `ordering: auto`. Sub-matrix per bus (~21×21 = 441 cellen) i.p.v. de volledige 141×141.
  - Disk-cache in `.cache/tomtom/` (sleutel = hash van request-body) zodat herhaalde runs geen quota vreten en identieke output geven. `.cache/` in .gitignore.
  - Limieten (cellen per sync-request, waypoints per calculateRoute) opzoeken in de TomTom-docs (context7) tijdens implementatie en noteren in data-en-tooling-opties.md.
- `busroutes/ordering.py` — alleen voor `ordering: auto`: eenvoudige heuristiek (nearest-neighbour vanaf het verste punt richting school + 2-opt) op de sub-matrix. Bewust simpel; OR-Tools vervangt dit later.
- `busroutes/evaluate.py` — kern:
  - Validatie: elke leerling exact één keer toegewezen, capaciteit ≤ 20, bus-ids bestaan → duidelijke fout, geen stille skip.
  - Terugrekenen vanaf `target_arrival`: aankomst school → pickup-tijd per stop → vertrektijd bus.
  - Metrics per leerling (rittijd instap→school), per bus (rijtijd, km, bezetting, vertrek/aankomst), per scenario (max/gemiddelde/mediaan rittijd, totale rijtijd, totale km, gemiddelde bezetting).
- `busroutes/render.py` — `routes.geojson` (per bus een LineString + stop-Points met properties) en `map.html`: Leaflet + OSM-tiles, één kleur per bus, popups met rittijd per leerling, metrics-tabel bovenaan.
- `busroutes/cli.py` — `busroutes evaluate <scenario.json> [--samples docs/samples] [--out out/<name>]` en `busroutes compare out/*/metrics.json` (vergelijkingstabel als markdown + `compare.html`).

Output per scenario in `out/<name>/`: `metrics.json`, `routes.geojson`, `map.html`. `out/` in .gitignore.

### Bekende beperking (nu al noteren)
Een Claude-artifact blokkeert externe afbeeldingen, dus OSM-tiles laden **niet** in een gepubliceerd artifact. v1 richt zich op het lokale `map.html` (openen in browser). Later mogelijk: tiles van de bbox op zoom ~11 vooraf ophalen en als data-URI inbedden (`--embed-tiles`) zodat de kaart wél als artifact werkt. AGENTS.md-regel "gepubliceerd als artifact/pagina" hierop nuanceren.

## Stap 3 — Claude-skill `.claude/skills/scenario-evaluator/SKILL.md`

Dunne laag bovenop de CLI (bouwen met de `superpowers:writing-skills`-skill):
- Wanneer gebruiken: "reken scenario X door", "vergelijk scenario's", "maak een Leuven-bus".
- Werkwijze voor de agent: scenario-json opstellen op basis van `docs/samples/students.json` (zones) → `busroutes evaluate` → metrics samenvatten in de tabel uit de brief (max/gem. rittijd, totale rijtijd, km, bezetting, aankomsttijden) → `map.html` aanbieden.
- Sectie "Verkennen met de TomTom MCP-connector": wanneer wél de connector gebruiken (geocode van een opstapplaats, `tomtom-routing` om een idee snel te checken, `tomtom-static-map` voor een kaartbeeld in het gesprek) en wanneer niet (nooit 7 routes via MCP doorrekenen als scenario-evaluatie — daarvoor de CLI). Vaste-opstapplaats-coördinaten die via de connector gevonden worden, gaan in het scenario-json.
- Verwijzingen naar schema in `docs/samples/README.md`, privacyregel uit AGENTS.md (enkel fictieve data).

## Werkwijze

- TDD (`superpowers:test-driven-development`): tests in `tests/` met een **fake TomTom-client** (opgenomen JSON-fixtures van één echte call), geen netwerk in de testsuite. Testen: validatie-fouten, terugrekening van tijden, metrics op een klein 2-bussen-voorbeeld, GeoJSON-structuur, ordering-heuristiek op een handmatrix.
- Eén echte end-to-end run tegen TomTom op de drie voorbeeldscenario's; resultaten (metrics.json) gecommit als referentie in `docs/samples/expected/` voor de regressiecheck uit de DoD.
- Commits per stap (0 → 1 → 2 → 3), geen attributie-regels.

## Verificatie

1. `uv run ruff check . && uv run ruff format --check . && uv run pytest` → groen.
2. `uv run python scripts/verify_matrix_routing.py` blijft werken na de refactor van `load_key`.
3. `uv run busroutes evaluate docs/samples/scenarios/regiobus-leuven.json` → `out/regiobus-leuven/{metrics.json,routes.geojson,map.html}`; map.html opent in de browser met 7 gekleurde routes eindigend aan de school; metrics bevatten alle criteria uit de brief.
4. Tweede identieke run (cache + historical traffic) → byte-identieke `metrics.json` (reproduceerbaarheid, DoD 4).
5. `busroutes compare out/*/metrics.json` toont de drie scenario's naast elkaar.
6. Skill-test: in een nieuwe sessie "reken het scenario regiobus-leuven door" → agent gebruikt de skill en levert de tabel + kaart.
7. Connector-test (zodra Mark hem geactiveerd heeft): `tomtom-routing` Leuven-station → school met `departAt` op een weekdag 7u30 geeft een plausibele tijd; vergelijk met de REST-waarde uit de evaluator voor dezelfde leg (zelfde orde van grootte — live vs. historical mag afwijken).

## Geheugen
Na goedkeuring opslaan:
- feedback-memory: Mark verkiest bestaande MCP-connectoren/diensten boven zelfgeschreven integratiecode waar die het werk dekken; eigen code enkel waar de connector tekortschiet (hier: matrix, batch, cache).
- reference-memory: TomTom Maps MCP-documentatie (overview/tools/quick-setup/Claude Desktop) + GitHub-repo `tomtom-international/tomtom-mcp` + endpoint `https://mcp.tomtom.com/maps`.

## Daarna (niet in dit plan)

- OR-Tools voor het "volledig geoptimaliseerde" scenario (doelfunctie: minimaliseer langste rittijd), zelfde datamodel en evaluator; Python pinnen op een versie met ortools-wheels.
- Tiles inbedden voor artifact-publicatie.
- Geocoding-stap + privacybeslissing zodra echte leerlingdata komt.
