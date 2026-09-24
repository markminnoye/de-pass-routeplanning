# SR-68 — OR-Tools-volgorde en de langste kinderrit

Linear SR-68 (23/09/2026) meldt dat een OR-Tools-TSP op bus 3 een langere maximale kinderrit geeft dan de automatische nearest-neighbour-volgorde. Plugin in het ticket: v0.2.0. OR-Tools in het ticket: 9.15.6755, `PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`, 10 s, depot = school, boogkost = hemelsbreed / 40 km/u.

De product-solver is sindsdien de stdlib in `busroutes/optimize.py`. Die blijft de default. Dit document legt vast wat de code doet, wat er op `docs/samples` uit de evaluator komt, en welke wijziging wel en niet helpt.

## Conclusie

Geen defect in `optimize`, en geen verkeerde depot- of tijdconversie in de evaluator. Drie verschillende doelen lopen door elkaar:

| Pad | Waar | Wat het minimaliseert |
|---|---|---|
| `optimize --order` en `ordering: auto` met strategie `matrix` (default sinds 0.3.0) | `order_stops_for_bus` | `(langste kinderrit, som van de kinderritten, totale rijtijd)`. Rit = vertrek aan de stop tot aankomst op school, eigen stilstand niet mee, latere stilstand wel |
| `ordering: auto` met `--ordering haversine` (default in v0.2.0, nu een verkenmodus) | `busroutes/ordering.py` | Lengte van school → stops → school (nearest neighbour van de school terug, daarna 2-opt op die padkost) |
| Bench-OR-Tools | `scripts/bench_solvers.py` | Boog = matrix-seconden + stilstand aan de oorsprong, plus `GlobalSpanCost` 100 op de duur van de bus (depot-vertrek tot depot-terugkomst). Niet de rit vanaf instappen |
| Klassieke TSP uit het ticket | niet in de plugin | Som van de bogen op een gesloten lus school → stops → school. Een tour en zijn omgekeerde zijn even lang. De eerste oplossing kiest de stop dicht bij school; dat is niet korter |

De evaluator scoort altijd de kinderrit. OR-Tools rekent die gesloten lus: depot en eindpunt zijn allebei de school (`RoutingIndexManager` met één depot). Op een symmetrische afstand zijn beide richtingen even lang, dus de solver mag de stops dicht bij school eerst zetten. Voor een bus die naar school rijdt is ver eerst dezelfde busafstand en een kortere langste kinderrit. Op de Tienen-mix (`s061`–`s070` plus `s023` en `s009`) is dat 13,2 km beide kanten, en 21,7 minuten langste rit tegen 26,9 minuten. De echte verbetering is een open rit die op school eindigt, zonder lege heenrit vanaf school; die zit niet in deze code en wordt apart opgevolgd, niet in deze release.

`school-distance-desc` (verste stop eerst, verder geen zoektocht) is op de Tienen-mix hieronder slechter dan de stdlib-solver: de volgorde binnen de verre cluster zigzag dan. Die modus is niet toegevoegd.

## Ticketcijfers komen niet terug op deze stops

Het ticket noemt scenario `bus3-tienen-merged`: 10 kinderen uit Tienen + 2 uit Hoegaarden-centrum, en deze volgorde:

`s014, s013, s008, s003, s010, s001, s006, s004, s002, s009, s007, s005`

In `docs/samples/students.json` zijn dat twaalf leerlingen uit **hoegaarden-centrum**, geen Tienen. Afstand tot de school (`50.778160, 4.896000`; het ticket noemt `50.7782, 4.8963`, 22 m ervandaan): 177 m (`s009`) tot 1312 m (`s004`). Het scenario zelf staat niet in de repo. `load_scenario` eist bovendien dat elke leerling van het pakket op precies één bus zit; het JSON-fragment in het ticket is tegen `docs/samples` geen geldig scenario.

`evaluate --offline` op alleen die twaalf stops, referentiedatum 2026-09-24, stilstand 30 s + 10 s per leerling, matrixcellen van het voorbeeldpakket (de stops liggen samen op bus 1 van `regiobus-per-zone`, dus de paren bestaan):

| Volgorde | Langste rit (min) | Gemiddelde | Ritten > 60 min | Rijtijd bus (min) |
|---|---:|---:|---:|---:|
| Ticket, `ordering: given` | 37,1 | 20,8 | 0 | 33,3 |
| `auto` + haversine | 33,4 | 17,5 | 0 | 27,5 |
| `auto` + matrix (rittijd-solver) | 22,1 | 12,3 | 0 | 17,9 |

84,5 en 92,7 minuten komen hier niet voor. Een online `evaluate` van de twintig Hoegaarden-leerlingen op bus 1 in het verwachte bestand komt op 57,0 minuten langste rit; twaalf van die punten halen 84 minuten niet via dezelfde wegen.

OR-Tools 9.15.6755 op deze coördinaten, zelfde eerste oplossing en local search als het ticket, 10 s, boogkost = afgeronde meters of seconden bij 40 km/u, mét en zonder `GlobalSpanCost` 100, levert de ticketvolgorde niet. Held-Karp op meters: optimum **4242 m**. De ticketvolgorde is **8382 m**, bijna het dubbele, dus ook geen TSP-optimum op dit pakket. De bench-variant (matrixcellen + stilstand + `GlobalSpanCost`, 1 s) evenmin.

De hypothese "deze volgorde is de kortste busrit, en daarom slechter voor de kinderen" klopt niet voor de gepubliceerde id's. Op de Tienen-mix hieronder is dicht-eerst ook niet korter dan ver-eerst: het is dezelfde lus, de andere kant op.

## Waar het mechanisme wel zichtbaar is

Tien Tienen-leerlingen `s061`–`s070` plus de twee unieke Hoegaarden-punten het dichtst bij school (`s023` 173 m, `s009` 177 m). Kosten voor de zoektocht: hemelsbreed / 40 km/u, stilstand zoals de evaluator. Zelfde functie als `score_bus`.

| Volgorde | Langste rit (min) | Bus (s) | Eerste stops |
|---|---:|---:|---|
| Nearest neighbour, van de school terug (zonder 2-opt) | 21,5 | 1203 | ver, Tienen; `s009` en `s023` laatst |
| Zelfde zaad + 2-opt op padkost (`order_stops`, haversine-auto) | 27,0 | 1195 | `s009`, `s023` |
| Klassieke TSP, richting "eerst dicht bij school" | 26,9 | 1190 | `s009`, `s023` |
| Die TSP omgekeerd (zelfde 1190 s bus) | 21,7 | 1190 | Tienen eerst |
| `order_stops_for_bus` | 21,4 | 1280 | Tienen eerst, `s009` laatst |
| Afstand tot school, aflopend | 27,2 | 1689 | verste eerst, maar zigzag in Tienen |

De twee TSP-richtingen zijn allebei 13.201 m (13,2 km) en 1190 s bus. Dicht eerst heeft een langste kinderrit van 26,9 minuten, ver eerst 21,7 minuten. 2-opt op een ander zaad wint 8 seconden bus tegenover nearest neighbour (1195 s tegen 1203 s) en zet daarbij de school-nabije stops vooraan; dat is een andere tour, niet het bewijs dat dicht-eerst korter is dan zijn omgekeerde.

De voorbeeldmatrix heeft geen paren tussen Tienen en Hoegaarden, dus `evaluate --offline` stopt op die mix (`OfflineError`, één ontbrekende leg van 3486 m). Met de echte cellen waar ze bestaan, en voor die ene leg de lijn uit `docs/solver-benchmark.md` (`seconden = max(1, afgerond(277,7976 + 0,075533 × meter))`), zelfde stilstand:

| Richting van de TSP-tour | Langste rit (min) | Ritten > 60 | Rijtijd bus (min) |
|---|---:|---:|---:|
| Eerst `s009`, `s023` | 68,2 | 2 | 62,1 |
| Omgekeerd (Tienen eerst) | 63,0 | 1 | 62,6 |
| Afstand tot school, aflopend | 76,5 | 3 | 82,4 |

De twee tourrichtingen delen die ontbrekende leg. Het verschil van 5 minuten op de langste rit komt uit de volgorde, niet uit de geschatte leg. 84,5 tegen 92,7 blijft een andere rit (andere stops, of `calculateRoute` in plaats van matrixcellen). Het teken van het verschil is hetzelfde: eerst de school-nabije stops maakt de langste kinderrit langer, bij bijna dezelfde bus.

## Aanbeveling

1. **Default laten.** `optimize --order` en `ordering: auto` met matrix minimaliseren al de langste kinderrit. Wie de tabel uit het ticket wil, draait die, niet een TSP naast de plugin.
2. **TSP en de bench niet als kinderrit verkopen.** De benchmark zegt dit al voor pyvroom en OR-Tools. Haversine-auto hoort in dezelfde categorie: padkost. De moduletekst van `ordering.py` zei nog dat OR-Tools die heuristiek zou vervangen; dat is de stdlib-solver, en alleen op de matrix-strategie.
3. **`school-distance-desc` niet toevoegen.** Op de ticket-id's verslaat het de ticketvolgorde (29,8 tegen 37,1 min offline), op de Tienen-mix verliest het van nearest neighbour én van de rittijd-solver, omdat de verre stops onderling niet geordend worden.
4. **Haversine-2-opt niet stil omzetten naar de rittijd-score.** Dat is een benoemde verkenmodus. De meting "4–13 % langere ritten dan matrix" gaat over padkost. Wie de kinderrit wil op een hemelsbrede schatting, kan `order_stops_for_bus` met een hemelsbrede reistijd aanroepen; dat is geen nieuwe CLI-vlag tot iemand die modus echt naast matrix wil.

Vastgelegd in `tests/test_sr68_objective.py`: op de ticket-id's is de matrix-ordening strikt korter in langste rit dan haversine-auto en dan de ticketvolgorde; op de Tienen-mix is de rittijd-score strikt beter dan `order_stops` op dezelfde hemelsbrede seconden.
