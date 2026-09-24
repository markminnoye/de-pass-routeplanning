---
name: scenario-evaluator
description: Use when asked to doorrekenen, simuleren, visualiseren, vergelijken of optimaliseren van schoolbus-scenario's voor "de pass" (Hoegaarden) — HTML-kaart, rittijd per kind, een bus naar een streek (Leuven), vaste opstapplaats, volgorde per bus, verdeling over bussen, of een ontbrekend matrixpaar (OfflineError).
---

# Scenario-evaluator

**Doel:** `out/<naam>/map.html` als HTML-pagina (in Claude: artifact). De gebruiker moet de ritten zien. Daarna de compare-tabel. De kaart is het hoofddeliverable.

Eén tabel, één commando per vraag. De tabel is de enige keuze.

## Beslissingstabel

| Gebruiker wil | Commando | TomTom-key |
|---|---|---|
| Scenario bedenken of aanpassen | scenario-JSON (`skills/scenario-evaluator/references/data-schema.md`) | nee |
| Snel weten of het beter is | `evaluate --offline` | nee |
| Volgorde per bus verbeteren | `optimize --order` | nee |
| Beste verdeling (vaste bussen/stops mogen) | `optimize --assign` | nee |
| Definitieve cijfers en kaart met echte wegen | `evaluate` | ja |
| Vergelijken | `compare` | nee |
| Nieuw punt | `data add-points` | ja (±280 transacties per punt) |
| Weten wat het pakket bevat of wat ontbreekt | `data status` | nee |

Aanroep, vanaf de repo-wortel: `uv run busroutes <commando>`. Een losse reistijd is een scenario van die rit, daarna `evaluate --offline`.

## Werkwijze

Altijd deze volgorde. Eén vaste referentiedatum voor de hele vergelijking (`BUSROUTES_REFERENCE_DATE` of `--reference-date`). In het voorbeeldpakket is dat `2026-09-15`.

1. `uv run busroutes data status`
2. Schrijf `scenarios/<naam>.json`. Schema: `skills/scenario-evaluator/references/data-schema.md`. Elke leerling exact één keer.
   - "Maak een bus naar een streek" of "eerst naar Leuven": scenario-JSON. Een voorgeschreven volgorde zet je op die bus als `"ordering": "given"`.
   - "Verbeter de volgorde van bus 6": kopieer het scenario, zet `"pinned": true` op elke andere bus, daarna `optimize --order`.
   - "Beste verdeling, bus1 vast": `"pinned": true` op die bus. Stops die op hun bus blijven: `pinned_stops`. Daarna `optimize --assign`.
3. `BUSROUTES_REFERENCE_DATE=2026-09-15 uv run busroutes evaluate --offline scenarios/<naam>.json`  
   Cijfers en die kaart zijn een schatting (matrix-tijden, rechte lijnen, km geschat). `metrics.json` heeft `"mode": "offline"`. Niet als definitief presenteren.
4. Alleen als de tabelrij optimaliseren is: `optimize --order` of `optimize --assign`. Geen TomTom-key. `--reference-date` is voor `optimize` niet nodig. Output: `scenarios/<naam>-optimized.json` plus vóór/na op stdout. Daarna stap 3 op dat nieuwe bestand.  
   `--assign` op een volledige schoolset (tot ongeveer 150 stops) kan enkele minuten duren en hoort binnen vijf minuten klaar te zijn. Gebruik daarvoor `--max-seconds 300`. Dat is een noodrem: als hij bijt, staat op stderr dat het resultaat van de machinesnelheid afhangt. `--max-perturbations` (default 1000) is het reproduceerbare stoppunt. Stdout meldt `Perturbaties: N (gestopt door: …)`; neem die regel op in het antwoord.
5. Pas dan, één keer: `BUSROUTES_REFERENCE_DATE=2026-09-15 uv run busroutes evaluate scenarios/<naam>.json`  
   Ongeveer 7 TomTom-calls. Zelfde datum. Dit zijn de definitieve cijfers en de kaart met echte wegen.
6. Toon `out/<naam>/map.html` als HTML-pagina. Daarna `uv run busroutes compare` op de `metrics.json`-bestanden. Doorslaggevend: langste en gemiddelde rit per kind.

Ontbreekt een matrixpaar (`OfflineError`, of `data status` toont ontbrekende paren): nogmaals `data status`, dan `uv run busroutes data fetch-matrix --dry-run`. Meld de raming en stop. Toon de offline-kaart die je al hebt, met het label schatting. Het voorbeeldpakket dekt de drie referentiescenario's per bus (`docs/samples/scenarios/`), niet de paren tussen bussen. Een nieuwe verdeling kan dus `OfflineError` geven ook al staan alle punten in het pakket. Vertrek voor een proef van zo'n referentie.

## Datapakket

`BUSROUTES_DATA_DIR` of `--data`, default `docs/samples/`. Die default is het fictieve voorbeeldpakket in deze repo (school, leerlingen, bussen, opstapplaatsen, `matrix/`). De plugin bevat geen datapakket. De school zet haar eigen map buiten de plugin en buiten git.

Echte leerlingdata nooit in git en nooit in de plugin. Een ad-hoc scenario hoort in `scenarios/`, niet in `docs/samples/scenarios/` en niet in `expected/`, tenzij Mark het als vaste referentie wil.

## Wat je nooit doet

- Geen andere solver of dienst zoeken. De tabel is de solver.
- De matrix niet opnieuw ophalen. `fetch-matrix` zonder `--dry-run` alleen nadat de gebruiker de raming goedkeurt. Niet stil terugvallen op `--ordering haversine`.
- Echte leerlingdata nooit in git of in de plugin.
- Offline-cijfers nooit als definitief presenteren. Definitief = de ene `evaluate` zonder `--offline`, en die `map.html`.
- De kaart niet vervangen door een pad, een schets of een andere kaart.
- Geen verdeling of volgorde met de hand verzinnen als de tabel `optimize` zegt.

## Rode vlaggen

| Gedachte | Doe in plaats daarvan |
|---|---|
| "Dit is geen solver, ik bedenk de verdeling." | `optimize --assign` |
| "Ik probeer een paar volgordes met de hand." | `optimize --order` |
| "Ik reken meteen met TomTom, offline sla ik over." | eerst `evaluate --offline` |
| "Haversine is goedkoop genoeg." | `evaluate --offline` |
| "Het paar ontbreekt, ik koop de matrix of ik schat hemelsbreed." | `data status` en `fetch-matrix --dry-run`, dan stoppen |
| "Offline is nauwkeurig genoeg om te rapporteren." | één `evaluate` zonder `--offline` |

## Interpretatie

Rittijd = instappen tot school, tenzij `direction` `from_school` is: dan van school tot uitstappen. Ontbreekt `direction`, dan is de rit naar school en stappen de verste kinderen eerst in. Een `"ordering": "given"` wordt niet omgedraaid. Thuis→stop zit er niet in (`to_stop_km`, `max_to_stop_km`). Een opstapplaats van de school weg maakt de rittijd korter dan deur-tot-school. Vergelijk alleen bij dezelfde referentiedatum en dezelfde modus. Verander per vergelijking één ding, of lees de gewijzigde bus in `buses[].stops[]` (`ride_min`, `arrival`).
