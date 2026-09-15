---
name: scenario-evaluator
description: Use when asked to doorrekenen, simuleren of vergelijken van schoolbus-scenario's voor "de pass" (Hoegaarden) — een bus naar een streek (bv. Leuven), vaste opstapplaatsen, andere verdeling van kinderen over bussen, rittijd per kind, km, bezetting, aankomsttijden, of een kaart van de routes.
---

# Scenario-evaluator

Rekent een door mens of agent bedacht scenario door via TomTom (Python/REST) en levert de
criteria uit de projectbrief: langste/gemiddelde rittijd per kind, totale rijtijd, km,
bezetting, vertrek- en aankomsttijden, plus een kaart. Geen solver: de indeling maak jij.

## Werkwijze

1. **Scenario schrijven** als `scenarios/<naam>.json` (ad-hoc; map is getrackt, commit als
   Mark het wil bewaren). Formaat: `docs/samples/README.md`. Kopieer een referentie uit
   `docs/samples/scenarios/` en pas aan. Bronnen: leerlingen per zone in
   `docs/samples/students.json` (`zone`), opstapplaatsen in `docs/samples/pickup_points.json`.
   Regels: elke leerling exact één keer, max. 30 per bus (`docs/samples/buses.json`;
   bovengrens, geen streefcijfer — niet alle 7 bussen hoeven gebruikt). `ordering: "auto"` als default;
   per bus overschrijfbaar met `"ordering": "given"` in het bus-object (dan geldt de
   opgegeven stopvolgorde voor die bus alleen).
   Zet een scenario **alleen** in `docs/samples/scenarios/` + `expected/` als Mark het als
   vaste referentie wil.
2. **Doorrekenen**, altijd met de referentiedatum van de bestaande outputs (anders vergelijk
   je verschillende verkeersdagen; de datum staat in `docs/samples/expected/*.metrics.json`
   onder `settings.depart_at_reference`):
   ```bash
   BUSROUTES_REFERENCE_DATE=2026-09-15 uv run busroutes evaluate scenarios/<naam>.json
   ```
   Output: `out/<naam>/metrics.json`, `routes.geojson`, `map.html`. Ontbreekt
   `out/<referentie>/` of wijkt `summary` af van `docs/samples/expected/<naam>.metrics.json`,
   reken die eerst (opnieuw) door met `... evaluate docs/samples/scenarios/<naam>.json`.
   Probeersels (bv. meerdere handmatige volgordes bij `given` — probeer er minstens twee)
   met `--out <scratchmap>` zodat `out/` alleen echte varianten bevat.
3. **Vergelijken**: `uv run busroutes compare out/*/metrics.json` → markdown-tabel (incl.
   aantal gebruikte bussen).
   Verander per scenario **één ding** t.o.v. een referentie, of vergelijk alleen de
   gewijzigde bus(sen) (`metrics.json` → `buses[]`); anders vergelijk je appels met peren.
4. **Rapporteren**: de `compare`-tabel (langste/gem./mediaan rit, ritten > 60 min, max.
   thuis→stop, totale rijtijd, km, bezetting, vroegste vertrek). Verschuift de winst tussen
   groepen kinderen (de ene groep korter, de andere langer), toon dan de gewijzigde bus per
   stop (`buses[].stops[]`: `ride_min`, `arrival` = instaptijd — bij een opstapplaats is
   "hoe vroeg moet je er staan" net zo relevant als de rittijd). Doorslaggevend is de
   kernvraag uit AGENTS.md: langste en gemiddelde rit per kind, niet km of totale rijtijd.
  `map.html` aanbieden (lokaal openen in de browser; tiles en OV-overlay laden niet in een artifact).
  De kaart heeft een laag "OV-haltes (De Lijn, TEC, NMBS)" die je kunt uitzetten.

## Interpretatie — vermeld dit waar het speelt

- Rittijd = van instappen tot aankomst school. Thuis→opstapplaats zit er **niet** in;
  `to_stop_km` per kind en `max_to_stop_km` tonen hoeveel er naar ouders verschuift. Een
  opstapplaats die van de school weg ligt (bv. Bierbeek-kinderen naar Leuven station) maakt
  de rittijd mooier dan de echte deur-tot-school-tijd.
- `auto` minimaliseert routelengte per bus, niet rittijd per kind: kinderen die vroeg
  instappen en daarna ver meerijden krijgen lange ritten. Kijk naar `ride_min` per stop; wil
  je een andere volgorde, geef die bus `"ordering": "given"`.
- TomTom rekent forse keer-penalty's (U-turns) bij deur-aan-deur in dorpsstraten; dat maakt
  ritten in `spreiding-gemengd`/`regiobus-per-zone` deels langer. Zie
  `docs/data-en-tooling-opties.md`, "Lessen uit de implementatie".
- Alleen fictieve data (AGENTS.md, Privacy). Nooit echte leerlingadressen invoeren.
- Nieuwe routes vragen TomTom-calls (key in `.env`, antwoorden gecachet in `.cache/tomtom/`);
  zonder key of netwerk faalt `evaluate` met een duidelijke fout — dan melden, niet gokken.

## TomTom MCP-connector vs. CLI

| Vraag | Gebruik |
|---|---|
| Coördinaten van een nieuwe opstapplaats | connector `tomtom-geocode` / `tomtom-fuzzy-search` → in het scenario-json |
| "Hoe lang is het van X naar de school om 7u30?" | connector `tomtom-routing` met `departAt` |
| Kaartbeeld in het gesprek | connector `tomtom-static-map` |
| Een scenario doorrekenen of vergelijken (meerdere bussen) | **altijd de CLI** — nooit 7 routes via de connector |

Geen connector? Coördinaten uit `docs/samples/pickup_points.json` hergebruiken of vragen.

## Veelgemaakte fouten

- Vergelijken zonder dezelfde `BUSROUTES_REFERENCE_DATE` → cijfers niet vergelijkbaar.
- `ScenarioError: niet toegewezen: ...` → elke leerling moet op precies één bus.
- Ad-hoc scenario in `docs/samples/` gezet → referentieset en regressietest vervuild.
- Meerdere bussen tegelijk veranderd en dan het totaal vergeleken.
