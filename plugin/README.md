# de-pass-routeplanning

Cowork-plugin om schoolbus-scenario's voor "de pass" (Hoegaarden) door te rekenen en te
vergelijken: rittijd per kind, kilometers, bezetting, aankomsttijden en een kaart per
scenario. Geen solver — jij (of Claude, in overleg) bedenkt een verdeling van kinderen
over de bussen, de plugin rekent hem door en maakt scenario's onderling vergelijkbaar.

## Wat je nodig hebt

- **Niets te installeren.** De plugin bevat een zelfstandige Python-tool
  (`skills/scenario-evaluator/references/busroutes/`) zonder externe dependencies — die
  draait in Claude's eigen werkomgeving.
- **Een gratis TomTom API-sleutel.** Aanmaken op
  [developer.tomtom.com](https://developer.tomtom.com/). Claude vraagt hiernaar bij het
  eerste gebruik en bewaart hem lokaal in de werkmap (niet in deze plugin, niet gedeeld).
- **Je eigen schooldata**: adres/coördinaten en gewenste aankomsttijd van de school, de
  leerlingenlijst (adres of coördinaten per kind) en de buscapaciteiten. Claude vraagt
  hiernaar en zet het in het juiste formaat — zie
  `skills/scenario-evaluator/references/data-schema.md` voor het exacte schema.

## Gebruik

Vraag Claude gewoon om een scenario door te rekenen of te vergelijken, bijvoorbeeld:

- "Reken dit scenario door: bus 3 haalt de kinderen uit Tienen op via het station."
- "Vergelijk regiobus-per-zone met vaste-opstapplaatsen — welke geeft de kortste ritten?"
- "Wat als we bus 6 een vaste opstapplaats in Leuven geven in plaats van deur-aan-deur?"

Claude schrijft het scenario, rekent het door met verkeersbewuste TomTom-reistijden, en
rapporteert de langste/gemiddelde rit per kind, kilometers, bezetting en aankomsttijden,
plus een kaart (`map.html`) die je lokaal in de browser kan openen.

## Updates

Bij het doorrekenen checkt Claude of GitHub Releases een nieuwere versie heeft. Is dat
zo, dan krijg je de downloadlink van `de-pass-routeplanning.plugin`. Verwijder de oude
plugin in Cowork en installeer het nieuwe bestand. Cowork werkt de plugin niet zelf bij.

Zolang er nog geen GitHub Release is, zegt Claude niets en werkt de plugin gewoon.

## Privacy

Leerlingadressen zijn gevoelige gegevens van minderjarigen. Ze verlaten je eigen omgeving
enkel als geocoding/routing-aanvraag naar TomTom (nodig om reistijden te berekenen) — niet
naar enige andere dienst. Bewaar de werkmap (met de leerlingdata en de TomTom-cache) niet
op een plek die breder gedeeld wordt dan nodig.

## Achtergrond

Gebouwd voor het routeoptimalisatie-project van "de pass": zie de discussie over
geodata-bronnen (TomTom), waarom niet Google Route Optimization (die optimaliseert op
vlootkost, niet op rittijd per kind) en de architectuurkeuzes in het projectdossier.
OR-Tools voor een volledig geoptimaliseerde verdeling (in plaats van een door mensen
bedacht scenario) staat genoteerd als mogelijke volgende stap, maar zit niet in deze
plugin.
