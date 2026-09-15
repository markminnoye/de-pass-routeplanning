---
title: TomTom-credits terugdringen in de scenario-evaluator
date: 2026-09-15
status: done
---

# TomTom-credits terugdringen

**Aanleiding:** de gratis TomTom-credits (Freemium: 2.500 non-tile requests per dag) waren op
na een handvol doorrekeningen. Zoekvraag: welke fouten of verbeteringen in de evaluator
kosten onnodig credits?

## Diagnose

De limieten in `docs/data-en-tooling-opties.md` stonden er wel (100/200/2500 cellen per
request), maar het **facturatiemodel** niet. Matrix Routing v2 rekent per aanvraag op basis
van de dimensies: `5 × max(origins, destinations)` zodra beide groter zijn dan 5, anders
`origins × destinations`. Een cel kost dus `5 / min(origins, destinations)` transacties.
Daardoor was de evaluator op de verkeerde grootheid geoptimaliseerd — "past onder 200 cellen"
in plaats van "kost zo weinig mogelijk".

Gevonden problemen, in volgorde van impact:

1. De matrix werd in **rijstroken** van `200 // aantal_destinations` rijen gesneden. Voor een
   bus met 20 kinderen 308 transacties waar vierkante blokken 220 kosten; bij 30 kinderen
   864 tegenover 480.
2. De matrix was **helemaal niet nodig**: hij bepaalde alleen de stopvolgorde, terwijl alle
   gerapporteerde tijden en km uit `calculateRoute` komen.
3. De cache zat **per aanvraag** in plaats van per punt-paar, dus één kind verplaatsen tussen
   twee bussen haalde beide matrices volledig opnieuw op.
4. `departAt` zat in de routecachesleutel met een **meeschuivende** referentiedatum
   (`None` = eerstvolgende weekdag), dus de routecache verviel elke dag en dezelfde input gaf
   morgen andere cijfers — in strijd met DoD 4.
5. Geen **raming en geen verbruiksrapport**: je zag pas achteraf dat het geld weg was.
6. Kleiner: destinations werden nooit gechunkt (breekt bij >200 bestemmingen), cachebestanden
   werden niet atomisch geschreven (afgebroken run → crash → `rm -rf .cache` → alles opnieuw
   betalen), en samenvallende leerlingpunten kregen elk een eigen stop.

## Wat er gebeurd is

- `busroutes/tomtom.py`: `matrix_transactions()` als expliciete facturatieformule;
  `plan_blocks()`/`_cheapest_split()` kiezen de goedkoopste blokvorm; matrixcache per
  punt-paar in `.cache/tomtom/cells/`; `_harvest_legacy()` vult die gratis uit de oude
  `.cache/tomtom/matrix/`; `Usage`-teller; atomische writes; afgebroken cachebestand wordt
  opnieuw opgehaald; identieke punten vallen samen.
- `busroutes/ordering.py` + `evaluate.py`: `OrderingStrategy` (`haversine` | `matrix`),
  default `haversine` (gratis), vastgelegd in `metrics.json` → `settings.ordering_strategy`.
- `busroutes/config.py`: referentiedatum verplicht met een fout die een datum voorstelt;
  `BUSROUTES_ORDERING` en `BUSROUTES_CACHE_DIR` erbij.
- `busroutes/cli.py`: `--ordering`, `--reference-date`, `--dry-run`, verbruiksrapport na een
  run, waarschuwing bij `--no-cache`.
- Docs: facturatiemodel in `docs/data-en-tooling-opties.md`, kostensectie in `SKILL.md`,
  `settings`-blok in `references/data-schema.md`, `.env.example` uitgebreid.

## Gemeten resultaat

Koude cache, de drie referentiescenario's samen: **5.934 → 21 transacties**. Per scenario
7 (één `calculateRoute` per bus) in plaats van ~2.000. Met `--ordering matrix` kost een
scenario 1.081–1.482 in plaats van 1.608–2.163.

Kwaliteitsprijs van de gratis ordening, gemeten met de echte TomTom-tijden uit de cache:
+3,8 % / +10,7 % / +13,3 % totale rijtijd op de drie scenario's, tot +20 min op één bus. Zie
`docs/data-en-tooling-opties.md` voor de tabel en de aanbevolen werkwijze (verkennen met
`haversine`, eindkeuze overrekenen met `--ordering matrix`, of één keer de volledige
139-puntsmatrix kopen voor 6.995 transacties waarna alles exact én gratis is).

De bestaande warme cache (65 matrixpayloads, 26 routes) is behouden: de drie
`docs/samples/expected/`-baselines reproduceren bit-identiek met `--ordering matrix` en
**nul** netwerkverkeer (gecontroleerd met een dode proxy, zodat een cache-misser geen credits
kon kosten).

## Daarna, niet gedaan

- `computeBestOrder=true` op `calculateRoute` als derde strategie: TomTom's eigen
  herschikking op het echte wegennet, één request per bus in plaats van een matrix. Harde
  limiet van 20 waypoints, dus een bus met 30 kinderen valt erbuiten — vraagt een fallback.
- Stops samenvoegen die binnen ~50 m van elkaar liggen (nu vallen alleen exact identieke
  punten samen). In de testset zitten o.a. s035/s038 op ~4 m en s044/s045 op ~25 m.
- Een voorgewarmde cache voor de fictieve testset meeleveren in de plugin, zodat een nieuwe
  sessie niet opnieuw begint te betalen.
