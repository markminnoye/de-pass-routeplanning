### Project Setup: Routeplanning Schoolbussen "de pass"

**Doel:** AI-gedreven route-optimalisatie voor de 7 schoolbussen van "de pass" (Hoegaarden) — scenario's simuleren en vergelijken, met als kernvraag een zo kort mogelijke individuele rit per kind (niet de laagste vlootkost).

**Schaal:** 7 bussen × ±20 kinderen/bus (±140 leerlingen totaal).

### Context Routing (Read Order)

1. **Vision / projectbrief:** `@docs/project-brief.md` — oorspronkelijke opdracht, scope, evaluatiecriteria per scenario.
2. **Architectuur & tooling-beslissingen:** `@docs/data-en-tooling-opties.md` — vergelijking van geodata-bronnen, VRP-solvers en visualisatie-opties, plus de genomen beslissingen (datum + rationale).
3. **Testdata:** `@docs/samples/` (fictieve leerlingpunten rond Hoegaarden + buscapaciteiten + voorbeeldscenario's; schema in `docs/samples/README.md`).
4. **Actief plan:** `@.agent/plans/INDEX.md`.

### Architectuur — drie lagen

1. **Geodata** (geocoding + verkeersbewuste reistijdmatrix) → TomTom, **hybride**: de MCP-connector voor interactief verkennen (geocoden, snelle routecheck, kaartbeeld), Python/REST (`busroutes/tomtom.py`: Matrix Routing v2 + `calculateRoute`, met disk-cache) voor de batch-evaluatie. Nooit een volledig scenario (7 routes) via de connector doorrekenen.
2. **Optimalisatie** (toewijzing kinderen→bus + volgorde per bus) → OR-Tools, doelfunctie = kortste individuele rittijd. Zie `@docs/data-en-tooling-opties.md` voor waarom niet Google Route Optimization (die optimaliseert op vlootkost, geen ingebouwd per-passagier-objectief).
3. **Visualisatie** → Leaflet.js + OpenStreetMap-tiles, gevoed met GeoJSON, als lokaal `map.html` per scenario. Let op: een Claude-artifact blokkeert externe afbeeldingen, dus OSM-tiles laden daar niet — artifact-publicatie vergt ingebedde tiles (later).

Deze lagen zijn complementair: laag 1 levert data, laag 2 lost het combinatorische toewijzingsprobleem op, laag 3 toont het resultaat. Een kaarten-API (TomTom/Google Maps) lost nooit laag 2 op.

### Scenario's die ondersteund moeten worden

- Regiobus die kinderen uit één streek verzamelt (bv. Leuven).
- Vaste opstapplaatsen voor zones met veel kinderen.
- Volledig geoptimaliseerde verdeling (OR-Tools).

Per scenario tonen: max. en gemiddelde reistijd/leerling, totale rijtijd, km, bezettingsgraad, aankomsttijden.

### Definition of Done (DoD)

1. `uv run ruff check . && uv run ruff format --check . && uv run pytest` groen (Python 3.13 via `uv`, config in `pyproject.toml`).
2. Typecheck (indien van toepassing).
3. Geen regressies in bestaande scenario-/testsets.
4. Scenario-output is reproduceerbaar (zelfde input → zelfde vergelijkingscijfers).

### Privacy

Thuisadressen van minderjarigen zijn gevoelige persoonsgegevens. Cloud-geocoding (TomTom e.a.) stuurt adressen naar een externe dienst. Gebruik in ontwikkeling en demo's uitsluitend fictieve/steekproef-adressen tot er een bewuste beslissing is over hoe met echte leerlingdata wordt omgegaan (zie `@docs/data-en-tooling-opties.md`, sectie "Aandachtspunt: privacy van kinderdata").

### Environment & Configuration

- **Zero Hardcoding**: geen production-fallback-URLs of API-keys hardcoden in code.
- **Centralized Config**: API-keys (TomTom, evt. Google) en config via environment variables / een centraal config-bestand, niet verspreid in de code.
- **Fail Fast**: ontbrekende of ongeldige config moet direct een duidelijke fout geven, niet stil falen.

### Plan Management

Plannen leven in `.agent/plans/` — de repo-kopie is canoniek (ook als een plan in Claude Code's planmodus ontstond: kopieer het volledig hierheen en werk het daar bij).
- **Index:** `.agent/plans/INDEX.md` (Status: ✅ / 🔄 / ⏳ / ⬜)
- **Nieuwe taak:** maak `YYYY-MM-DD-naam.md` en registreer in de index.
- **Handoff:** voeg `## Status: Paused` toe aan een actief plan met de huidige stand van zaken.

### Continuous Learning

Vraag amendementen aan `@docs/data-en-tooling-opties.md` (of dit bestand) bij nieuwe inzichten over API-limieten, kosten, of solver-gedrag die tijdens implementatie aan het licht komen.

### Volgende stappen

Zie het einde van `@docs/data-en-tooling-opties.md` voor de actuele actielijst (TomTom-connector activeren, testset opbouwen, scenario-evaluator-skill bouwen, enz.).
