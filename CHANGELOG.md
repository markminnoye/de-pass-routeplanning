# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Benchmark `scripts/bench_solvers.py` (dependency-groep `bench`, niet in CI): stdlib-ordening
  tegen pyvroom en OR-Tools op de sample-matrix, gescoord met `evaluate --offline`
- `busroutes optimize --order|--assign`: stdlib-solver op de matrix (geen TomTom); schrijft
  een scenario-JSON met `ordering: given` en een vóór/na-samenvatting op offline-cijfers
  ("vóór" = wat `evaluate --offline` voor het invoerscenario geeft; `--assign` start vanaf
  die niveau-A-ordening, dus "na" is nooit slechter)
- Scenario-velden `pinned` (per bus, geldt voor `--order` én `--assign`) en `pinned_stops`
  (stop-ids blijven op hun bus)
- Datapakket (`BUSROUTES_DATA_DIR` / `--data`, default `docs/samples/` inclusief `matrix/`)
- `evaluate --offline`: scenario's doorrekenen zonder TomTom-key
- `busroutes data status|fetch-matrix|add-points`

### Changed
- Matrix-cache default is `<data>/matrix` (was `.cache/tomtom/cells/`)
- Default ordening terug naar `matrix` (beslissing 15/09/2026: exactheid boven credits);
  `haversine` blijft als goedkope verkenmodus (`--ordering haversine` / `BUSROUTES_ORDERING`)
- Plugin-pakket is weer `de-pass-routeplanning.plugin` (Desktop: `.zip` = skill, `.plugin` = plugin)
- Leaflet CSS in `map.html` inlined; JS via cdnjs `leaflet.min.js` (artifact-viewer CSP blokkeert unpkg én externe stylesheets)
- Skill: HTML-kaart is het hoofddeliverable (routes zien), daarna pas cijfers/vergelijking
- Stopnummer staat nu ín de marker op `map.html` in plaats van in een zwevend labeltje erboven
- Testset: beltijd (`target_arrival`) 08:30 i.p.v. 08:20; `docs/samples/expected/` hergenereerd
- Legende in `map.html`: ronde kleurstippen i.p.v. vierkantjes, en per bus aan/uit te zetten

## [0.2.1] - 2026-09-15

### Changed
- Leaflet CSS/JS in `map.html` via cdnjs.cloudflare.com (Claude-artifact CSP blokkeert unpkg.com)

## [0.2.0] - 2026-09-15

### Added
- Overlay van De Lijn-, TEC- en NMBS-haltes op `map.html` via Overpass (gecached in `.cache/overpass/`, uitzetbaar in Leaflet)
- Esri World Street Map als tweede basemap in de layer control
- GitHub als canonieke remote (`repository` in `plugin.json`) zodat de versie-check Releases kan zien
- Gratis default-ordening `haversine` naast TomTom-`matrix`; CLI `--ordering` en `BUSROUTES_ORDERING`
- `--dry-run` en verbruiksrapport (TomTom-transacties) na een run
- Matrix-facturatieformule en goedkoopste blokvorm (`matrix_transactions` / `plan_blocks`)
- Cache per punt-paar (`.cache/tomtom/cells/`), legacy matrix-harvest, atomische cache-writes
- Verplichte referentiedatum (`BUSROUTES_REFERENCE_DATE` / `--reference-date`) voor reproduceerbare `departAt`
- Cowork-plugin packaging (`plugin/`, `scripts/build_plugin.py`, GitHub Actions release-op-tag)
- Scenario-evaluator v1: TomTom-client, stopordening, metrics, Leaflet-kaart, CLI, fictieve testset

### Changed
- Basemap: OpenStreetMap.de i.p.v. `tile.openstreetmap.org` (Chrome op lokaal `file://` stuurt geen HTTP-Referer; OSMF geeft dan 403)
- Plugin-pakket voor Desktop/Cowork-upload is `de-pass-routeplanning.zip` (geen `.plugin`-extensie)
- Default ordening: `haversine` i.p.v. matrix → ~21 i.p.v. ~5.900 transacties voor de drie samples (koude cache)
- Buscapaciteit 30; compare toont `buses-used`
- Docs: TomTom-facturatiemodel en aanbevolen werkwijze in `docs/data-en-tooling-opties.md` en skill

### Fixed
- Cache sleutel schoof dagelijks mee zonder vaste referentiedatum (DoD-reproduceerbaarheid)
- Identieke leerlingpunten krijgen geen aparte stops meer

## [0.1.0] - 2026-09-14

Initiële evaluator- en plugin-basis (nog niet als GitHub Release gepubliceerd).

[Unreleased]: https://github.com/markminnoye/de-pass-routeplanning/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/markminnoye/de-pass-routeplanning/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/markminnoye/de-pass-routeplanning/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/markminnoye/de-pass-routeplanning/releases/tag/v0.1.0
