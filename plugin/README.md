# de-pass-routeplanning

Cowork-plugin om schoolbus-scenario's voor "de pass" (Hoegaarden) te bouwen, offline te
vergelijken, de volgorde of de verdeling te verbeteren, en daarna een kaart met echte
wegen te tonen: rittijd per kind, kilometers, bezetting en aankomsttijden.

## Wat je nodig hebt

- **Niets te installeren.** De plugin bevat een zelfstandige Python-tool
  (`skills/scenario-evaluator/references/busroutes/`) zonder externe dependencies — die
  draait in Claude's eigen werkomgeving.
- **Een TomTom API-sleutel**, alleen voor de definitieve kaart en voor een nieuw punt.
  Aanmaken op [developer.tomtom.com](https://developer.tomtom.com/). Claude bewaart hem
  in de werkmap (niet in deze plugin, niet gedeeld).
- **Het datapakket van de school**, buiten deze plugin en buiten git: een map met
  school, leerlingen, bussen, opstapplaatsen en `matrix/`. Wijs die map aan met
  `BUSROUTES_DATA_DIR` of `--data`. Zonder die instelling zoekt de tool in
  `docs/samples/`. De fictieve set in de git-repository is alleen het voorbeeld; die
  zit niet in dit bestand. Schema: `skills/scenario-evaluator/references/data-schema.md`.

## Gebruik

Vraag Claude gewoon om een scenario door te rekenen of te vergelijken, bijvoorbeeld:

- "Reken dit scenario door: bus 3 haalt de kinderen uit Tienen op via het station."
- "Vergelijk regiobus-per-zone met vaste-opstapplaatsen — welke geeft de kortste ritten?"
- "Wat als we bus 6 een vaste opstapplaats in Leuven geven in plaats van deur-aan-deur?"

Claude volgt één commando per vraag: eerst offline, dan eventueel de volgorde of de
verdeling, en pas daarna één TomTom-run voor de echte wegen. Hoofdresultaat is een
HTML-kaart (`map.html`, in Claude als artifact) met de busroutes, stops en tijden.
Daarna de langste en gemiddelde rit per kind en, bij meerdere scenario's, een
vergelijkingstabel. Op de kaart staan ook publieke De Lijn-, TEC- en NMBS-haltes
(aan/uit te zetten).

## Updates

Aan het begin van een sessie zegt Claude welke pluginversie hij gebruikt. Daarna
checkt hij of GitHub Releases een nieuwere versie heeft. Is dat zo, dan krijg je
de downloadlink van `de-pass-routeplanning.plugin`. Je vervangt de plugin in Claude
via Plugin → Add.

Lukt die check niet, dan hoor je alsnog de versie die nu geïnstalleerd is.

## Privacy

Het datapakket hoort bij de school: niet in deze plugin, niet in git. TomTom krijgt
coördinaten, alleen voor de definitieve kaart of een nieuw punt. Bewaar de werkmap niet
op een plek die breder gedeeld wordt dan nodig.
