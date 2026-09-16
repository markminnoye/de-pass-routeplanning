---
title: Route-optimalisatie verkennen & skill uitbreiden
status: "⬜"
date: 2026-09-16
---

# Plan: Route-optimalisatie verkennen (kosten × kwaliteit) → skill + De Pass-basisdataset

**Canonieke user-facing tekst** (Project store): houd inhoud synchroon met dit bestand bij wijzigingen.  
Dit plan volgt de projectconventie (INDEX + `.agent/plans/`).

**Doel:** optimalisatie-opties vergelijken op kosten en kwaliteit t.o.v. “kortste rit per kind”; daarna de gekozen aanpak in de skill + De Pass-basisdataset.  
**Non-goals:** online app, multi-school (later).

## Context (kort)

- Laag 1 TomTom (hybride) + evaluator CLI + skill + fictieve samples ✅
- Laag 2 solver (OR-Tools / Google RO / …) ⬜ — INDEX “volgend” na 2026-09-14
- `ordering: auto` ≠ per-kind-objectief; geen automatische kinderen→bus-toewijzing

## Assen

Kosten · kwaliteit op max/gem. rittijd · constraints · limieten/reproduceerbaarheid · privacy · skill-fit · onderhoud/EOL.

Kandidaten: A agent+evaluate · B OR-Tools · C OR-Tools-varianten · D Google Route Optimization · E TomTom Waypoint Opt (afvallen: 12 stops, EOL 2027) · F VROOM/ORS (lage prio).

## Experimenten (samples, zelfde `BUSROUTES_REFERENCE_DATE`)

1. **A** — skill: ≤5 manuele scenario’s vs. referenties (`spreiding-gemengd`, `regiobus-per-zone`, `opstapplaatsen`).
2. **B** — OR-Tools spike → scenario-JSON → `busroutes evaluate`; objectieven max-rittijd / som-rittijden.
3. **C** — alleen als B werkt (zones→TSP, soft pickups, matrix vs haversine).
4. **D** — Google RO empirisch (Mark: GCP); output via TomTom-evaluate voor appels-met-appels; of “deferred”.
5. **E/F** — kort afvinken.

Meet: `max_ride_min`, `avg_ride_min`, rides >60/>90, km/rijtijd, API-kost, uitlegbaarheid. Dry-run / cache discipline.

## Skill-scope (na beslissing)

Uitbreiden van `scenario-evaluator`: evaluate/compare blijft; + “volledig geoptimaliseerd” via gekozen solver → JSON → metrics + `map.html`. Basisdataset = `docs/samples/` tot echte De Pass-data (zelfde schema, privacy-pad apart).

## Beslissingscheckpoint

Na A+B (+D indien klaar): winnaar op per-kind-metrics, genoeg winst vs. onderhoud, kost, skill-fit, privacy → OR-Tools primair / hybride / Google secundair / alleen evaluator. Amendement in `docs/data-en-tooling-opties.md`.

## Volgorde

1. Scorekaart (docs)  
2. Experiment A  
3. OR-Tools spike + B  
4. D of deferred (Mark)  
5. Checkpoint  
6. Pas daarna implementatie skill/CLI + DoD

## Open vragen (Mark)

Zie Project-store plan § “Open vragen”: GCP-budget D, beltijd 08:20, timing echte data, harde zone-regels, TomTom volle-matrix OK, wie de skill moet kunnen draaien.

## Status: ⬜ Nog niet gestart
