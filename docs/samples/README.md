# Fictieve testset

Deze map is het **voorbeeld-datapakket**: school, leerlingen, bussen, opstapplaatsen
én de reistijdmatrix. De evaluator gebruikt het als default (`BUSROUTES_DATA_DIR` /
`--data docs/samples`). Een eigen pakket volgt dezelfde layout.

Alles hierin is **verzonnen** en deterministisch gegenereerd door
`scripts/generate_testset.py` (vaste seed). Er staan geen echte adressen of namen in;
de punten liggen willekeurig verspreid rond echte dorpskernen in de regio Hoegaarden en
worden daarna op de dichtstbijzijnde gewone straat gelegd (TomTom reverse geocoding,
`roadUse=LocalStreet,Arterial`) — anders klikt de routering ze vast aan voetpaden of
veldwegen en worden de reistijden onzin.
Regenereren: `uv run python scripts/generate_testset.py` (byte-identieke output; de
reverse-geocoding zit in `.cache/tomtom/`, dus enkel de allereerste keer is een
`TOMTOM_API_KEY` en netwerk nodig).

`expected/*.metrics.json` is de TomTom-referentie van de drie scenario's (DoD:
regressie + reproduceerbaarheid). Controleren: `BUSROUTES_REGRESSION=1 uv run pytest
tests/test_regression.py`. Vernieuwen na een bewuste wijziging: de drie scenario's
opnieuw doorrekenen met `BUSROUTES_REFERENCE_DATE` gelijk aan de datum in het
bestand en `out/<naam>/metrics.json` hierheen kopiëren.

`expected/offline/*.metrics.json` is de offline-referentie (`evaluate --offline`);
die draait altijd in pytest, zonder TomTom-key.

Zie AGENTS.md, sectie "Privacy": echte leerlingdata komt hier nooit in.

## Bestanden

### `school.json`

```json
{"id": "school", "name": "...", "lat": 50.778, "lon": 4.896, "target_arrival": "08:20"}
```

`target_arrival` is de gewenste aankomsttijd van alle bussen aan de school (lokale tijd,
Europe/Brussels). De evaluator rekent hiervan terug naar ophaaltijden en vertrektijd per bus.
De echte beltijd is nog te bevestigen door de school.

### `students.json`

Lijst van `{"id": "s001", "lat": ..., "lon": ..., "zone": "tienen"}`. 140 leerlingen,
ids per zone gegroepeerd (s001–s030 = hoegaarden-centrum, enz.). `zone` is enkel een label
om scenario's mee op te bouwen; de evaluator gebruikt het niet.

### `buses.json`

Lijst van `{"id": "bus1", "capacity": 30, "start": "school"}`. Capaciteit 30 is de aanname
van Mark (14/09/2026) als fysieke bovengrens voor alle bussen — geen streefcijfer: de doelfunctie
blijft rittijd per kind, dus scenario's hoeven een bus niet vol te zetten. Per bus aanpasbaar. `start` is waar de bus zijn
rit begint: `"school"` of `{"lat": ..., "lon": ...}` (bv. een stelplaats). Rittijd per kind
hangt hier niet van af, totale rijtijd/km wel.

### `pickup_points.json`

Vaste opstapplaatsen die in de voorbeeldscenario's gebruikt worden (`id`, `lat`, `lon`,
`name`), al op de straat gesnapt. Hergebruik deze coördinaten in eigen scenario's zodat
resultaten vergelijkbaar blijven.

### `matrix/`

Gecachete TomTom-reistijden per oorsprongspunt: `matrix/<digest>/<lat,lon>.json`
(zelfde formaat als de oude `.cache/tomtom/cells/`). `evaluate --offline` leest
alleen deze map; ontbrekende paren falen met het commando
`busroutes data fetch-matrix --dry-run`. Status: `busroutes data status`.

### Output (`out/<naam>/metrics.json`)

`summary` bevat de criteria uit de brief plus `rides_over_60_min`, `rides_over_90_min`,
`max_to_stop_km` en `students_with_to_stop_over_1km`; `students[]` heeft per kind
`ride_min` (van instappen tot school) en `to_stop_km` (hemelsbreed thuis→stop, 0 bij een
thuisstop — die verplaatsing zit **niet** in `ride_min`).

### `scenarios/*.json` — scenario-formaat

```json
{
  "name": "regiobus-per-zone",
  "description": "vrije tekst",
  "ordering": "auto",
  "buses": [
    {
      "bus_id": "bus4",
      "stops": [
        "s041",
        {"id": "pp-tienen-station", "lat": 50.8085, "lon": 4.9245, "name": "Tienen station",
         "students": ["s042", "s043"]}
      ]
    }
  ]
}
```

- Een **stop** is een locatie plus de leerlingen die daar instappen.
  - Een string (`"s041"`) is een thuisstop: locatie = het punt van die leerling, één instapper.
  - Een object is een **vaste opstapplaats** met eigen coördinaten en een lijst `students`.
- `ordering` (scenario-breed, per bus te overschrijven met `"ordering"` in het bus-object):
  - `"given"` — de bus rijdt de stops exact in de opgegeven volgorde.
  - `"auto"` — de evaluator bepaalt zelf een volgorde per bus (heuristiek op de TomTom-matrix;
    minimaliseert routelengte, niet rittijd per kind).
- Regels die de evaluator afdwingt: elke leerling exact één keer toegewezen, aantal instappers
  per bus ≤ `capacity` (30), elke `bus_id` bestaat in `buses.json`. Overtreding = foutmelding.

### Meegeleverde scenario's

| Scenario | Idee |
|---|---|
| `spreiding-gemengd` | Negatieve referentie: leerlingen willekeurig over de bussen, zones gemengd. |
| `regiobus-per-zone` | Elke bus bedient één streek; bus6 = regiobus Leuven/Bierbeek, bus7 = Landen/Linter/Zoutleeuw. Ophalen aan huis. |
| `opstapplaatsen` | Zoals per-zone, maar Tienen via station + Grote Markt en Leuven via het station. |

Zones en aantallen: hoegaarden-centrum 30, tienen 24, leuven 14, meldert 10, boutersem 10,
landen 10, outgaarden 8, hoksem 6, jodoigne 6, kumtich 6, bierbeek 6, linter 6, zoutleeuw 4.
