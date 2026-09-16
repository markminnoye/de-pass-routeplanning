---
name: scenario-evaluator
description: Use when asked to doorrekenen, simuleren, visualiseren of vergelijken van schoolbus-scenario's voor "de pass" (Hoegaarden) — routes op een kaart zien, HTML-kaart, Leaflet-map, rittijd per kind, kilometers, bezetting, aankomsttijden, een bus naar een streek (bv. Leuven), vaste opstapplaatsen, of een andere verdeling van kinderen over de bussen.
---

# Scenario-evaluator — schoolbusroutes "de pass"

**Doel:** een HTML-kaart waarop de schoolbusroutes zichtbaar zijn. De gebruiker moet de
ritten *zien* (lijnen, stops, school, aankomst/instaptijden). Cijfers en een
vergelijkingstabel horen erbij; de kaart is het hoofddeliverable.

Rekent een door een mens (of jou) bedacht scenario door met TomTom-reistijden. Dit is
**geen solver** — de verdeling van kinderen over bussen bedenkt de gebruiker (of jij, in
overleg); deze skill rekent een gegeven verdeling door en maakt scenario's onderling
vergelijkbaar.

De skill bevat een zelfstandige Python-tool (`references/busroutes/`, geen dependencies
buiten de standaardbibliotheek — werkt overal waar `python3` beschikbaar is, ook in de
cloud-werkruimte). Je hoeft niets te installeren.

## Versie-check (eenmaal per sessie)

Doe dit aan het begin van een sessie waarin je scenario's doorrekent, of wanneer de
gebruiker naar de versie of een update vraagt. Niet bij elke follow-up.

1. Lees de lokale versie uit `.claude-plugin/plugin.json` in de pluginwortel (veld
   `version`).
2. Staat er geen veld `repository` (GitHub-URL), of lukt het netwerk niet: **stil
   doorgaan**. Niet blokkeren, niet gissen.
3. Haal `https://api.github.com/repos/<owner>/<repo>/releases/latest` op. `owner/repo`
   komt uit `repository` (`https://github.com/owner/repo`). Pre-releases en drafts
   tellen niet (deze endpoint slaat ze over).
4. Vergelijk semver: tag `v0.1.0` = `0.1.0`. Alleen een **nieuwere** Release is een
   update. Bij gelijk of geen Release: niets zeggen, doorwerken.
5. Is er een nieuwere versie: één alinea met het versienummer, de download
   `https://github.com/<owner>/<repo>/releases/latest/download/de-pass-routeplanning.plugin`,
   en de instructie de oude plugin in Cowork te verwijderen en dit bestand te
   installeren. Overschrijf de geïnstalleerde plugin niet zelf. Daarna pas het scenario.

## Eenmalige setup (per sessie/werkruimte)

1. Kies een vaste werkmap, bv. `/tmp/de-pass-routeplanning/` (of een map die de gebruiker
   aanwijst als ze dit blijvend willen bewaren buiten deze sessie). Kopieer er **eenmalig**
   de map `references/busroutes/` naartoe zodat de structuur wordt:
   ```
   <werkmap>/
   ├── busroutes/           (gekopieerd uit references/busroutes/)
   ├── .env                 (TOMTOM_API_KEY=...)
   ├── docs/samples/        (school.json, students.json, buses.json — zie hieronder)
   ├── scenarios/           (scenario-json's)
   ├── out/                 (wordt aangemaakt bij het doorrekenen)
   └── .cache/               (tomtom/ en overpass/, wordt automatisch aangemaakt)
   ```
   Bestaat de werkmap al (van een vorige beurt in dezelfde sessie)? Hergebruik ze — niet
   opnieuw kopiëren, en zeker de `.cache/` (TomTom én Overpass) en `.env` niet overschrijven.

2. **TomTom-sleutel.** Vraag de gebruiker om hun eigen `TOMTOM_API_KEY` als die nog niet in
   `<werkmap>/.env` staat (gratis aan te maken op developer.tomtom.com). Schrijf hem naar
   `<werkmap>/.env` als `TOMTOM_API_KEY=...` — nooit elders loggen of tonen. Zonder geldige
   sleutel faalt elke aanroep met een duidelijke foutmelding; meld dat dan, gok niet.

3. **Schooldata.** Vraag naar (of laat de gebruiker aanleveren): het adres/coördinaten en
   gewenste aankomsttijd van de school, de leerlingenlijst (adres/coördinaten per kind) en
   de buscapaciteiten. Schrijf deze naar `docs/samples/school.json`, `students.json` en
   `buses.json` in de werkmap. Schema en voorbeeld: `references/data-schema.md`.

   **Privacy — dit zijn nu echte adressen van minderjarigen.** Nooit delen buiten wat nodig
   is voor deze taak, nooit naar een andere dienst sturen dan TomTom (de geocoding/routing),
   en de gebruiker erop wijzen dat de werkmap (incl. `.cache/tomtom/`, dat ruwe coördinaten
   bevat) lokaal blijft en niet zomaar gedeeld moet worden.

## Werkwijze

1. **Scenario schrijven** als `scenarios/<naam>.json`. Formaat en regels:
   `references/data-schema.md`. Kernpunten: elke leerling exact één keer, aantal
   instappers per bus ≤ capaciteit, `ordering: "auto"` (evaluator bepaalt volgorde) of
   `"given"` (jij/gebruiker bepaalt volgorde) — per bus overschrijfbaar.

2. **Doorrekenen.** De referentiedatum is **verplicht** — zonder vaste datum schuift
   `departAt` elke dag mee, vervalt de TomTom-cache dagelijks en zijn scenario's niet
   vergelijkbaar. Kies één representatieve schooldag (bv. de eerstvolgende maandag) en
   hergebruik die voor de hele sessie:
   ```bash
   cd <werkmap>
   BUSROUTES_REFERENCE_DATE=<YYYY-MM-DD> python3 -m busroutes.cli evaluate scenarios/<naam>.json
   ```
   Output: `out/<naam>/metrics.json`, `routes.geojson`, `transit.geojson`, **`map.html`**.
   `map.html` is een volledige HTML-pagina (Leaflet): busroutes, stops met volgnummer,
   school, zijbalk met tijden, plus een laag OV-haltes (De Lijn, TEC, NMBS) aan/uit.
   Overlay uit Overpass (`.cache/overpass/`); faalt Overpass, dan gaat de evaluatie door
   (kaart zonder overlay). Onderaan meldt de CLI het TomTom-verbruik.

   Twijfel je of een run duur wordt? `--dry-run` haalt niets op en telt alleen:
   ```bash
   BUSROUTES_REFERENCE_DATE=<YYYY-MM-DD> python3 -m busroutes.cli evaluate scenarios/<naam>.json --dry-run
   ```

3. **Vergelijken** van meerdere scenario's:
   ```bash
   python3 -m busroutes.cli compare out/*/metrics.json
   ```
   Geeft een markdown-tabel (langste/gem./mediaan rit, ritten > 60 min, max. thuis→stop,
   totale rijtijd, km, bezetting, vroegste vertrek, aantal gebruikte bussen).
   Verander per vergelijking bij voorkeur **één ding** t.o.v. een referentiescenario, of
   vergelijk alleen de gewijzigde bus(sen) (`metrics.json` → `buses[]`) — anders vergelijk
   je appels met peren.

4. **Rapporteren — in deze volgorde, altijd allebei:**
   1. **De kaart.** Toon `out/<naam>/map.html` als HTML-pagina (in Claude: artifact). Niet
      alleen het pad noemen, niet samenvatten als markdown-schets, niet vervangen door de
      TomTom-connector (dynamic-map/static-map). Leaflet-CSS zit in de pagina; JS komt van
      cdnjs — de artifact-viewer kan die kaart renderen. Bij meerdere scenario's: de kaart
      van elk scenario (of minstens van de twee die je vergelijkt).
   2. **De tijden.** Compare-tabel of samenvatting: langste en gemiddelde rit per kind
      (doorslaggevend — niet km of totale rijtijd). Verschuift de winst tussen groepen
      kinderen, toon de betrokken bus per stop (`buses[].stops[]`: `ride_min`, `arrival`).

## Interpretatie — vermeld dit waar het speelt

- Rittijd = van instappen tot aankomst school. Thuis→opstapplaats zit er **niet** in;
  `to_stop_km` per kind en `max_to_stop_km` tonen hoeveel er naar de ouders verschuift.
  Een opstapplaats die van de school weg ligt maakt de rittijd mooier dan de echte
  deur-tot-school-tijd.
- `"ordering": "auto"` minimaliseert routelengte per bus, niet rittijd per kind: kinderen
  die vroeg instappen en daarna ver meerijden krijgen lange ritten. Kijk naar `ride_min`
  per stop; wil je een andere volgorde, geef die bus `"ordering": "given"`.
- De volgorde bij `"auto"` komt standaard uit **TomTom-reistijden**, wat een nieuw scenario
  ~1500 transacties kost. Wil je snel veel varianten aftasten, dan geeft `--ordering
  haversine` dezelfde heuristiek op hemelsbrede afstanden voor 7 transacties, maar met 4 tot
  13 % meer rijtijd (tot +20 min op één bus) omdat het geen eenrichtingsstraten of omwegen
  ziet. Rapporteer dan expliciet dat de cijfers een benadering zijn en reken de uiteindelijke
  keuze over met de default. `metrics.json` → `settings.ordering_strategy` houdt bij welke
  van de twee gebruikt is; vergelijk nooit een `haversine`-scenario met een `matrix`-scenario.
- TomTom rekent forse keer-penalty's (U-turns) bij deur-aan-deur ophalen in dorpsstraten;
  dat kan ritten onnodig langer maken t.o.v. opstapplaatsen op een doorgaande weg.
- Nieuwe routes/matrixcellen vragen een TomTom-call. Antwoorden worden gecachet in
  `.cache/tomtom/` (routes per aanvraag, matrixcellen per punt-paar), dus een scenario dat
  dezelfde punten anders over de bussen verdeelt is daarna gratis. Een gratis TomTom-sleutel
  geeft 2.500 requests per dag en een nieuw scenario kost er standaard ~1.500: twee nieuwe
  scenario's op één dag passen er dus niet in.

## Kosten laag houden

De gebruiker betaalt zelf per TomTom-request, dus:

- **Bewaar `.cache/`.** Kies een werkmap die de sessie overleeft en wijs de gebruiker
  erop dat wegwerpen van `.cache/tomtom/` alles opnieuw laat afrekenen bij TomTom. `.cache/overpass/`
  is gratis om opnieuw te vullen maar scheelt Overpass-calls. Een tijdelijke map zoals
  `/tmp/...` is prima binnen één sessie, niet als blijvende keuze — vraag bij een tweede
  sessie of de vorige werkmap er nog is.
- **Vraag het de gebruiker** voor je aan een reeks nieuwe scenario's begint: exact rekenen
  (default, ~1.500 per scenario) of eerst breed verkennen met `--ordering haversine` (7 per
  scenario). Loop niet stil het dagplafond op.
- **Overweeg de puntmatrix één keer in bulk te kopen** als er veel scenario's aankomen: alle
  punten onderling kost ~7.000 transacties en daarna is elk scenario exact én gratis. Zie
  `docs/data-en-tooling-opties.md`.
- **Gebruik `--no-cache` niet** om iets te "verversen"; dat rekent TomTom opnieuw aan én haalt Overpass opnieuw op.
  Wil je andere verkeersomstandigheden, verander dan de referentiedatum of `--traffic`.
- Bij twijfel eerst `--dry-run`, en meld de raming aan de gebruiker voor je een dure run doet.

## Veelgemaakte fouten

- Geen referentiedatum meegeven → de CLI stopt met een fout en een voorstel; kies één datum
  en hergebruik die voor de hele vergelijking.
- Vergelijken met verschillende `BUSROUTES_REFERENCE_DATE` of `ordering_strategy` → cijfers
  niet vergelijkbaar.
- `ScenarioError: niet toegewezen: ...` → elke leerling moet op precies één bus staan.
- Meerdere bussen tegelijk veranderd en dan het totaal vergeleken in plaats van de
  betrokken bussen apart te bekijken.
- Een scenario indienen zonder eerst `docs/samples/*.json` (school/leerlingen/bussen) in
  de werkmap te zetten — dat geeft direct een foutmelding bij het inladen.
- Alleen cijfers of een tabel rapporteren zonder `map.html` als HTML-pagina te tonen.
- De scenario-kaart vervangen door een TomTom-static-map, markdown-schets of GeoJSON-dump.

## Optioneel: TomTom Maps-connector

Is de TomTom Maps-connector geïnstalleerd in deze sessie? Gebruik die dan voor lichte,
interactieve vragen die niet de hele evaluatie nodig hebben:

| Vraag | Gebruik |
|---|---|
| Coördinaten van een nieuw adres/opstapplaats opzoeken | connector: geocode/fuzzy-search |
| "Hoe lang is het van X naar de school om 7u30?" (één route, snel) | connector: routing |
| Kaart van een doorgerekend scenario | **altijd** `out/<naam>/map.html` — nooit de connector |
| Een scenario doorrekenen of vergelijken (meerdere bussen) | **altijd** de `busroutes`-CLI hierboven — nooit alle routes van een scenario los via de connector |

Geen connector geïnstalleerd? Geen probleem — de CLI hierboven volstaat voor alles wat
deze skill doet; de connector is puur een handig extraatje voor losse vragen.
