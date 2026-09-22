# WP3-fix tasks: `optimize --assign` inzetbaar maken op 140 stops / 7 bussen

Bron: `.agent/reviews/2026-09-16-wp2-wp3-review.md` — issues 1 (Critical: schaalt niet, tijdslimiet niet gerespecteerd), 5 (reproduceerbaarheid onder tijdslimiet), 6 (geen e2e op realistische schaal) en de minors 8 (foute "1 matrixparen ontbreken") en 7 (`BUSROUTES_REFERENCE_DATE` onnodig).
Issues 2, 3, 4 zijn al gefixt (17/09/2026, ongecommit op `wp3-stdlib-solver` bij het schrijven van dit plan).

Werkdir: repo-root op branch `wp3-stdlib-solver`. TDD verplicht (RED → GREEN). Geen WP4-benchmark tegen OR-Tools/VROOM, geen WP5-skill, geen `cells.py`-extract (blijft WP2-restpunt).

## Meetlat (harde eisen, allemaal als test)

| Wat | Nu (gemeten 16/09) | Doel |
|---|---|---|
| `optimize --order` op `regiobus-per-zone.json` (140 stops, 7 bussen), CLI | 18 s (6,9 s system = schijf-reads) | < 3 s |
| `optimize_assign` 40 stops / 4 bussen, `max_seconds=1`, in-memory | 24 s | < 3 s |
| `optimize_assign` 140 stops / 7 bussen, `max_seconds=30`, in-memory | onbekend (100/5 na 15 min afgebroken) | terug binnen 35 s, met minstens 1 verbetering op een geografisch gemengde start |
| Zelfde seed, zelfde invoer, zelfde `--max-perturbations` | byte-identiek zolang de tijdslimiet niet bijt | byte-identiek ongeacht machinesnelheid, tenzij de noodrem bijt en dat gemeld is |

## Global constraints

- Doelfunctie blijft `(max_ride_s, sum_ride_s, total_drive_s)` lexicografisch; `score_bus` blijft de referentie. Elke snelheidswinst moet **dezelfde score** opleveren voor dezelfde uiteindelijke toewijzing — test dat `score_scenario(result)` gelijk is aan de som/max van de gecachte per-bus-scores.
- Pinned-semantiek (`pinned`, `pinned_stops`, `auto` blijft `auto` op een pinned bus) ongewijzigd; de bestaande tests in `tests/test_optimize.py` blijven groen zonder aanpassing.
- Solver blijft stdlib-only, geen numpy.
- Plugin-kopie: na elke wijziging in `busroutes/` `uv run python scripts/build_plugin.py`.
- DoD na elke task: `uv run ruff check . && uv run ruff format --check . && uv run pytest` groen.
- Commit per task op `wp3-stdlib-solver`. Geen force-push, geen amend.

## Task 1: Synthetische schaalfixture + benchmark (meetbaar maken)

Doel: de meetlat kunnen draaien vóór er iets geoptimaliseerd wordt. Deze task levert **falende** schaaltests op (RED), die tasks 2–4 groen maken.

### Fixture (`tests/conftest.py` of nieuw `tests/scale.py`)

- `make_scale_world(n_stops: int, n_buses: int, seed: int = 0) -> tuple[School, dict[str, Student], dict[str, Bus], HandMatrixClient-achtige client]`.
- Punten: school in het midden, stops in `n_buses` geografische clusters (bv. cluster-centra op een cirkel, stops met gaussische spreiding) — zo bestaat er een duidelijk betere toewijzing dan een gemengde start.
- Reistijd = haversine / 10 m/s + kleine deterministische asymmetrie (bv. +5 % heen, −5 % terug per paar op basis van `hash`-vrije formule zoals `(i*7 + j*3) % 11`), volledig **in-memory**, geen schijf.
- Capaciteit per bus = `ceil(n_stops / n_buses) + 2` zodat er vrije plaatsen zijn (perturbatie moet kunnen bewegen).
- `mixed_scenario(world)`: stops round-robin over de bussen (bus_i krijgt stop_i, stop_{i+n_buses}, …) → geografisch gemengd.

### Benchmark-script `scripts/bench_optimize.py` (throwaway, geen test)

- Argumenten `--stops`, `--buses`, `--max-seconds`, `--seed`.
- Print: wall-time, aantal `travel()`-calls (tel via wrapper), score vóór/na, aantal perturbaties.
- Draai na elke volgende task op 40/4, 100/5, 140/7 en noteer de cijfers in de commitmessage.

### Tests (RED na deze task)

- `test_optimize_assign_40x4_returns_within_3s`: `max_seconds=1` → wall < 3 s.
- `test_optimize_assign_140x7_returns_within_35s`: `max_seconds=30` → wall < 35 s **en** score na < score vóór. Markeer `@pytest.mark.slow` als de suite anders > 60 s wordt; de default-run moet hem wel draaien (DoD 3).
- `test_optimize_order_140x7_under_1s_in_memory`: niveau A alleen.

### Niet in deze task

Geen wijziging aan `optimize.py` of `cli.py`.

## Task 2: Matrix één keer laden in de CLI (issue 1.1 + minor 8 + minor 7)

### Gedrag

- `cmd_optimize`: verzamel alle punten (school, elke `bus.start`, elke stop) en roep **één keer** `client.matrix(points, points)` aan; bouw `travel` met `_travel_from_matrix` (verplaats die helper uit `evaluate.py` naar `optimize.py` of een klein `busroutes/travel.py`, en laat `evaluate.py` hem daar importeren — geen duplicaat).
- `OfflineError` uit die ene call geeft de **echte** telling van ontbrekende paren (nu altijd "1"). Meld daarbij `busroutes data status` als volgende stap.
- `optimize` (en `data fetch-matrix`, `data add-points`) vereisen geen `BUSROUTES_REFERENCE_DATE` meer: geef `load_settings(require_key=False, require_reference_date=False, …)` of vul een dummy in. `evaluate` blijft hem eisen (route-calls).

### Tests

- `tests/test_cli.py`: `write_auto_pack` → tel `OfflineClient.matrix`-calls via monkeypatch: exact 1 voor `--order`, exact 1 voor `--assign`.
- Pack met 3 ontbrekende paren → stderr bevat "3 matrixparen ontbreken".
- `optimize --order` zonder `--reference-date` en zonder env → exit 0.
- Meetlat-regel 1: `optimize --order` op `docs/samples/scenarios/regiobus-per-zone.json` < 3 s (CLI-test met `main([...])`, `--out` naar `tmp_path`).

## Task 3: Delta-scoring en ordenen na acceptatie (issue 1.2 + 1.3)

Dit is de kern. Spec §4 Niveau B zegt "na elke zet niveau A op de geraakte bussen"; letterlijk per **kandidaat** is dat O(n³) per kandidaat × O(N²) kandidaten. Nieuwe lezing (spec-amendement, zie onderaan): niveau A na **acceptatie** van een zet; kandidaten worden geschat met `_best_insert`.

### Gedrag

- Houd in `_local_search` een lijst `bus_scores: list[Score]` bij (één `score_bus` per bus). `score_scenario` van een kandidaat = herbereken **alleen** de twee geraakte bussen en combineer met de rest (max over max_ride, som over sum_ride en total_drive). Voeg `combine_scores(scores: Iterable[Score]) -> Score` toe en test dat `combine_scores(map(score_bus, …)) == score_scenario(…)`.
- **Relocate-kandidaat**: src zonder de stop (volgorde ongewijzigd, dus geen herordening nodig voor de schatting) + dst via `_best_insert`. Accepteer als de gecombineerde score daalt. **Na acceptatie**: `_apply_order` op src en dst, scores bijwerken.
- **Swap-kandidaat**: stop_a uit i, stop_b uit j; elk via `_best_insert` in de andere bus (niet positie-wissel). Na acceptatie `_apply_order` op beide.
- First-improvement blijft (geen best-improvement), maar loop de bussen af in een vaste volgorde zodat de uitkomst deterministisch blijft.
- `deadline: float | None` doorgeven aan `_local_search`, `_first_improving_relocate`, `_first_improving_swap`; check `time.monotonic() > deadline` in de **buitenste stop-lus** van elke buurt (niet per kandidaat — te duur, en één buitenste iteratie is op 140 stops hooguit ~N·B `_best_insert`-calls). Bij deadline: huidige (geldige) toestand teruggeven.
- Dezelfde `bus_scores`-cache gebruiken in `_perturb` (alleen geraakte bussen herscoren).

### Tests

- `combine_scores` == `score_scenario` op de handwereld en op `make_scale_world(20, 3)`.
- Bestaande assign-tests (mixed north/south, capaciteit, pinned, pinned_stops, niveau-A-start, seed-trail) blijven groen **zonder aanpassing** — dat is de regressiebescherming van de semantiek.
- Meetlat-regel 2 (40×4 < 3 s) wordt groen.
- `_local_search` met `deadline = now` op `make_scale_world(60, 4)` keert terug < 0,5 s en geeft een scenario waarvan elke bus binnen capaciteit zit en alle stops exact één keer voorkomen.

## Task 4: Reproduceerbaar stopcriterium (issue 5)

### Gedrag

- Nieuwe parameter `max_perturbations: int = 1000` op `optimize_assign` en CLI-flag `--max-perturbations` (default 1000). Stop-regel wordt: `stall < 200 and perturbations < max_perturbations` — beide deterministisch gegeven seed + invoer.
- `--max-seconds` (default 30) blijft als **noodrem**. Als hij bijt: `optimize_assign` geeft dat terug (bv. `OptimizeResult(scenario, perturbations, stopped_by: Literal["stall","max_perturbations","max_seconds"])` of een tweede return-waarde) en de CLI print op stderr: `Let op: tijdslimiet (30 s) bereikt na N perturbaties; resultaat hangt af van machinesnelheid. Verhoog --max-seconds of verlaag --max-perturbations voor een reproduceerbare run.`
- CLI print altijd `Perturbaties: N (gestopt door: …)` op stdout, zodat de skill-agent (WP5) het kan rapporteren.
- Signature-wijziging van `optimize_assign` niet breken voor bestaande callers: `max_seconds` en `seed` blijven keyword-only met dezelfde defaults.

### Tests

- Zelfde seed + `max_perturbations=50`, `max_seconds=1000` → twee runs byte-identiek op `make_scale_world(40, 4)` (waar perturbatie iets doet; zie seed-trail-test).
- `max_seconds=0.001` op 140×7 → `stopped_by == "max_seconds"` en CLI-stderr bevat "tijdslimiet".
- `max_perturbations=5` → `stopped_by == "max_perturbations"` en exact 5 `_perturb`-calls (via de bestaande `_record_perturbations`-helper).
- Meetlat-regel 3 (140×7 < 35 s met verbetering) wordt groen.

## Task 5: End-to-end `--assign` op schaal via de CLI (issue 6)

### Gedrag

- Schrijffunctie `write_scale_pack(directory, n_stops, n_buses)` in `tests/` die `make_scale_world` naar een datapakket op schijf dumpt (`school.json`, `students.json`, `buses.json`, `scenario.json` gemengd, `matrix/` cellen inclusief 0-diagonaal, exact het formaat van `write_origin_row`).
- Geen wijziging aan `docs/samples/` (matrix blijft de drie referentiescenario's dekken; dat is een bewuste WP2-keuze).

### Tests (`tests/test_cli.py`)

- `optimize --assign --seed 0 --max-perturbations 100` op een 12-stops/3-bussen pack → exit 0, stdout bevat minstens één regel `sXXX: was busA, nu busB`, output-JSON laadt via `load_scenario_file` zonder fout en elke bus zit binnen capaciteit.
- Zelfde aanroep twee keer → byte-identieke output (vervangt de huidige 1-leerling-variant `test_optimize_assign_seed_zero_is_deterministic`).
- `busroutes data status` op dat pack → "0 ontbrekend" (bewijst dat de fixture compleet is).

### Docs

- `docs/samples/README.md` en `skills/scenario-evaluator/references/data-schema.md`: `--max-perturbations` en de noodrem-melding beschrijven; vermelden dat `--reference-date` niet nodig is voor `optimize`.
- CHANGELOG: onder Added `--max-perturbations`; onder Changed "optimize laadt de matrix één keer; `--max-seconds` is een noodrem met melding".
- `docs/superpowers/specs/2026-09-16-hybride-optimalisatie-design.md` §4 Niveau B: "Na elke zet niveau A op de geraakte bussen" → "Kandidaten worden geschat met beste-invoegpositie; na **acceptatie** van een zet niveau A op de geraakte bussen. Stop bij 200 perturbaties zonder verbetering of `--max-perturbations` (reproduceerbaar); `--max-seconds` is een noodrem die gemeld wordt." Datum + "besloten na review 16/09/2026".

## Afsluiting

- Benchmark-cijfers (40/4, 100/5, 140/7) in `.agent/plans/2026-09-16-hybride-optimalisatie.md` onder WP3 noteren.
- `.agent/reviews/2026-09-16-wp2-wp3-review.md`: issues 1, 5, 6, 7, 8 afvinken.
- INDEX.md: dit plan registreren (✅ na afronding).
- Daarna: `superpowers:requesting-code-review` op de range vanaf `b24c9a4`.
