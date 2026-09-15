# Data- en scenarioformaat

Alle bestanden hieronder horen in `docs/samples/` in de werkmap (zie SKILL.md, "Eenmalige
setup"), behalve scenario's zelf die in `scenarios/` komen.

## `school.json`

```json
{"id": "school", "name": "de pass", "lat": 50.778, "lon": 4.896, "target_arrival": "08:20"}
```

`target_arrival` is de gewenste aankomsttijd van alle bussen aan de school (lokale tijd,
Europe/Brussels). De evaluator rekent hiervan terug naar ophaaltijden en vertrektijd per bus.

## `students.json`

Lijst van leerlingen:

```json
[
  {"id": "s001", "lat": 50.792, "lon": 4.911, "zone": "hoegaarden-centrum"},
  {"id": "s002", "lat": 50.804, "lon": 4.933, "zone": "tienen"}
]
```

`zone` is optioneel, enkel een label om scenario's mee op te bouwen — de evaluator gebruikt
het zelf niet.

## `buses.json`

Lijst van bussen:

```json
[
  {"id": "bus1", "capacity": 30, "start": "school"},
  {"id": "bus2", "capacity": 30, "start": {"lat": 50.77, "lon": 4.88}}
]
```

`capacity` is een bovengrens, geen streefcijfer — de doelfunctie blijft rittijd per kind,
dus een scenario hoeft een bus niet vol te zetten. `start` is waar de bus zijn rit begint:
`"school"` of expliciete coördinaten (bv. een stelplaats). Rittijd per kind hangt hier niet
van af, totale rijtijd/km wel.

## Scenario-formaat (`scenarios/<naam>.json`)

```json
{
  "name": "regiobus-per-zone",
  "description": "vrije tekst",
  "ordering": "auto",
  "buses": [
    {
      "bus_id": "bus1",
      "stops": [
        "s001",
        {
          "id": "pp-tienen-station",
          "lat": 50.8085,
          "lon": 4.9245,
          "name": "Tienen station",
          "students": ["s002", "s003"]
        }
      ]
    }
  ]
}
```

- Een **stop** is een locatie plus de leerlingen die daar instappen.
  - Een string (`"s001"`) is een thuisstop: locatie = het punt van die leerling, één
    instapper.
  - Een object is een **vaste opstapplaats** met eigen coördinaten en een lijst
    `"students"`.
- `ordering` (scenario-breed, per bus te overschrijven met `"ordering"` in het
  bus-object):
  - `"given"` — de bus rijdt de stops exact in de opgegeven volgorde.
  - `"auto"` — de evaluator bepaalt zelf een volgorde per bus (heuristiek op de
    TomTom-reistijdmatrix; minimaliseert routelengte, **niet** rittijd per kind).
- Regels die de evaluator afdwingt (foutmelding bij overtreding):
  - elke leerling exact één keer toegewezen,
  - aantal instappers per bus ≤ `capacity`,
  - elke `bus_id` bestaat in `buses.json`.

## Output (`out/<naam>/metrics.json`)

`summary` bevat de evaluatiecriteria: `max_ride_min`, `avg_ride_min`, `median_ride_min`,
`rides_over_60_min`, `rides_over_90_min`, `max_to_stop_km`,
`students_with_to_stop_over_1km`, `total_drive_min`, `total_km`, `avg_occupancy_pct`,
`earliest_departure`, `buses_used`/`buses_unused`.

`students[]` heeft per kind `bus_id`, `stop_id`, `pickup` (instaptijd), `ride_min` (van
instappen tot school) en `to_stop_km` (hemelsbreed thuis→stop, 0 bij een thuisstop — die
verplaatsing zit **niet** in `ride_min`).

`buses[]` heeft per bus de bezetting, vertrek-/aankomsttijd, rijtijd, km, en per stop
(`stops[]`) de instaptijd en rittijd van de kinderen die daar opstappen.
