# Hybride optimalisatie: datapakket, offline-modus, stdlib-solver, skill-herwerking

Datum: 2026-09-16
Status: ontwerp ter goedkeuring (brainstorming 15–16/09/2026)
Plan: `.agent/plans/2026-09-16-hybride-optimalisatie.md` (werkpakketten WP0–WP6)

## Probleem

De evaluator rekent handgemaakte scenario's door, maar bedenkt er zelf geen. Het
"volledig geoptimaliseerde scenario" uit de projectbrief ontbreekt, en elke doorrekening
hangt aan TomTom (key, credits, netwerk). Bovendien moet de agent die de skill gebruikt
nu zelf kiezen tussen CLI, TomTom-connector en kaartvormen — dat gaat mis.

Doel: met een **vooraf verzameld datapakket** (school, bussen, leerlingpunten,
opstapplaatsen, reistijdmatrix) kan de skill scenario's bouwen, **gratis offline**
doorrekenen, **optimaliseren** (volgorde per bus én verdeling over bussen) en enkel voor
de definitieve kaart en cijfers TomTom aanspreken. De agent volgt één beslissingstabel.

## Beslissingen

| Vraag | Keuze | Waarom |
|---|---|---|
| Solver | Eigen stdlib-solver (local search) in `busroutes/optimize.py` | Plugin kan geen bibliotheken installeren; 7 bussen × 140 stops op een kant-en-klare matrix is klein genoeg. OR-Tools/pyvroom/VROOM enkel als benchmark (WP4) |
| Solver-invoer | De TomTom-matrix uit het datapakket (`departAt=any`, historisch) | Eén keer betalen (±8.000 tr. voor 141 punten), daarna onbeperkt gratis; nieuw punt ±280 tr. |
| Doelfunctie | Lexicografisch: langste rit per kind → som van rittijden → totale rijtijd | Kernvraag van de brief; niet vlootkost |
| Offline-modus | `evaluate --offline`: tijden uit de matrix, afstand geschat, rechte lijnen | Onbeperkt proberen zonder key; TomTom enkel voor de definitieve versie |
| Datapakket | Eén map, `BUSROUTES_DATA_DIR` / `--data`; fictieve set in `docs/samples/` is het voorbeeldpakket, inclusief matrix | School-specifieke data leeft buiten de code en buiten de publieke repo/plugin |
| Privacy | Alleen coördinaten, willekeurige ids, geen namen/adressen; punten op de straat gesnapt; pakket nooit in git of plugin | TomTom rekent toch enkel met coördinaten; adres is alleen nodig voor eenmalige geocoding |
| Skill | Vaste beslissingstabel, één commando per vraag; TomTom-MCP-connector verdwijnt uit de skill | Agent hoeft geen diensten te kiezen |
| Hosting | Geen | Stdlib-solver draait in de plugin; herzien enkel als de benchmark een groot kwaliteitsverschil toont |

## Architectuur

```
datapakket (<data>/)                busroutes/                        output
  school.json      ──┐                models.load_data_pack             out/<naam>/
  students.json    ──┼──► Scenario ──► evaluate ──┬─ OfflineClient ─────► metrics.json (mode: offline)
  buses.json       ──┤    (json)      (bestaand)  └─ TomTomClient ──────► metrics.json + map.html (mode: tomtom)
  pickup_points.json─┤
  matrix/…         ──┴──► optimize ───► scenarios/<naam>-optimized.json ──► evaluate …
```

- **`evaluate`** blijft de enige bron van cijfers en kaarten; het verschil offline/TomTom
  zit uitsluitend in de `GeoClient`-implementatie (bestaand Protocol in `busroutes/tomtom.py`).
- **`optimize`** produceert enkel een scenario-JSON in het bestaande formaat; het doet
  nooit een netwerkcall.
- De matrix-cache per punt-paar (nu `.cache/tomtom/cells/`) verhuist naar het datapakket
  (`<data>/matrix/`). De route-cache (`.cache/tomtom/route/`) blijft waar hij is — die is
  afgeleid, niet school-specifieke brondata.

## Componenten

### 1. Datapakket (`busroutes/models.py`, `busroutes/config.py`)

Layout van `<data>/`:

| Bestand | Verplicht | Inhoud |
|---|---|---|
| `school.json` | ja | bestaand schema (id, naam, lat/lon, `target_arrival`) |
| `students.json` | ja | `[{id, lat, lon, zone?}]` — ids willekeurig, geen namen |
| `buses.json` | ja | bestaand schema |
| `pickup_points.json` | nee | bestaand schema |
| `matrix/<opties-digest>/<lat,lon>.json` | voor offline/optimize | exact de huidige cells-structuur: per oorsprong een dict `"lat,lon" → seconden` |
| `README.md` | nee | herkomst, datum van de matrix, wat wél/niet echte data is |

Resolutie van de map: `--data <pad>` > `BUSROUTES_DATA_DIR` > `docs/samples/`. De
bestaande `--samples`-vlag blijft als alias van `--data` (met een deprecatie-melding).
`load_samples` wordt `load_data_pack` (oude naam blijft als alias) en leest ook
`pickup_points.json` in. `Settings` krijgt `data_dir`; `TomTomClient` krijgt een aparte
`cells_dir` (default `<data>/matrix`) naast `cache_dir` (routes, geocoding).

Migratie: eenmalig `.cache/tomtom/cells/` → `docs/samples/matrix/` verplaatsen en
**committen** (fictieve data, ±19.000 getallen, <1 MB). Daarmee werkt offline-modus in
de repo en in CI zonder key. De plugin-build blijft `docs/samples/` uitsluiten.

### 2. Offline-client (`busroutes/offline.py`)

`OfflineClient(cells_dir)` implementeert `GeoClient`:

- `route(points, depart_at)` → per leg `RouteLeg(travel_time_s=cel(a→b),
  length_m=round(haversine(a,b) × 1.3), points=[a, b])`. De factor 1,3 is een
  wegenfactor (constante `OFFLINE_ROAD_FACTOR`, gedocumenteerd) — km zijn in offline-modus
  een **schatting** en worden zo gelabeld. `depart_at` wordt genegeerd (matrix is
  tijdsonafhankelijk).
- `matrix(origins, destinations)` → cellen lezen. Nooit ophalen.
- Ontbrekende cel → `OfflineError` met het aantal ontbrekende paren en het commando
  `busroutes data fetch-matrix --dry-run` als oplossing. Geen stille fallback naar
  haversine (fail fast, AGENTS.md).
- `usage` blijft `Usage()` met nullen, zodat het bestaande verbruiksrapport "0" toont.

Gevolgen in de output:

- `metrics.json`: nieuw veld `"mode": "offline" | "tomtom"` onder `settings`, en
  `"km_estimated": true` bij offline.
- `map.html`: banner "Offline-schatting: tijden uit de matrix, rechte lijnen, km geschat";
  routes als rechte lijnen tussen stops (zelfde kleuren/markers als nu).
- `compare`: kolom "Modus"; menging offline/tomtom in één tabel is toegestaan maar
  wordt gemarkeerd.

### 3. `busroutes data …` (`busroutes/cli.py`, `busroutes/datapack.py`)

| Subcommando | Doet | TomTom |
|---|---|---|
| `data status` | telt punten, aanwezige/ontbrekende matrixparen, geraamde kost om te vervolledigen | nee |
| `data fetch-matrix [--dry-run]` | haalt alle ontbrekende paren (alle punten × alle punten, incl. school en opstapplaatsen) via `TomTomClient.matrix` met de bestaande goedkoopste-blokplanning; dry-run toont enkel de kost | ja |
| `data add-points <json>` | voegt leerlingen/opstapplaatsen toe: snap op straat (`snap_to_street`), schrijft naar `students.json`/`pickup_points.json`, haalt enkel de nieuwe rijen en kolommen | ja (±2×N cellen per punt) |
| `data geocode <csv>` (WP6) | adres → coördinaat via TomTom Search, snap, willekeurige id; **adres wordt niet weggeschreven** | ja (1 per adres) |

`add-points`-invoer: `[{"id"?: "…", "lat": …, "lon": …, "zone"?: "…", "kind": "student" | "pickup_point", "name"?: "…"}]`.
Zonder `id` wordt er een willekeurige gegenereerd. Alle schrijfacties zijn atomisch
(bestaand `_write_json`).

### 4. Solver (`busroutes/optimize.py`)

**Doelfunctie.** Voor een bus met stops `s₁…sₙ` in die volgorde, leg-tijden `t` uit de
matrix en dwell `d(s) = 30 + 10·|riders(s)|` (uit `Settings`):

```
rit(sₖ)   = Σ_{j>k} t(sⱼ₋₁→sⱼ) + t(sₙ→school) + Σ_{j>k} d(sⱼ)      # zelfde formule als evaluate_bus
score     = ( max over alle kinderen rit,                            # 1. langste rit
              Σ over alle kinderen rit,                              # 2. som (= gemiddelde)
              Σ over bussen totale rijtijd incl. start→s₁ )          # 3. rijtijd
```

Vergelijking is lexicografisch (tuple-vergelijking). Dit wijkt bewust af van
`ordering.py`, dat routelengte minimaliseert.

**Niveau A — `optimize --order`.** Per bus, verdeling ongewijzigd: start van de gegeven
volgorde, herhaal 2-opt (segment omkeren) en or-opt (segment van 1–3 stops verplaatsen)
zolang de score daalt. Deterministisch. Dit vervangt intern de heuristiek voor
`ordering: auto` met strategie `matrix` (`_ordered_stops` in `evaluate.py` roept de
solver aan); de `haversine`-strategie blijft de bestaande heuristiek gebruiken.

**Niveau B — `optimize --assign`.** Verdeling én volgorde:

1. Start = het invoerscenario (elke bus die in het scenario staat, ook met lege
   `stops`, is beschikbaar; bussen die er niet in staan worden niet gebruikt).
2. Buren: *relocate* (één stop naar een andere bus, beste invoegpositie) en *swap*
   (twee stops van verschillende bussen wisselen). Capaciteit is hard. Na elke zet
   niveau A op de geraakte bussen. Accepteer bij lagere score.
3. Zit de zoektocht vast: perturbatie (willekeurig `k` stops verplaatsen, `k`=3) en
   opnieuw; bewaar het beste. Stop bij `--max-seconds` (default 30) of als 200
   perturbaties niets opleveren.
4. `--seed` (default 0) → identieke output bij identieke invoer.

**Vaste elementen** in het invoerscenario, zodat de gebruiker kan "tunen":

- bus-object `"pinned": true` → deze bus wordt niet aangeraakt (verdeling én volgorde).
- scenario-veld `"pinned_stops": ["s041", "pp-leuven-station"]` → deze stops blijven
  op hun huidige bus; hun volgorde mag wel wijzigen.
- Een opstapplaats is altijd één stop met al zijn leerlingen; de solver splitst nooit.
- `start` per bus (bv. stelplaats of "eerst naar Leuven") wordt gerespecteerd via de
  leg start→s₁ in de derde score-component.

`load_scenario` accepteert de nieuwe velden en valideert ze (onbekende stop-id in
`pinned_stops` → `ScenarioError`).

**Output.** `scenarios/<naam>-optimized.json` (`--out` overschrijft): bestaand formaat,
`"ordering": "given"`, `description` = origineel + " · geoptimaliseerd (order|assign,
seed N)". Stdout: compare-tabel vóór/na, berekend met de `OfflineClient` (dus 0
TomTom-calls), plus welke kinderen van bus wisselden.

### 5. Skill (`skills/scenario-evaluator/SKILL.md` → plugin-kopie)

Kern is deze tabel; de agent kiest nooit een andere weg:

| Gebruiker wil | Agent doet | TomTom-key |
|---|---|---|
| Scenario bedenken/aanpassen | scenario-JSON schrijven (schema in `references/data-schema.md`) | nee |
| Snel weten of het beter is | `evaluate --offline` | nee |
| Volgorde per bus verbeteren | `optimize --order` | nee |
| Beste verdeling zoeken (evt. met vaste bussen/stops) | `optimize --assign` | nee |
| Definitieve cijfers + kaart met echte wegen | `evaluate` (7 calls) | ja |
| Vergelijken | `compare` | nee |
| Nieuw adres/opstapplaats | `data add-points` | ja (±280 tr./punt) |
| Weten wat het pakket bevat / wat ontbreekt | `data status` | nee |

Werkwijze in de skill: (1) `data status` → (2) scenario → (3) offline → (4) optioneel
optimize → (5) pas dan één echte `evaluate` → (6) kaart als artifact + compare-tabel.
De sectie "TomTom Maps-connector" verdwijnt; "Wat je nooit doet" krijgt erbij: geen
andere solver/dienst zoeken, matrix niet opnieuw ophalen, echte data nooit in git of
in de plugin, offline-cijfers nooit als definitief presenteren.

De plugin bevat géén datapakket. `README.md` van de plugin legt uit waar de school haar
pakket zet (`BUSROUTES_DATA_DIR`) en dat de fictieve set enkel in de repo staat.

### 6. Benchmark (WP4, throwaway)

Op de fictieve set, allemaal met dezelfde matrix: stdlib-solver, pyvroom, Google
OR-Tools; optioneel VROOM-demoserver en Google Route Optimization API. Beoordeling via
`evaluate --offline` en één echte `evaluate`. Dependency-groep `bench` los van `dev`.
Scripts in `scripts/bench_*.py`; resultaat als sectie in
`docs/data-en-tooling-opties.md`. Beslist of hosting ooit nodig is.

### 7. Echte data (WP6, na levering door de school)

`data geocode` (TomTom Search API, `countrySet=BE`) → snap → willekeurige ids → geen
adres in de output → `data fetch-matrix`. De school beslist expliciet over de eenmalige
cloud-geocoding. Docs: privacy-sectie (wat het pakket bevat, waar het staat, wat nooit
in git komt) in `docs/data-en-tooling-opties.md` en AGENTS.md.

## Foutafhandeling

- Ontbrekend datapakket of bestand → `ScenarioError` met pad en verwachte layout.
- Offline zonder volledige matrix → `OfflineError` met aantal ontbrekende paren en het
  fetch-commando; nooit stil terugvallen op haversine.
- `optimize` op een scenario dat `load_scenario` afkeurt → dezelfde `ScenarioError`.
- `fetch-matrix` zonder key → bestaande `ConfigError`; met `--dry-run` werkt het zonder key.

## Testen

- `tests/test_offline.py`: legs = matrixcellen; km = haversine × factor; ontbrekend paar
  → `OfflineError`; `metrics["settings"]["mode"] == "offline"`.
- `tests/test_datapack.py`: resolutie `--data`/env/default; `status` telt juist;
  `add-points` vraagt exact 2×N×(punten) cellen (via `FakeGeoClient.matrix_calls`);
  atomisch schrijven.
- `tests/test_optimize.py` (handmatrix-wereld uit `conftest.py`): A vindt het optimum op
  4–5 stops en verslaat de routelengte-heuristiek op een geconstrueerd geval; B verplaatst
  een fout ingedeeld kind; capaciteit hard; `pinned`/`pinned_stops` gerespecteerd;
  seed → byte-identieke output; `--max-seconds` wordt gerespecteerd.
- Regressie: `docs/samples/expected/` blijft de TomTom-referentie; erbij komt
  `expected/offline/` die in CI zonder key draait.
- Skill-test met subagenten (WP5): drie opdrachten uit het plan; agent volgt de tabel.

## Buiten scope

- VROOM/OR-Tools hosten of in de plugin stoppen.
- Tijdvensters per kind, meerdere scholen, namiddagritten (terugrit is de omgekeerde
  vraag; later).
- Modellering van TomTom's U-turn-penalty in de matrix (gedocumenteerde beperking).
- GUI.

## Definition of Done

Per WP: `uv run ruff check . && uv run ruff format --check . && uv run pytest` groen,
`BUSROUTES_REGRESSION=1` groen, CHANGELOG bijgewerkt, plugin-kopie gesynct
(`scripts/build_plugin.py --check`). Einde van het geheel: de vijf verificatiestappen
uit het plan.
