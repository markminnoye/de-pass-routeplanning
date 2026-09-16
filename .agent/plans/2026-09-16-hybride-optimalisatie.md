# Plan: hybride optimalisatie — datapakket, offline-modus, stdlib-solver, skill-herwerking

Status: 🔄 actief — WP0 ✅, WP1 ✅ (spec), WP2 ✅ (16/09/2026, branch `wp2-datapakket-offline`). Volgende: WP3 solver.

## Context

De evaluator v1 en de Cowork-plugin staan (alle plannen in `.agent/plans/INDEX.md` ✅,
alles gecommit; laatste commit: matrix weer default-ordening). Het enige open spoor is
het **volledig geoptimaliseerde scenario** (laag 2). Uit de analyse van 15–16/09/2026:

- De **TomTom-matrix** (reistijd per punt-paar, tijdsonafhankelijk, cache per paar in
  `.cache/tomtom/cells/`) is het enige dure stuk: ±8.000 transacties voor 141 punten,
  **één keer**. Een nieuw punt kost ±280 transacties (rij + kolom). Daarna kan een solver
  onbeperkt draaien zonder TomTom.
- `calculateRoute` (7 calls per scenario, met wegtekening en 07:20-verkeersprofiel) is
  niet vooraf te berekenen (hangt van de volgorde af) maar is goedkoop.
- De Cowork-plugin kan geen bibliotheken installeren (`busroutes/` is stdlib-only). Met
  een opgeslagen matrix is een **eigen stdlib-solver** (local search, 7 bussen × 140
  stops) haalbaar → geen OR-Tools (75 MB), geen gehoste VROOM. pyvroom / de
  VROOM-demoserver dienen enkel als **benchmark** in de repo.
- De agent die de skill gebruikt moet niet hoeven te kiezen tussen diensten: de skill
  krijgt een **vaste beslissingstabel** (één commando per vraag), en de sectie over de
  TomTom-MCP-connector verdwijnt.
- **Privacy**: TomTom rekent alleen met coördinaten; adressen zijn enkel nodig voor de
  eenmalige geocoding en worden daarna weggegooid. Datapakket = willekeurige ids, geen
  namen, punten op de straat gesnapt, en **nooit in de publieke repo/plugin** (apart,
  school-specifiek bestand naast de plugin). Mark: "privacy is geen probleem als we
  anonimiseren" — akkoord 16/09/2026.

Doel: een skill die met een vooraf verzameld datapakket (school, bussen, leerlingpunten,
opstapplaatsen, matrix) scenario's laat bouwen, gratis offline doorrekenen, optimaliseren
(volgorde per bus én verdeling), en enkel voor de definitieve kaart/cijfers TomTom aanspreekt.

## Beslissingstabel voor de agent (kern van de skill, WP5)

| Gebruiker wil | Commando | TomTom-key nodig |
|---|---|---|
| Scenario bedenken/aanpassen (Leuven-bus, opstapplaats, andere verdeling) | scenario-JSON schrijven (bestaand formaat) | nee |
| Snel weten of het beter is | `busroutes evaluate --offline <scenario>` | nee |
| Volgorde per bus verbeteren | `busroutes optimize --order <scenario>` | nee |
| Beste verdeling laten zoeken (evt. met vaste bussen/stops) | `busroutes optimize --assign <scenario>` | nee |
| Definitieve cijfers + kaart met echte wegen | `busroutes evaluate <scenario>` | ja (7 calls) |
| Vergelijken | `busroutes compare out/*/metrics.json` | nee |
| Nieuw punt (leerling/opstapplaats) toevoegen | `busroutes data add-points …` | ja (±280 tr./punt) |

## Werkpakketten (elk zelfstandig aan een agent te geven)

Elk WP: eigen branch of worktree, TDD, DoD (`uv run ruff check . && uv run ruff format
--check . && uv run pytest`), geen regressie in `docs/samples/expected/`, commit per WP,
CHANGELOG `[Unreleased]` bijwerken. Werkwijze: `superpowers:subagent-driven-development`
met dit plan als opdrachtbeschrijving per WP; ik (hoofdsessie) review elk WP.

### WP0 — Huishouden (ik, klein)
- `docs/samples/school.json` staat lokaal op `08:30` (ongecommit); `expected/` is op
  08:20 gerekend. Beslissing Mark: 08:20 terugzetten óf 08:30 committen en de drie
  `expected/*.metrics.json` hergenereren (21 route-calls, goedkoop). Default in dit plan:
  **08:30 behouden + expected vernieuwen** (Mark heeft dit bewust aangepast).
- `Claude outputs/` in `.gitignore`.
- Dit plan volledig kopiëren naar `.agent/plans/2026-09-16-hybride-optimalisatie.md` en
  registreren in `INDEX.md` (AGENTS.md: repo-kopie is canoniek).

### WP1 — Ontwerp-spec (ik, na goedkeuring van dit plan)
`docs/superpowers/specs/2026-09-16-hybride-optimalisatie-design.md`: datapakket-layout,
offline-modus, solver-doelfunctie, CLI-contract, skill-tabel, privacyregels. Dit is het
contract waar WP2–WP6 tegen bouwen; Mark keurt de spec goed vóór WP2 start.

### WP2 — Datapakket + offline-modus (`busroutes`) ✅ 16/09/2026
Agent-opdracht:
- **Datapakket** = één map (`BUSROUTES_DATA_DIR`, CLI `--data`), default `docs/samples/`
  (de fictieve set is meteen het voorbeeldpakket): `school.json`, `students.json`,
  `buses.json`, `pickup_points.json`, `matrix/` (= de bestaande cells-cache, per punt).
  Bestaande `load_samples` (`busroutes/models.py`) hergebruiken/uitbreiden; de
  matrix-cache van `TomTomClient` (`_read_cells`/`_write_cells`, `busroutes/tomtom.py`)
  laten wijzen naar `<data>/matrix/`.
- **Offline-client**: een `GeoClient` (Protocol in `busroutes/tomtom.py`) die `route()`
  beantwoordt uit de matrix: leg-tijd = cel, leg-afstand = haversine (`busroutes/geo.py`)
  — gemarkeerd als benadering —, polyline = rechte lijn. Fout (fail fast) als een paar
  ontbreekt, met het commando dat het oplost. `matrix()` = cellen lezen, nooit ophalen.
- `evaluate --offline` gebruikt die client; `metrics.json` krijgt `"mode": "offline"`
  en `map.html` toont dat duidelijk (rechte lijnen, banner). `compare` toont de modus.
- `busroutes data fetch-matrix [--dry-run]`: vult alle ontbrekende paren van het pakket
  (via bestaande `plan_blocks`/goedkoopste blokvorm), rapporteert kost vooraf.
- `busroutes data add-points <json>`: nieuwe leerling(en)/opstapplaats(en) toevoegen +
  snap (`snap_to_street`) + enkel de nieuwe rij/kolom ophalen.
- Tests met `FakeGeoClient` (`tests/conftest.py`): offline-evaluatie geeft dezelfde
  rittijden als de matrix voorschrijft; ontbrekend paar → duidelijke fout; `add-points`
  haalt exact 2×N cellen.
- Docs: `docs/samples/README.md` (pakket-layout), `docs/data-en-tooling-opties.md`
  (beslissing offline-modus + kostencijfers).

### WP3 — Stdlib-solver `busroutes/optimize.py` + CLI `optimize`
Agent-opdracht (na WP2, werkt op de matrix van het datapakket):
- **Doelfunctie** (lexicografisch): 1) langste rit per kind, 2) som van rittijden
  (= gemiddelde), 3) totale rijtijd. Rittijd per kind = tijd van zijn stop tot school
  incl. dwell van latere stops (zelfde formule als `evaluate_bus`). Let op: dit is *niet*
  de kortste route — de huidige `ordering.py` minimaliseert routelengte.
- **Niveau A `--order`**: per bus de volgorde verbeteren (2-opt + or-opt op de echte
  doelfunctie), verdeling ongewijzigd. Vervangt de heuristiek in `ordering.py` voor
  `ordering: auto` (matrix-strategie) — `haversine`-strategie blijft bestaan.
- **Niveau B `--assign`**: verdeling + volgorde. Local search: relocate/swap van stops
  tussen bussen, capaciteit hard, daarna A per bus. Respecteert in het invoer-scenario
  **vaste elementen**: `"pinned": true` op een bus (raak niet aan) of scenario-veld
  `"pinned_stops": [...]` (die stops blijven op hun bus); opstapplaatsen blijven één stop met hun leerlingen. Deterministisch
  (vaste seed, `--seed`), tijdslimiet `--max-seconds` (default 30).
- Output: `scenarios/<naam>-optimized.json` (bestaand formaat, `ordering: given`) +
  samenvatting vóór/na op stdout (offline-cijfers). Geen TomTom-call.
- Tests: kleine handmatrix-wereld (conftest) — A vindt het optimum op 4–5 stops;
  B verplaatst een verkeerd ingedeeld kind; pinned blijft staan; capaciteit gerespecteerd;
  seed → identieke output.

### WP4 — Benchmark-spike (throwaway, parallel aan WP3 na WP2)
Agent-opdracht: op de **fictieve** set de solver van WP3 vergelijken met echte
VRP-solvers, allemaal gevoed met **dezelfde matrix uit het datapakket** (zodat enkel de
solver verschilt, niet de reistijden), en allemaal beoordeeld via `evaluate --offline` +
één `evaluate` met TomTom, op dezelfde doelfunctie (langste rit, gemiddelde rit):

| Kandidaat | Hoe | Kost / voorwaarde |
|---|---|---|
| **Stdlib-solver (WP3)** | referentie | gratis |
| **pyvroom** | `uv add --group bench pyvroom`; `matrices`-invoer; langste rit drukken via dalende `max_travel_time` | gratis, ±40 MB |
| **Google OR-Tools** | `uv add --group bench ortools`; routing-model met capaciteit + tijd-dimensie, `GlobalSpanCost` voor min-max, arc-kost voor de som | gratis, ±75 MB |
| **VROOM-demoserver** (optioneel, eerste blik) | `http://solver.vroom-project.org`, ≤100 jobs → bus1 vast, ≤5 queries, niet-commercieel; OSRM-tijden i.p.v. onze matrix | gratis, geen garanties |
| **Google Route Optimization API** (optioneel) | eigen GCP-project met billing; vlootkost-objectief, dus min-max enkel benaderbaar via `costPerHour` + route-duurlimieten; eigen reistijden (niet onze matrix) | ±€4 per volledige run (docs 14/09); enkel als Mark een GCP-project opzet |

Meetpunten per kandidaat: `max_ride_min`, `avg_ride_min`, `rides_over_60_min`, totale
km, rekentijd, regels code, installatiegrootte. Resultaat: sectie in
`docs/data-en-tooling-opties.md` met de tabel + aanbeveling (stdlib volstaat / VROOM
hosten / OR-Tools lokaal). Scripts onder `scripts/bench_*.py`, niet in `busroutes/`,
niet in de plugin; `bench`-dependency-groep staat los van `dev` zodat de DoD niet
zwaarder wordt.

### WP5 — Skill herschrijven (`skills/scenario-evaluator/SKILL.md` + plugin-kopie)
Agent-opdracht (met `superpowers:writing-skills`, na WP2+WP3):
- Beslissingstabel hierboven als kern; werkwijze: pakket controleren → scenario → offline
  → optimize → pas dan TomTom → kaart als artifact → compare.
- Datapakket-instructie: waar de school-map staat (`BUSROUTES_DATA_DIR`), dat die nooit
  in de plugin zit; fictieve set als voorbeeld.
- Sectie "TomTom Maps-connector" **verwijderen**; sectie "Wat je nooit doet" uitbreiden
  (geen solver-alternatieven zoeken, geen matrix opnieuw ophalen, geen echte data in git).
- Skill-test met subagenten (baseline/GREEN zoals in plan 2026-09-14): "maak een
  Leuven-bus die eerst naar Leuven rijdt", "verbeter de volgorde van bus 6", "zoek de
  beste verdeling met bus1 vast".
- `scripts/build_plugin.py` + `tests/test_build_plugin.py`: nieuw module-bestand komt
  automatisch mee (controleren), README van de plugin bijwerken.

### WP6 — Echte-data-pijplijn (geblokkeerd tot de school data levert)
Agent-opdracht:
- `busroutes data geocode <adressen.csv>`: adres → coördinaat (TomTom geocoding, ±1 call
  per adres) → snap op straat → **adres wordt niet opgeslagen**; ids worden willekeurig
  (`uuid`/teller), geen namen; output `students.json` + optionele `pickup_points.json`.
- Daarna `data fetch-matrix` (±8.000 tr. voor 140 punten; dry-run eerst).
- Privacy-sectie in `docs/data-en-tooling-opties.md` + AGENTS.md: wat het pakket bevat,
  waar het staat, dat `.cache/`/datapakket buiten git blijven; de school beslist over
  cloud-geocoding (eenmalig, adressen gaan één keer naar TomTom).
- Wat Mark aanlevert: adressen (of al coördinaten), buscapaciteiten per bus, beltijd
  (nu 08:30 aangenomen), eventuele vaste opstapplaatsen.

## Volgorde en afhankelijkheden

```
WP0 → WP1 (spec, goedkeuring Mark) → WP2 → WP3 → WP5
                                        └→ WP4 (parallel met WP3)
WP6 pas zodra de school data levert (na WP2)
```

## Verificatie (einde van het geheel)

1. DoD groen; `BUSROUTES_REGRESSION=1 uv run pytest tests/test_regression.py` groen met
   vernieuwde expected.
2. `busroutes evaluate --offline docs/samples/scenarios/opstapplaatsen.json` → geen
   TomTom-call (usage-rapport 0), metrics met `mode: offline`.
3. `busroutes optimize --assign docs/samples/scenarios/opstapplaatsen.json` → nieuw
   scenario; offline `max_ride_min` ≤ die van het invoer-scenario; daarna één echte
   `evaluate` → compare-tabel toont winst t.o.v. de drie handscenario's.
4. Plugin gebouwd (`scripts/build_plugin.py`), in Cowork: agent volgt de tabel en levert
   kaart + cijfers zonder naar de TomTom-connector te grijpen.
5. Benchmark-sectie in de docs met cijfers stdlib-solver vs pyvroom vs OR-Tools (en
   optioneel VROOM-demo / Google Route Optimization), allemaal op dezelfde matrix.
