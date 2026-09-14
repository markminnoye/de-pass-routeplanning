---
title: Projectbrief — Schoolbusroutes "de pass" Hoegaarden
description: Oorspronkelijke opdracht/vision voor het routeoptimalisatie-project
date: 2026-09-14
---

# Projectbrief

We bekijken hoe we de routes van de zeven schoolbussen vanuit de school "de pass" in Hoegaarden met AI en route-optimalisatie kunnen verbeteren. Doel: lange ritten beperken, en rekening houden met buscapaciteit, vertrektijden, aankomstwensen en ochtendverkeer.

Het doel is om voor elk kind de rit zo kort mogelijk te houden.

Er kunnen verschillende scenario's gemaakt worden, zoals een bus inleggen die naar een bepaalde streek rijdt (bijvoorbeeld Leuven) om daar de kinderen uit die regio op te pikken/af te halen. Er kunnen ook scenario's bedacht worden met vaste opstapplaatsen voor kleinere gebieden waar meer kinderen wonen, om verkeer en omwegen te vermijden, of een volledig geoptimaliseerde verdeling.

Voor elk scenario bekijken we maximale en gemiddelde reistijd per leerling, totale rijtijd, kilometers, bezettingsgraad en aankomsttijden. Technisch lijkt het haalbaar om dit via MCP aan een AI-agent te geven voor simulaties.

We willen deze scenario's voorstellen op een kaart en ook de route kunnen uittekenen in een mapping tool.

## Kernvereisten (samengevat)

- **Doelfunctie**: kortst mogelijke rit per individueel kind (niet de laagste vlootkost — zie [data-en-tooling-opties.md](data-en-tooling-opties.md)).
- **Constraints**: buscapaciteit, vertrektijden, aankomstwensen, ochtendverkeer.
- **Scenario's**:
  - Regiobus (bv. Leuven) die kinderen uit één streek verzamelt.
  - Vaste opstapplaatsen voor zones met veel kinderen.
  - Volledig geoptimaliseerde verdeling.
- **Evaluatiecriteria per scenario**: max. en gemiddelde reistijd/leerling, totale rijtijd, km, bezettingsgraad, aankomsttijden.
- **Uitvoering**: simulaties via een AI-agent, aangestuurd met MCP-tools.
- **Output**: scenario's tonen op een kaart, routes uittekenen in een mapping tool.

Zie [data-en-tooling-opties.md](data-en-tooling-opties.md) voor de uitwerking van welke tools/APIs/solvers dit concreet invullen, en de beslissingen die daaruit voortkomen.
