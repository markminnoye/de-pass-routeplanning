# Solver-benchmark (23/09/2026)

Vergelijking van de stdlib-solver, pyvroom en OR-Tools op **één matrix**, voor twee vragen: de stopvolgorde per bus (`optimize --order`) en de verdeling van leerlingen over de bussen (`optimize --assign`). Score is `evaluate --offline`.

De cijfers hier zijn een schatting op een gladgemaakte matrix, geen TomTom-`evaluate` op een verkeersdag. De tabel van 22/09 in [data-en-tooling-opties.md](data-en-tooling-opties.md) blijft de volgorde-vergelijking op de echte per-bus-cellen. De minuten uit de twee tabellen mag je niet naast elkaar leggen.

## Advies

**De plugin houdt de stdlib-solver.** pyvroom en OR-Tools blijven in de dependency-groep `bench`. VROOM hosten is niet nodig.

Het doel is de rit van het kind (eerst de langste, dan het gemiddelde, dan het aantal ritten boven 60 minuten), niet de kilometers. Op die score halen de drie solvers elkaar. Waar ze uit elkaar lopen, rijdt de stdlib-solver meer kilometers om de langste rit korter te maken — dat is het objectief, niet een misser.

- **Volgorde.** Op dit model is het verschil klein. `spreiding-gemengd`: stdlib 191,5 min langste rit tegen 201,9 voor de andere twee. `opstapplaatsen`: pyvroom heeft 53 ritten boven 60 minuten, stdlib 66, bij bijna dezelfde langste rit (144,3 tegen 145,8). Op de echte TomTom-cellen (22/09) won stdlib de langste rit op alle drie de scenario's.
- **Verdeling.** Vanaf een slechte mix (`spreiding-gemengd`) zakt de langste rit van 191,5 naar ongeveer 136 minuten, bij alle drie. Op `opstapplaatsen` haalt OR-Tools 107,5 minuten, stdlib 110,2, pyvroom 110,0. Op `regiobus-per-zone` is stdlib de kortste langste rit (130,0 tegen 135,8 en 136,6). OR-Tools doet dat in 8 seconden, de stdlib-zoektocht werd na 180 seconden afgekapt en was nog niet uitgeraasd (0 perturbaties). De rit wordt er niet duidelijk beter van.
- **Kilometers en onevenwicht.** pyvroom en OR-Tools blijven dichter bij de kilometerstand van de invoer. De stdlib-verdeling legt er tientallen kilometers bij. De zeven bussen starten met 20 leerlingen elk. Na `--assign` loopt het verschil tussen de volste en de leegste bus op tot 3–16 leerlingen. Stdlib houdt dat verschil het kleinst op de twee deur-tot-deur-scenario's.
- **Niet hosten.** pyvroom minimaliseert de routeduur en zoekt daarna de krapste `max_travel_time` die nog haalbaar is. Dat is niet de rit van het kind, en door die herhaalde solves duurt een verdeling 2–3 minuten. Een VROOM-dienst zou dezelfde matrix nog moeten ontvangen; de publieke demo gebruikt OSRM en is daarom niet aangeroepen.
- **OR-Tools alleen lokaal, in `bench`.** 65,5 MiB, niet in de plugin. Nuttig als later een snelle batch of een kilometerdoel nodig is. Google Route Optimization is niet gedraaid: die optimaliseert vlootkost, en er is geen GCP-project.

## Draaien

Vanaf de repo-wortel, na `uv sync --group bench`:

```bash
uv run python scripts/bench_full.py
```

Standaard: de drie referentiescenario's, seed 0, stdlib-verdeling tot 200 perturbaties of 180 seconden, OR-Tools-verdeling 8 seconden, pyvroom `exploration_level=5` en `nb_threads=1`. OR-Tools-volgorde is 1 seconde per bus, dezelfde routine als `scripts/bench_solvers.py`.

De run schrijft `docs/images/solver-bench-order.png`, `solver-bench-assign.png` en `solver-bench-runtime.png`, plus `out/bench/full.json` (gitignored). Een kortere proef:

```bash
uv run python scripts/bench_full.py \
  --scenarios spreiding-gemengd \
  --stdlib-seconds 20 --stdlib-perturbations 10 --ortools-seconds 3
```

Alleen de echte per-bus-cellen, zonder herverdeling:

```bash
BUSROUTES_REFERENCE_DATE=2026-09-15 uv run python scripts/bench_solvers.py
```

OR-Tools stopt op de klok. Deze build heeft geen schakelaar voor één zoekthread, dus een herhaling op een andere machine kan een halte verschuiven. De stdlib-verdeling hier stopte ook op de klok (`gestopt door max_seconds`, 0 perturbaties), niet op het reproduceerbare perturbatieplafond. pyvroom met één thread volgt wel een vaste zoektocht.

## Matrix

`docs/samples/matrix/` heeft 4.956 positieve TomTom-cellen, per referentiebus. Paren tussen bussen ontbreken, dus een herverdeling kan daar niet op scoren. Een mix van echte cellen en schattingen zou een rit tussen bussen een ander soort getal maken dan een rit binnen een bus.

`scripts/bench_matrix.py` trekt daarom één lijn door al die cellen en gebruikt die voor elk paar:

`seconden = max(1, afgerond(278 + 0,0755 × meter))`

Dat is 278 seconden plus 76 seconden per kilometer (marginale snelheid ongeveer 48 km/u, mediaan van de cellen 25 km/u). R² = 0,87. De mediane absolute fout is 18%. De lijn is symmetrisch; eenrichtingsverkeer zit er niet in. De diagonaal is 0.

`evaluate --offline` ziet die tijden via een `OfflineClient`. Kilometers blijven hemelsbreed × 1,3.

## Wat elke solver optimaliseert

| Solver | Volgorde | Verdeling |
|---|---|---|
| stdlib | 2-opt/or-opt op (langste rit, som van de ritten, rijtijd) | relocate/swap, daarna dezelfde ordening. Hier afgekapt na 180 s, vóór de eerste perturbatie |
| pyvroom 1.15.2 | kortste routeduur, dan de laagste `max_travel_time` die nog elke stop haalt | hetzelfde, met capaciteit (`pickup` = aantal leerlingen) en zeven voertuigen |
| OR-Tools 9.15 | tijd-dimensie, boog = reistijd + stilstand, `GlobalSpanCost` 100, 1 s per bus | hetzelfde, plus capaciteit, vaste kost 0, 8 s, eerste oplossing `PARALLEL_CHEAPEST_INSERTION` |

Stilstand is 30 s + 10 s per leerling. De rit van een kind loopt van vertrek aan zijn stop tot aankomst op school, zonder de eigen stilstand. De externe solvers optimaliseren de duur van de bus, niet die rit. De score hierna is wel die rit.

## Volgorde per bus

De verdeling blijft die van het scenario. Elke bus heeft 20 leerlingen, dus het onevenwicht is 0.

![Volgorde per bus: langste rit, gemiddelde, ritten boven 60 minuten en kilometers](images/solver-bench-order.png)

| Scenario | Solver | max rit (min) | gem. rit (min) | ritten > 60 | km | rekentijd (s) |
|---|---|---:|---:|---:|---:|---:|
| regiobus-per-zone | stdlib | 145.8 | 66.9 | 76 | 223.1 | 0.61 |
| regiobus-per-zone | pyvroom | 145.8 | 67.6 | 76 | 207.3 | 1.60 |
| regiobus-per-zone | ortools | 146.1 | 68.7 | 80 | 207.6 | 7.02 |
| opstapplaatsen | stdlib | 145.8 | 55.7 | 66 | 201.4 | 0.40 |
| opstapplaatsen | pyvroom | 144.3 | 54.9 | 53 | 189.7 | 1.10 |
| opstapplaatsen | ortools | 146.1 | 55.5 | 57 | 190.0 | 7.01 |
| spreiding-gemengd | stdlib | 191.5 | 85.5 | 86 | 664.7 | 0.60 |
| spreiding-gemengd | pyvroom | 201.9 | 93.9 | 89 | 639.5 | 1.39 |
| spreiding-gemengd | ortools | 201.9 | 102.9 | 97 | 639.8 | 7.01 |

pyvroom en OR-Tools rijden iets minder kilometers. Op de door elkaar gehusselde verdeling wordt de langste rit daardoor langer.

## Verdeling over de bussen

`stdlib --order` is de basis: alleen de volgorde, dezelfde run als hierboven. De andere drie mogen stops verplaatsen, binnen capaciteit 30.

![Verdeling: langste rit, gemiddelde, ritten boven 60 minuten en onevenwicht](images/solver-bench-assign.png)

| Scenario | Solver | max rit (min) | gem. rit (min) | ritten > 60 | km | onevenwicht | rekentijd (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| regiobus-per-zone | stdlib --order | 145.8 | 66.9 | 76 | 223.1 | 0 | 0.61 |
| regiobus-per-zone | stdlib --assign | 130.0 | 66.3 | 76 | 311.2 | 6 | 180.01 |
| regiobus-per-zone | pyvroom | 136.6 | 69.3 | 82 | 227.1 | 11 | 172.99 |
| regiobus-per-zone | ortools | 135.8 | 69.8 | 83 | 244.0 | 9 | 8.00 |
| opstapplaatsen | stdlib --order | 145.8 | 55.7 | 66 | 201.4 | 0 | 0.40 |
| opstapplaatsen | stdlib --assign | 110.2 | 54.0 | 60 | 281.8 | 15 | 180.04 |
| opstapplaatsen | pyvroom | 110.0 | 53.1 | 58 | 201.3 | 16 | 106.29 |
| opstapplaatsen | ortools | 107.5 | 50.4 | 63 | 201.2 | 11 | 8.00 |
| spreiding-gemengd | stdlib --order | 191.5 | 85.5 | 86 | 664.7 | 0 | 0.60 |
| spreiding-gemengd | stdlib --assign | 136.1 | 65.4 | 72 | 360.5 | 3 | 180.00 |
| spreiding-gemengd | pyvroom | 135.9 | 69.9 | 82 | 226.7 | 11 | 173.82 |
| spreiding-gemengd | ortools | 136.4 | 67.5 | 79 | 238.6 | 6 | 8.00 |

Onevenwicht = leerlingen op de volste bus min leerlingen op de leegste, lege bussen meegerekend.

De drie `--assign`-rijen van stdlib zijn afgekapt: `perturbaties=0, gestopt door max_seconds`. De lokale zoektocht was na drie minuten nog bezig. Het resultaat hangt daardoor af van de machinesnelheid. Op deze machine is de langste rit toch gelijkwaardig aan pyvroom en OR-Tools.

![Rekentijd van volgorde en verdeling](images/solver-bench-runtime.png)

## Installatie en omvang

Gemeten in deze `bench`-omgeving (macOS, arm64). Niets hiervan staat in `project.dependencies` (die lijst is leeg) en niets gaat mee in de plugin.

| Onderdeel | Versie | Schijf |
|---|---|---:|
| stdlib (`busroutes/optimize.py`) | — | 455 niet-lege regels, geen extra pakket |
| OR-Tools | 9.15.6755 | 65,5 MiB |
| pyvroom | 1.15.2 | 10,2 MiB |
| numpy (vereist door pyvroom) | 2.5.3 | 21,7 MiB |
| pandas (vereist door pyvroom) | 3.0.6 | 44,4 MiB |
| matplotlib (alleen de grafieken) | 3.11.2 | 26,6 MiB |

Scripts, niet-lege regels: `bench_full.py` 497, `bench_solvers.py` 213, `bench_charts.py` 185, `bench_matrix.py` 127.

## Niet aangeroepen

- TomTom `evaluate` zonder `--offline`. Er is geen reden credits te spenderen: de ontbrekende paren zouden eerst aangekocht moeten worden, en deze vergelijking moet juist zonder netwerk herhaalbaar zijn.
- De publieke VROOM-demo (`solver.vroom-project.org`). Die rekent met OSRM, niet met deze matrix.
- Google Route Optimization. Geen GCP-project; het objectief is vlootkost.
