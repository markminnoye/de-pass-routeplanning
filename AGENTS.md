### Project Setup: Routeplanning Schoolbussen "de pass"

**Doel:** AI-gedreven route-optimalisatie voor de 7 schoolbussen van "de pass" (Hoegaarden) — scenario's simuleren en vergelijken, met als kernvraag een zo kort mogelijke individuele rit per kind (niet de laagste vlootkost).

**Schaal:** 7 bussen × max. 30 kinderen/bus (aanname 14/09/2026), ±140 leerlingen totaal.

### Context Routing (Read Order)

1. **Vision / projectbrief:** `@docs/project-brief.md` — oorspronkelijke opdracht, scope, evaluatiecriteria per scenario.
2. **Architectuur & tooling-beslissingen:** `@docs/data-en-tooling-opties.md` — vergelijking van geodata-bronnen, VRP-solvers en visualisatie-opties, plus de genomen beslissingen (datum + rationale).
3. **Testdata:** `@docs/samples/` (fictieve leerlingpunten rond Hoegaarden + buscapaciteiten + voorbeeldscenario's; schema in `docs/samples/README.md`).
4. **Actief plan:** `@.agent/plans/INDEX.md`.

### Architectuur — drie lagen

1. **Geodata** (geocoding + verkeersbewuste reistijdmatrix) → TomTom via Python/REST (`busroutes/tomtom.py`: Matrix Routing v2 + `calculateRoute`, met disk-cache). De matrix staat in het datapakket (`BUSROUTES_DATA_DIR` / `--data`, default `docs/samples/`) en wordt één keer opgehaald. De scenario-evaluator-skill gebruikt de TomTom-connector niet: één CLI-commando per vraag (`skills/scenario-evaluator/SKILL.md`).
2. **Optimalisatie** (toewijzing kinderen→bus + volgorde per bus) → stdlib-solver in `busroutes optimize` (`--order` / `--assign`), doelfunctie = kortste individuele rittijd. Benchmark 23/09/2026: op één volledige matrix halen pyvroom en OR-Tools de rit per kind niet duidelijk beter; ze blijven buiten de plugin. Zie `@docs/solver-benchmark.md`. `--ordering haversine` blijft een padkost-heuristiek (lengte van de bus), niet die doelfunctie. Een klassieke TSP op buslengte kan de langste kinderrit verlengen; dat is geen defect in `optimize` (SR-68, `@docs/sr-68-ortools-objective.md`). Google Route Optimization optimaliseert op vlootkost en is geen ingebouwd per-passagier-objectief.
3. **Visualisatie** → Leaflet.js + OpenStreetMap.de-tiles (niet tile.openstreetmap.org, die 403 geeft op lokaal `file://`), gevoed met GeoJSON, als lokaal `map.html` per scenario, met een togglebare overlay van De Lijn / TEC / NMBS-haltes (Overpass). Een gepubliceerd Claude-artifact blokkeert elke externe afbeelding; `evaluate` bouwt daarom de tiles van de scenariobbox in als data-URI (cache `.cache/map-tiles/`, max. 32). Leaflet-JS blijft van cdnjs (dat mag het artifact wel). Andere zoomniveaus en de Esri-laag laden alleen in een gewone browser.

Deze lagen zijn complementair: laag 1 levert data, laag 2 lost het combinatorische toewijzingsprobleem op, laag 3 toont het resultaat. Een kaarten-API (TomTom/Google Maps) lost nooit laag 2 op.

### Scenario's die ondersteund moeten worden

- Regiobus die kinderen uit één streek verzamelt (bv. Leuven).
- Vaste opstapplaatsen voor zones met veel kinderen.
- Volledig geoptimaliseerde verdeling (`busroutes optimize --assign`; vaste bussen/stops mogen). Tot ongeveer 150 stops hoort dat binnen vijf minuten terug te zijn (`--max-seconds 300`). De voorbeeldmatrix dekt niet alle paren tussen bussen; zonder die paren stopt `--assign`.

Per scenario tonen: max. en gemiddelde reistijd/leerling, totale rijtijd, km, bezettingsgraad, aankomsttijden.

### Definition of Done (DoD)

1. `uv run ruff check . && uv run ruff format --check . && uv run pytest` groen (Python 3.13 via `uv`, config in `pyproject.toml`).
2. Typecheck (indien van toepassing).
3. Geen regressies in bestaande scenario-/testsets.
4. Scenario-output is reproduceerbaar (zelfde input → zelfde vergelijkingscijfers).

### Privacy

Thuisadressen van minderjarigen zijn gevoelige persoonsgegevens. Het datapakket bewaart coördinaten en willekeurige ids, geen adressen, en hoort niet in git en niet in de plugin. TomTom krijgt alleen anonieme coördinaten — geen adressen. Gebruik in ontwikkeling en demo's uitsluitend het fictieve voorbeeld in `docs/samples/` tot de school data levert (WP6). Zie `@docs/data-en-tooling-opties.md`, sectie "Aandachtspunt: privacy van kinderdata".

### Environment & Configuration

- **Zero Hardcoding**: geen production-fallback-URLs of API-keys hardcoden in code.
- **Centralized Config**: API-keys (TomTom, evt. Google) en config via environment variables / een centraal config-bestand, niet verspreid in de code.
- **Fail Fast**: ontbrekende of ongeldige config moet direct een duidelijke fout geven, niet stil falen.

### Plan Management

Plannen leven in `.agent/plans/` — de repo-kopie is canoniek (ook als een plan in Claude Code's planmodus ontstond: kopieer het volledig hierheen en werk het daar bij).
- **Index:** `.agent/plans/INDEX.md` (Status: ✅ / 🔄 / ⏳ / ⬜)
- **Nieuwe taak:** maak `YYYY-MM-DD-naam.md` en registreer in de index.
- **Handoff:** voeg `## Status: Paused` toe aan een actief plan met de huidige stand van zaken.

### Releases

De tekst op een GitHub Release staat in `docs/release-notes/vX.Y.Z.md`: Nederlands, voor de school, en alleen wat de gebruiker merkt. Een berekening die aangerekend wordt noem je TomTom. `CHANGELOG.md` is het technische logboek en hoort niet op de release. De release-job publiceert het notitiebestand; zonder dat bestand faalt de tag-check.

### Continuous Learning

Vraag amendementen aan `@docs/data-en-tooling-opties.md` (of dit bestand) bij nieuwe inzichten over API-limieten, kosten, of solver-gedrag die tijdens implementatie aan het licht komen.

### Volgende stappen

Zie het einde van `@docs/data-en-tooling-opties.md`. Open: echte leerlingdata (WP6, geblokkeerd). `optimize --assign` schaalt tot ongeveer 150 stops (22/09/2026).
