---
title: Data- en tooling-opties voor routeoptimalisatie
description: Vergelijking van kaart/geodata-MCP's, VRP-solvers en visualisatie-opties voor het schoolbus-project van "de pass"
date: 2026-09-14
---

# Data- en tooling-opties voor routeoptimalisatie

Uitgangspunt: we hebben drie losse lagen nodig, en dat is meteen de belangrijkste correctie op het eerste voorstel — een "Maps MCP" (Google/TomTom/Mapbox) lost vooral laag 1 op, niet laag 2.

1. **Geodata**: adressen omzetten naar coördinaten (geocoding) en reistijden/afstanden tussen punten berekenen — bij voorkeur verkeersbewust voor de ochtendspits.
2. **Optimalisatie**: met die reistijden de eigenlijke toewijzing maken — welk kind op welke bus, in welke volgorde, gegeven buscapaciteit en aankomstvenster op school.
3. **Visualisatie**: scenario's op een kaart tonen en routes kunnen uittekenen.

**Schaal van het project**: 7 bussen × ±20 kinderen/bus → tot ±140 leerlingen in totaal. Dat is klein voor een echte solver (OR-Tools/VROOM verwerken probleemloos duizenden stops), maar te groot voor een aantal gratis/lichte API's die we hieronder tegenkomen (bv. TomTom Waypoint Optimization: max. 12 stops; OpenRouteService gratis tier: max. 3 voertuigen).

## 1. Geodata — wat is er echt beschikbaar

| Optie | Status in Claude registry | Wat het levert | Link |
|---|---|---|---|
| **TomTom Maps** | ✅ Installeerbare connector | Geocoding, routing, **verkeersdata** | [developer.tomtom.com](https://developer.tomtom.com/) · MCP: [overview](https://docs.tomtom.com/tomtom-maps-mcp/documentation/overview), [tools](https://docs.tomtom.com/tomtom-maps-mcp/documentation/tools), [quick-setup](https://docs.tomtom.com/tomtom-maps-mcp/documentation/quick-setup), [Claude Desktop](https://docs.tomtom.com/tomtom-maps-mcp/documentation/integration-guides/claude-desktop), [GitHub](https://github.com/tomtom-international/tomtom-mcp) |
| Google Maps / Routes API | ❌ Geen connector | Rechtstreeks aan te roepen met eigen API-key (zie onder) | [developers.google.com/maps](https://developers.google.com/maps) |
| Mapbox | ❌ Geen connector | Idem | [docs.mapbox.com](https://docs.mapbox.com/api/navigation/) |
| OpenRouteService (OSM-based) | ❌ Geen connector, wel gratis publieke API | Geocoding + matrix bruikbaar; optimalisatie zwaar gelimiteerd | [openrouteservice.org](https://openrouteservice.org/) |

Van de vier genoemde kandidaten is **enkel TomTom nu als connector te activeren** in Claude.

### Wat de TomTom MCP-connector wel en niet kan (nagekeken 14/09/2026)

De officiële server ([tomtom-international/tomtom-mcp](https://github.com/tomtom-international/tomtom-mcp), npm `@tomtom-org/tomtom-mcp`, of hosted op `https://mcp.tomtom.com/maps` — "public preview", authenticatie met dezelfde API-key) biedt 11 tools: `tomtom-geocode`, `tomtom-reverse-geocode`, `tomtom-fuzzy-search`, `tomtom-poi-search`, `tomtom-nearby`, `tomtom-routing` (A→B), `tomtom-waypoint-routing` (meerdere stops in vaste volgorde; `departAt`/`arriveAt`, `traffic`, `computeBestOrder`), `tomtom-reachable-range`, `tomtom-traffic`, `tomtom-static-map`, `tomtom-dynamic-map`.

Beperkingen die voor dit project tellen:

- **Geen Matrix Routing-tool.** De reistijdmatrix (invoer voor auto-ordening en OR-Tools) is via MCP alleen te benaderen met honderden losse routing-calls.
- **Geometrie wordt standaard weggegooid**: `response_detail` staat op `compact` (strips polyline-coördinaten, guidance, secties); `full` geeft alles, maar dan stroomt per bus een volledige polyline door de conversatiecontext.
- **Alles loopt door de context**: 7 routes per scenario met geometrie = tienduizenden tokens per doorrekening, en de agent moet cijfers manueel overnemen naar metrics/GeoJSON.
- **Niet cachebaar/reproduceerbaar**: elke herberekening = nieuwe live-calls; de DoD vraagt identieke cijfers bij identieke input.

De REST-tegenhanger is klein: het smoke-script doet de Matrix-call in ~40 regels, `calculateRoute` is vergelijkbaar.

**Beslissing: hybride.** De MCP-connector voor interactief verkennen (een opstapplaats geocoden, "Leuven-station → school om 7u30" snel checken, een kaartbeeld in het gesprek, scenario-ideeën aftoetsen). Python + REST (Matrix Routing v2 + `calculateRoute`, met disk-cache en `traffic: historical`) voor de batch-evaluator die scenario's doorrekent. Uitgangspunt blijft: bestaande connectoren gebruiken waar ze het werk dekken, eigen code enkel waar ze tekortschieten.

### Bestaat er een (open source) Google Maps MCP?

Ja, maar met een belangrijke kanttekening: de **officiële referentie-server van Anthropic/MCP zelf is gearchiveerd en niet meer onderhouden** — ze staat nu in de [servers-archived repository](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/google-maps) en is uit de actieve MCP-referentie-implementaties gehaald.

Er bestaan wel community-forks die het gat opvullen, bv.:
- [david-pivonka/google-maps-mcp-server](https://mcpservers.org/servers/github-com-david-pivonka-google-maps-mcp-server)
- [ArtixZ/MCP-Google-Maps](https://glama.ai/mcp/servers/@ArtixZ/MCP-Google-Maps)
- [BACH-AI-Tools/MCP-Google-Maps](https://glama.ai/mcp/servers/@BACH-AI-Tools/MCP-Google-Maps)

Dit zijn ongeverifieerde, door individuen onderhouden projecten — geen officiële Google- of Anthropic-connector, en ze staan niet in de Claude-connectorregistry. Voor de eigenlijke *Route Optimization API* (het fleet-routing-product) bestaat sowieso geen community-MCP — dat is een gespecialiseerd product waar ik geen open-source wrapper voor terugvind.

**Belangrijke nuance nu jij zelf developer bent en een eigen key wil gebruiken**: een volledige MCP-server hosten voor "Google Maps" in het algemeen is hier waarschijnlijk overkill. Een MCP-server is nuttig als je een brede, herbruikbare toolset permanent aan een Claude-sessie wil koppelen (zodat je conversational allerlei Maps-functies kan aanroepen). Voor dit project heb je maar één specifieke capability nodig — de Route Optimization-call. Die kan je (of ik, in een skill) gewoon **rechtstreeks als REST-call** aanspreken vanuit Python, met jouw eigen Google Cloud API-key/service account — geen aparte MCP-server nodig, geen extra onderhoud. Een MCP heeft pas meerwaarde als je deze capability breder herbruikbaar wil maken over meerdere projecten/agents heen.

## Kan TomTom de optimalisatie zelf doen?

Gedeeltelijk, maar met twee harde beperkingen die het ongeschikt maken voor dit project:

- TomTom heeft een aparte **[Waypoint Optimization API](https://docs.tomtom.com/waypoint-optimization/documentation/waypoint-optimization-service)**. Die herschikt de volgorde van stops voor **één voertuig** (een "traveling salesman"-achtige optimalisatie, geen verdeling over meerdere bussen), ondersteunt tijdvensters, maar is **beperkt tot 12 waypoints per aanvraag** (hogere limiet enkel via een apart contract met sales) — te weinig voor een bus met ~20 kinderen.
- Belangrijker: TomTom kondigt aan dat deze API **op 31 mei 2027 volledig wordt stopgezet**, zonder aangeboden migratiepad. Daar zou ik dus sowieso niet op bouwen.

TomTom's **[Matrix Routing API](https://developer.tomtom.com/matrix-routing-api/documentation)** (reistijd/afstand tussen elk paar punten, verkeersbewust) blijft wel prima bruikbaar — dat is exact de data die een solver (of een agent die scenario's evalueert) nodig heeft als invoer. TomTom levert dus betrouwbaar **laag 1** (de reistijden), maar niet laag 2 (de verdeling over 7 bussen).

### Lessen uit de implementatie van de evaluator (14/09/2026)

- **Matrix Routing v2, synchroon**: max. **100 cellen** per request bij een concrete `departAt`; **200 cellen** bij `departAt: any` + `traffic: historical` + `routeType: fastest`; 2500 enkel op een enterprise-plan. De evaluator gebruikt daarom de tijdsonafhankelijke variant (`any`/historical, in blokken ≤ 200 cellen) **alleen voor de stopvolgorde**; de autoritatieve tijden komen uit `calculateRoute`.
- **calculateRoute**: max. 150 waypoints per request (wij: ~22 per bus). `traffic=false` + `departAt` = historische, tijdsafhankelijke snelheden zonder live-incidenten → reproduceerbaar. Elke leg geeft tijd, afstand én polyline.
- **Rate limit**: de gratis key geeft snel HTTP 429 (Search API ~5 requests/s). De client doet retries met backoff; alle antwoorden worden op schijf gecachet (`.cache/tomtom/`).
- **U-turn-penalty**: in een multi-waypoint-route rekent TomTom een forse straf (orde 2 minuten) als de bus na een stop moet keren om naar de volgende te rijden — een leg van 140 m kan zo 153 s duren waar hij los berekend 33 s duurt. Dat is realistisch voor deur-aan-deur ophalen in dorpsstraten en verklaart deels de lange rittijden; het is meteen een argument voor vaste opstapplaatsen. De eenvoudige ordeningsheuristiek (matrix + 2-opt) ziet die penalty niet; OR-Tools straks ook niet zonder extra modellering.
- **Willekeurige punten moeten op een straat liggen**: routering klikt een punt in een veld vast aan het dichtstbijzijnde segment, ook voetpaden of "service vehicles only" — vandaar de snapping in de testset-generator.

### Wat matrixcellen echt kosten (15/09/2026)

Aanleiding: de gratis TomTom-credits waren op na een handvol doorrekeningen. De oorzaak stond niet in de limieten hierboven maar in het **facturatiemodel**, dat we eerst niet hadden nagekeken. Volgens [Discounted Transaction Billing](https://developer.tomtom.com/matrix-routing-v2-api/documentation/discounted-transaction-billing) rekent Matrix Routing v2 **niet per cel** maar per aanvraag, op basis van de dimensies:

- zijn origins **én** destinations groter dan 5 → `5 × max(origins, destinations)` transacties;
- anders → `origins × destinations` transacties.

Eén cel kost in een grote aanvraag dus `5 / min(origins, destinations)` transacties. Gevolgen die de implementatie veranderd hebben:

- **Vierkante blokken zijn spotgoedkoop, rijstroken zijn duur.** De eerste versie sneed de matrix in stroken van `200 // aantal_destinations` rijen: voor een bus met 20 kinderen (22 punten) 3 aanvragen van 9×22 = 308 transacties, waar 4 blokken van 11×11 hetzelfde werk voor 220 doen. Bij 30 kinderen (32 punten) is het verschil 864 tegenover 480. De blokvorm wordt nu per geval uitgerekend (`_cheapest_split` in `busroutes/tomtom.py`).
- **Cachen per aanvraag was verkeerd; het moet per punt-paar.** Eén kind van bus3 naar bus5 verplaatsen veranderde de request-body van beide bussen en haalde dus beide matrices volledig opnieuw op (~600 transacties), terwijl bijna alle punt-paren al bekend waren. De cache staat nu in `.cache/tomtom/cells/` met de coördinaten als sleutel: een paar dat één keer betaald is, wordt nooit opnieuw betaald, ook niet als een later scenario dezelfde punten anders over de bussen verdeelt. Samenvallende stops (kinderen op hetzelfde punt) vallen daardoor gratis samen.
- **De matrix dient alleen voor de stopvolgorde**; alle gerapporteerde tijden en kilometers komen uit `calculateRoute`. Er is dus een gratis alternatief: de volgorde uit hemelsbrede afstanden (`ordering: "haversine"`), waarmee een scenario 7 transacties kost in plaats van ~1.500. Dat blijft een keuze en niet de default — zie de afweging hieronder.
- **Gemeten op de eigen testset** (koude cache, drie referentiescenario's samen): 5.934 transacties met de eerste versie, 4.025 met de huidige default, 21 met `--ordering haversine`. Het Freemium-plafond is 2.500 non-tile requests per dag, dus één volledige pass met exacte ordening past nog altijd niet in één dag — plan dat over twee dagen of gebruik de gratis ordening om te verkennen.
- **`departAt` zat in de cachesleutel van `calculateRoute`, zonder vaste referentiedatum.** Daardoor verviel de routecache elke dag en waren dezelfde cijfers morgen niet reproduceerbaar (DoD 4). De referentiedatum is nu verplicht: `BUSROUTES_REFERENCE_DATE` of `--reference-date`, anders een duidelijke fout met een voorstel.
- **Raming vóór het geld weg is.** `busroutes evaluate --dry-run` haalt niets op en telt exact wat de run zou kosten; na een echte run rapporteert de CLI het verbruik en wat de cache uitspaarde.
- **Cachebestanden worden atomisch geschreven** en een afgebroken bestand wordt opnieuw opgehaald in plaats van de run te laten crashen — anders is de reflex `rm -rf .cache`, en dat betaal je volledig terug.
- **Bij een gaten-cache is precies-de-gaten-ophalen soms duurder dan alles opnieuw halen.** Een aanvraag met één origin valt onder `origins × destinations`, dus 1 transactie per cel, terwijl een cel in een blok van 14×14 er 0,36 kost. Voor de eigen testset (139 punten, 5.099 paren al bekend) kostte gaten-vullen 13.694 transacties en één volledige rechthoek 6.995. `plan_blocks()` rekent daarom beide plannen door en neemt het goedkoopste.

### Afweging: gratis ordening tegenover exacte ordening (15/09/2026)

De hemelsbrede ordening is niet gratis in kwaliteit. Gemeten op de drie referentiescenario's, met de **echte** TomTom-reistijden uit de cache als scheidsrechter, geeft ze een langere totale rijtijd:

| Scenario | Volgorde uit TomTom-matrix | Volgorde uit hemelsbrede afstand | Verschil |
|---|---|---|---|
| spreiding-gemengd | 1.165 min | 1.210 min | +3,8 % |
| regiobus-per-zone | 553 min | 612 min | +10,7 % |
| opstapplaatsen | 437 min | 495 min | +13,3 % |

Per bus loopt het verschil op tot +20 minuten (bus6 in spreiding-gemengd). Voor een project waarvan de kernvraag "zo kort mogelijke individuele rit per kind" is, is 10 % geen ruis. **Daarom blijft `matrix` de default** (beslissing 15/09/2026): liever ~1.500 transacties per nieuw scenario dan cijfers die de school niet kan vertrouwen. `haversine` is er om snel veel varianten af te tasten; dat hoort dan wel in de rapportering te staan, want de twee zijn niet onderling vergelijkbaar.

Wie veel scenario's gaat doorrekenen, koopt beter één keer de **volledige puntmatrix**: alle 139 punten van de testset onderling kost 6.995 transacties (~3 dagen Freemium-plafond), en daarna is elk scenario exact én gratis, omdat elk punt-paar dan in de cache zit. Zodra de echte leerlingenlijst stabiel is, is dat de goedkoopste weg naar onbeperkt vergelijken.

## 2. Optimalisatie

- **Google Route Optimization API** ([documentatie-hub](https://developers.google.com/maps/documentation/route-optimization) / [overview](https://developers.google.com/maps/documentation/route-optimization/overview), voorheen Cloud Fleet Routing): capaciteit + tijdvensters + meerdere voertuigen, in één API die zowel de reistijden als de oplossing berekent (op Google's eigen wegennetwerk). **Prijs: ±$30 per 1000 "shipments" bij meerdere voertuigen** (single-vehicle tier goedkoper: $10/1000). Voor 140 kinderen = ±140 shipments per volledige herberekening → **ruwweg €4 per keer dat je het scenario volledig laat heroptimaliseren**. Vergt een Google Cloud-project + billing account + service-account-authenticatie, geen aparte MCP nodig (zie hierboven) — rechtstreeks als REST-call bruikbaar in een skill. Zie hieronder voor waarom we dit **voorlopig niet gebruiken**, en hoe je het zelf snel kan uittesten.
- **[Mapbox Optimization API v2](https://docs.mapbox.com/api/navigation/optimization/)**: tot 1000 locaties, capaciteit + tijdvensters, $2/1000 na 100.000 gratis/maand. Geen connector.

Open-source solvers:

| Solver | Karakter | Snelheid | Licentie | Link |
|---|---|---|---|---|
| **VROOM** | Lichte C++ REST-service | Milliseconden | BSD-2 (gratis) | [github.com/VROOM-Project/vroom](https://github.com/VROOM-Project/vroom) |
| **Google OR-Tools** | Python/C++ bibliotheek | Seconden | Apache 2.0 (gratis) | [github.com/google/or-tools](https://github.com/google/or-tools) |
| JSprit | Java-bibliotheek | Seconden | Apache 2.0 (gratis) | [github.com/graphhopper/jsprit](https://github.com/graphhopper/jsprit) |

Kanttekening bij VROOM: de oorspronkelijke makers hebben er ondertussen ook een commercieel product rond gebouwd, **Verso** ([vroom-project.org](http://vroom-project.org/)) — de open-source engine zelf blijft gratis op GitHub staan, maar wie liever een kant-en-klare hosted service wil, kan ook bij Verso terecht (tegen betaling).

OpenRouteService's eigen [optimalisatie-endpoint](https://openrouteservice.org/dev/#/api-docs/optimization) wrapt trouwens intern ook VROOM, maar de gratis publieke API is er hard gelimiteerd op **max. 3 voertuigen en 50 stops per request** — te klein voor 7 bussen.

### Waarom we Google Route Optimization API voorlopig NIET gebruiken

**Geverifieerd, niet enkel een vermoeden**: ik heb Google's eigen [cost-model-documentatie](https://developers.google.com/maps/documentation/route-optimization/concepts/costs) nagekeken. Het bevestigt exact het onderscheid dat je zelf aanhaalde. De API optimaliseert uitsluitend op basis van deze kostencomponenten:

- `fixedCost` — vaste kost als een bus wordt ingezet
- `costPerHour` — kost per uur inzet (rijden + wachten + stops + pauzes)
- `costPerTraveledHour` — kost per uur, enkel tijdens het rijden zelf
- `costPerKilometer` — kost per gereden kilometer
- `penaltyCost` — boete als een shipment (kind) wordt overgeslagen

**Er bestaat geen ingebouwd objectief om de individuele rittijd van één passagier/kind te minimaliseren.** De documentatie omschrijft het doel expliciet als het vinden van "routes with the lowest cost" — bedoeld voor vlootefficiëntie (brandstof, arbeidsuren, aantal voertuigen), niet voor het comfort/de ritduur van een individuele passagier. Dat is ook precies hoe Google het product zelf positioneert in hun [aankondiging](https://mapsplatform.google.com/resources/blog/plan-efficient-routes-for-your-fleet-route-optimization-api-is-now-generally/): gericht op logistiek, leveringen, technici en on-demand bezorging — operationele kostenefficiëntie, niet passagierservaring. Er is geen native constraint voor "maximale rittijd per passagier" zoals je in ride-pooling-systemen soms tegenkomt.

**Conclusie**: jouw vermoeden klopt. Google Route Optimization is gebouwd om de *kost van de vloot* te minimaliseren (aantal voertuigen, gereden km, gewerkte uren) — niet om de *rit van elk kind* zo kort mogelijk te maken. Je zou het objectief kunnen "misbruiken" (bv. door elke bus zijn eigen fixed cost te geven en te hopen dat kortere routes daar toevallig uit rollen), maar dat is indirect en onbetrouwbaar t.o.v. wat je eigenlijk wil. Daarom gebruiken we dit **voorlopig niet** als primaire solver — OR-Tools, waar je de doelfunctie zelf schrijft (bv. minimaliseer de langste individuele rittijd), blijft de eerste keuze voor dit project. We houden Google Route Optimization wel genoteerd als optie mocht de doelstelling ooit verschuiven naar "zo weinig mogelijk bussen/kilometers" (een kostenvraag) in plaats van "zo kort mogelijke rit per kind" (een comfortvraag).

### Hoe kan je dit zelf snel uittesten? Is er een GUI?

Ja — Google heeft een **open-source, deploybare demo-applicatie met GUI**: [googlemaps/js-route-optimization-app](https://github.com/googlemaps/js-route-optimization-app). Wat die biedt:

- Een web-interface met **formulieren, tabellen én een kaart** om scenario's (voertuigen, shipments, capaciteit, tijdvensters) samen te stellen zonder zelf JSON te schrijven.
- Visualisatie van de berekende routes op de kaart — precies het soort snelle feedback dat je zoekt.
- Door Google zelf omschreven als een **"exploratory tool"** — nadrukkelijk niet bedoeld voor productie, wel ideaal om te begrijpen wat de API wel/niet doet voor je er verder in investeert.

**Belangrijk**: dit is geen live publieke demo die je zomaar in de browser opent. Je moet de app zelf deployen naar een eigen Google Cloud-project (met billing account en Route Optimization API ingeschakeld) — de repo bevat een project-setup-gids en een deployment-gids (Cloud Run/Artifact Registry) plus een gids om ze lokaal te draaien. Voor jou als developer is dat een kwestie van een uurtje volgens hun documentatie, geen zware klus.

Over kosten om te testen: Google's eigen aankondiging vermeldt "tot 10.000 gratis calls per SKU per maand" voor Maps Platform-diensten in het algemeen, maar de specifieke Route Optimization-pricing-pagina beschrijft een shipment-gebaseerd model zonder expliciete gratis staffel voor die SKU. Die twee bronnen zijn niet helemaal consistent — check dus zeker de prijscalculator in de Google Cloud Console vóór je test, maar met de scenario's van deze omvang (140 shipments) praat je hoe dan ook over een paar euro per testrun, geen grote uitgave.

### En die YouTube-video over Gemini + route-optimalisatie?

Mark vond ["Intelligent Route Optimization Using Google Maps and Gemini"](https://www.youtube.com/watch?v=V8iEt4lK3cQ). **Eerlijkheidshalve: ik kon de video zelf niet bekijken** (geen toegang tot video/transcript vanuit hier, enkel de titel via zoeken), dus onderstaande is afgeleid uit Google's eigen documentatie over hetzelfde patroon — check de video zelf voor het volledige verhaal.

Wat ik wel kon vinden: Google's eigen materiaal over "Gemini + Maps" (bv. ["Grounding with Google Maps" in het Gemini Enterprise Agent Platform](https://mapsplatform.google.com/resources/blog/introducing-new-routing-features-in-grounding-with-google-maps/)) beschrijft **niet** dat Gemini zelf een routing-/optimalisatieprobleem oplost. Gemini is een taalmodel, geen solver. Wat er in die demo's typisch gebeurt: Gemini treedt op als **agent/orchestrator** die natuurlijke taal omzet naar gestructureerde aanroepen van bestaande Google Maps-API's (Directions, Places, eventueel Route Optimization) via function calling — bijvoorbeeld "vind cocktailbars met een bepaalde sfeer langs mijn traject" wordt vertaald naar een reeks API-calls. Die specifieke "Grounding with Google Maps"-routingfunctie ondersteunt trouwens maximaal 13 tussenstops voor één route — dus ook weer een single-route-tool, geen multi-voertuig-VRP-oplosser.

**Concreet betekent dit**: als de video toont dat Gemini "het schoolbusprobleem" oplost, doet het dat vermoedelijk op dezelfde manier als wat wij hier al aan het opzetten zijn — een LLM-agent (Gemini in plaats van Claude) die de onderliggende Maps-/Route Optimization-API als *tool* aanroept. Het verandert niets aan de kern van het probleem: als die demo onder de motorkap de Route Optimization API gebruikt, geldt exact dezelfde beperking die we hierboven bespraken (kostenmodel, geen "kortste rit per kind"-objectief). Gemini "toveren" er geen VRP-oplossing bij die de onderliggende API niet al had. Mocht de video toch iets tonen dat hiermee in tegenspraak is (bv. een expliciete per-passagier-rittijd-constraint), hoor ik dat graag — dan neem ik dat er alsnog bij.

### Google Route Optimization API vs. zelf OR-Tools draaien — samengevat

| | Google Route Optimization API | OR-Tools (zelf draaien) |
|---|---|---|
| Doelfunctie | Vlootkost (vaste kost, uren, km, boetes) — **geen** ingebouwd "kortste rit per kind"-objectief | Volledig zelf te coderen — kan expliciet "minimaliseer de langste rittijd van eender welk kind" |
| Kost | ±€4 per volledige herberekening (140 kinderen), geen bevestigde gratis staffel | Gratis |
| Setup | Google Cloud-project, billing, service account | `pip install ortools`, direct bruikbaar in deze sessie |
| Reistijddata | Ingebouwd (Google's eigen wegennetwerk + verkeer) | Moet je apart aanleveren (bv. via TomTom-matrix) |
| GUI om te verkennen | Ja — [js-route-optimization-app](https://github.com/googlemaps/js-route-optimization-app) (zelf te deployen) | Nee — puur programmatisch |
| Onderhoud | Geen — Google host en beheert de solver | Jij (of ik) beheert de code, maar het is een stabiele, veelgebruikte bibliotheek |
| Snelheid | Zeer snel (volgens Google's documentatie: 2000 shipments/10 voertuigen in <30s) | Snel genoeg op deze schaal (seconden) |

**Beslissing**: voor de kernvraag van dit project (kortste rit per kind) gebruiken we voorlopig OR-Tools. Google Route Optimization staat genoteerd als iets om apart te verkennen via hun GUI-demo-app — nuttig om te begrijpen wat het product wel/niet kan, maar niet ingezet als primaire solver zolang het doel "kortste individuele rit" blijft in plaats van "laagste vlootkost".

### Wat is nu precies het verschil tussen laag 1 (TomTom/Google Maps) en laag 2 (OR-Tools)? Wat kan de solver dat de kaarten-API niet kan?

Dit is de kernvraag, dus even expliciet:

Een routing-/kaarten-API zoals TomTom of Google Maps Directions beantwoordt de vraag *"wat is de snelste route/tijd tussen deze punten"* — en bij een beperkte variant (zoals TomTom's Waypoint Optimization of Google's `optimizeWaypointOrder`) ook *"in welke volgorde bezoekt één voertuig deze paar stops het snelst"*. Dat is één route, al gegeven welke stops erop staan.

Wat het project vraagt is iets fundamenteel anders: **welke 20 van de 140 kinderen gaan op bus 1, welke 20 op bus 2, enzovoort — én in welke volgorde per bus — zodat de rit voor élk kind zo kort mogelijk is, binnen de capaciteit en het aankomstvenster.** Dat is een *toewijzingsprobleem* (partitie van 140 kinderen over 7 bussen) gecombineerd met een *volgordeprobleem* per bus, tegelijk opgelost. Het aantal mogelijke combinaties is astronomisch groot — dit is een klassiek NP-hard combinatorisch probleem, geen simpele routeberekening.

Een kaarten-API "weet" niets over die andere 6 bussen of over capaciteitsgrenzen — hij berekent gewoon een route voor de stops die je hem geeft. OR-Tools (of VROOM) is specifiek gebouwd om zo'n combinatorisch zoekprobleem slim te doorzoeken en een bijna-optimale verdeling + volgorde te vinden, gegeven een kostenmatrix (reistijden) als invoer. Concreet kan een solver dus:

- de knip maken over welke kinderen bij welke bus horen (Google Maps/TomTom doen dit niet — jij zou dat zelf/manueel moeten beslissen);
- die knip herhaaldelijk herzien en duizenden alternatieve verdelingen aftoetsen op een paar seconden tijd;
- een aangepaste doelfunctie gebruiken — bv. **minimaliseer de langste rittijd van eender welk kind**, in plaats van gewoon totale afstand;
- dit alles combineren met capaciteit (max. 20/bus) én het aankomstvenster op school.

TomTom/Google Maps blijven wél noodzakelijk als **databron**: een solver kent zelf geen wegen of verkeer, hij heeft de reistijdmatrix nodig. De twee lagen zijn dus complementair, niet vervangend.

## Alternatief: scenario's testen met enkel de AI-agent + TomTom (geen solver)

Dit is een heel legitieme, lichtere aanpak — en sluit trouwens goed aan bij de voorbeelden uit de projectbeschrijving ("een bus naar Leuven inleggen", "vaste opstapplaatsen per zone"). Die scenario's zijn namelijk **door een mens (of agent) manueel bedachte indelingen**, geen door een solver berekende optimale verdeling. Voor zo'n manueel scenario is geen VRP-solver nodig: de agent stelt een indeling voor (bv. "deze 20 kinderen uit zone Leuven op bus 3, in deze volgorde"), en TomTom's Matrix/Routing API berekent gewoon de resulterende rittijden, afstanden, bezetting en aankomsttijden om dat scenario te *evalueren*. Dat is precies genoeg voor een skill die vooraf-gedefinieerde scenario's doorrekent en vergelijkt — en dat kan ik nu al bouwen, zonder solver.

De grens ligt bij het woord "geoptimaliseerd" in de projectbeschrijving: een agent die met de hand een handvol scenario's aftoetst, zal zelden de écht kortste rit per kind vinden — daarvoor is de zoekruimte te groot om manueel/intuïtief te doorzoeken (zie hierboven). Dus:

- **Wil je vooraf-bedachte scenario's (per zone, met vaste opstapplaatsen, "bus naar Leuven") laten doorrekenen en vergelijken?** → agent + TomTom volstaat, geen solver nodig. Dit kan een skill worden die je aan de school bezorgt.
- **Wil je ook weten wat de best mogelijke verdeling is (het "volledig geoptimaliseerde" scenario uit je eigen projectbeschrijving)?** → daarvoor blijft OR-Tools nuttig, gevoed met dezelfde TomTom-data.

Beide kunnen naast elkaar bestaan in dezelfde skill: TomTom voor de reistijden, optioneel OR-Tools erbij voor het scenario "volledig geoptimaliseerd".

## 3. Visualisatie

- **[Leaflet.js](https://leafletjs.com/)** + OpenStreetMap.de-tiles in een zelfgebouwde HTML-pagina: gratis, geen API-key. `tile.openstreetmap.org` is onbruikbaar voor lokaal `map.html`: OSMF eist een HTTP-Referer, `file://` stuurt die niet, resultaat is 403 "Access blocked". Esri World Street Map zit als tweede basemap in de layer control. Publieke bushaltes en stations (De Lijn, TEC, NMBS) komen als overlay via de [Overpass API](https://overpass-api.de/) (OSM-data, disk-cache in `.cache/overpass/`), uitzetbaar in de kaart.
- **Mapbox GL**: mooiere styling, vergt een token/quota.
- **Google My Maps**: handig om manueel te verfijnen, niet automatiseerbaar.
- **QGIS**: volwaardige desktop-GIS, overkill voor scenario-presentatie.

→ Voorstel: routes/scenario's als GeoJSON laten genereren, gerenderd in een Leaflet-artifact.

## Aandachtspunt: privacy van kinderdata

Thuisadressen van minderjarigen zijn gevoelige persoonsgegevens. Het datapakket bevat geen adressen: alleen anonieme coördinaten en willekeurige ids. TomTom krijgt diezelfde anonieme coördinaten — geen adressen. Overpass krijgt alleen een bounding box rond de scenario-geometrie (geen adressenlijst). Geen juridisch advies, maar wel een factor om in het achterhoofd te houden zodra er met échte leerlingdata gewerkt wordt.

## Beslissingen (14/09/2026)

- **Geodata-bron: TomTom** (cloud, verkeersbewust), **hybride ingezet**: MCP-connector voor interactief verkennen, REST met eigen `TOMTOM_API_KEY` (uit `.env`) voor de evaluator. Matrix Routing v2 via REST bevestigd werkend op 14/09/2026 (`scripts/verify_matrix_routing.py`). Connector zelf nog te activeren (zie actielijst).
- **Schaal: 7 bussen, ±20 kinderen/bus (±140 leerlingen totaal).**
- **Leerlingdata/buscapaciteiten: nog niet beschikbaar.** Eerste iteratie start met een klein fictief/steekproef-voorbeeld rond Hoegaarden.
- **Optimalisatie-laag: OR-Tools, niet Google Route Optimization.** Geverifieerd dat Google's API optimaliseert op vlootkost (vaste kost, uren, km, boetes), niet op individuele rittijd — geen ingebouwd objectief voor "kortste rit per kind". Daarom voorlopig niet gebruikt als solver. Wel genoteerd om apart te verkennen via hun open-source GUI-demo ([js-route-optimization-app](https://github.com/googlemaps/js-route-optimization-app)), zelf te deployen op een eigen Google Cloud-project.
- **Gemini/"Grounding with Google Maps"**: vermoedelijk hetzelfde agent-over-Maps-API-patroon als wat wij met Claude opzetten, geen aparte VRP-oplosser — niet bevestigd via de video zelf (kon niet bekeken worden), wel via Google's eigen documentatie over dat patroon.
- Een aparte MCP-server voor Google Maps hosten is voor dit project waarschijnlijk niet nodig — één REST-call rechtstreeks vanuit de skill volstaat.

De optimalisatie- en connector-keuze in deze lijst is bijgesteld op 16/09 en 22/09: de plugin-solver is de stdlib-solver, en de scenario-evaluator volgt één CLI-tabel zonder TomTom-connector. Zie de beslissingen van die data.

## Beslissingen (15/09/2026)

- **Kaart-basemap: OpenStreetMap.de**, met Esri straten als tweede laag. Niet `tile.openstreetmap.org`: lokaal geopende `map.html` heeft geen HTTP-Referer en OSMF blokkeert die requests (403). CARTO Voyager toont zonder key een "API KEY REQUIRED"-watermerk.
- **Publieke OV-haltes als overlay**: De Lijn, TEC en NMBS via Overpass API, gefilterd op Belgische operator-tags (`ref:De_Lijn`, `ref:TEC` / `network=TEC*`, `railway=station|halt` + NMBS/SNCB of `uic_ref` 88…). Resultaat gecachet in `.cache/overpass/`. Mislukte fetch → waarschuwing, scenario gaat door, kaart zonder overlay. In `map.html` uitzetbaar via Leaflet layer control.

## Beslissingen (16/09/2026)

- **Offline-modus:** `evaluate --offline` rekent een scenario door op de matrix in het datapakket, zonder TomTom-key of netwerk. Tijden komen uit de cellen; km zijn hemelsbreed × wegenfactor (`km_estimated: true`); de kaart toont rechte lijnen. Definitieve cijfers en wegen blijven `evaluate` (TomTom `calculateRoute`).
- **Matrix in het datapakket:** de reistijdmatrix leeft in `<data>/matrix/` (default `docs/samples/matrix/`), niet meer alleen in `.cache/tomtom/cells/`. Eén keer ophalen: ±8.000 transacties voor de ~141 punten van de fictieve set; een nieuw punt kost ±280 transacties (rij + kolom). Daarna is offline-evaluatie onbeperkt en gratis.

## Beslissingen (24/09/2026)

- **Pluginversie die de agent noemt.** `plugin.json` had al een versie, maar de agent meldde die alleen als GitHub een nieuwere Release had. `busroutes --version` leest `__version__` (gelijk aan `pyproject.toml`; `scripts/build_plugin.py --check` weigert afwijking). De plugin-skill zegt die zin aan het begin van een sessie, en daarna pas of er een nieuwere Release is.

- **Waarom de kaart in Claude leeg of grijs blijft, en wat anderen doen.** Drie sandboxes lopen door elkaar. Een gepubliceerd claude.ai-artifact (CSP gemeten door [simonw/scrape-claude-artifacts](https://github.com/simonw/scrape-claude-artifacts), oktober 2024) laat scripts van cdnjs toe en blokkeert elke externe afbeelding (`img-src` is `blob:`, `data:` en `claudeusercontent.com`). [Claude Code-artifacts](https://code.claude.com/docs/en/artifacts) (paginabeperkingen, 2026) laten scripts toe van vijf CDN's (cdnjs, unpkg, Tailwind, jQuery, geselecteerde paden op jsDelivr) en lettertypen van Google Fonts, en blokkeren nog steeds elke externe afbeelding plus `fetch` naar tile-hosts. Er is geen tile-server die daardoorheen komt. MCP-widgets lossen het anders op: zij mogen in de tool-CSP `resourceDomains` voor `openstreetmap.org` zetten ([ext-apps, ISS-voorbeeld](https://dev.to/jason_peterson_607e54abf5/visual-uis-are-now-possible-in-mcp-servers-369a)); een gepubliceerd artifact heeft dat veld niet. Een srcdoc-iframe in sommige hosts voert een statische `<script src>` niet uit; daar inline't men de bibliotheek ([three.ws](https://github.com/nirholas/three.ws/blob/main/specs/CLAUDE_ARTIFACT.md), Anthropic iframe-sandbox). Leaflet zelf is hier al cdnjs plus inline CSS en data-URI-icoontjes; de straten zijn maximaal 32 OSM.de-PNG's als data-URI (beslissing 23/09). Wat alsnog misgaat: de agent typt `map.html` over in een nieuw artifact. Dat bestand is te groot (de tiles zitten er als base64 in, plafond 16 MiB, en het genereren kost output-tokens), dus de straten vallen weg en soms ook het script. Anderen publiceren het bestaande bestand ongewijzigd, of tekenen de routes als SVG zonder rastertegels als het bestand toch door het model moet. Een `data:image/svg+xml` in het gepubliceerde bestand kan publiek delen blokkeren terwijl privé kijken wél werkt ([claude-code#81410](https://github.com/anthropics/claude-code/issues/81410)); onze tegels zijn PNG. De skill zegt daarom: publiceer `map.html` zoals `evaluate` hem schreef.

## Beslissingen (23/09/2026)

- **Artifact-basiskaart: ingebedde OSM.de-tiles.** Een gepubliceerd Claude-artifact laat scripts van cdnjs toe en blokkeert elke externe afbeelding (`img-src` beperkt tot `data:` en `blob:`). Er is geen tile-host die daardoorheen komt, dus wisselen van provider lost SR-67 niet op. `evaluate` haalt maximaal 32 PNG-tiles voor de scenariobbox op (cache `.cache/map-tiles/`) en zet ze als data-URI in `map.html`. Mislukte fetch → waarschuwing; routes en stops (SVG) blijven, de stratenlaag in het artifact niet. In een gewone browser laden zoomniveaus zonder embed alsnog live van OpenStreetMap.de, en de Esri-laag blijft beschikbaar. Leaflet-icoontjes in de CSS zijn ook data-URI's.

## Benchmark solvers (22/09/2026)

### Gebruikte data

Fictief voorbeeldpakket `docs/samples/`, gegenereerd door `scripts/generate_testset.py` (vaste seed). Geen echte leerlingdata. Het script is `scripts/bench_solvers.py`; het leest dit pakket vast in (`data_dir = docs/samples`, `BUSROUTES_REFERENCE_DATE=2026-09-15`).

| Onderdeel | Bestand | Wat erin zit |
|---|---|---|
| School | `school.json` | "de pass (Hoegaarden)", aankomst `08:30` |
| Leerlingen | `students.json` | 140 verzonnen punten rond dorpskernen in de regio, op de straat gesnapt. Zones: hoegaarden-centrum 30, tienen 24, leuven 14, meldert 10, boutersem 10, landen 10, outgaarden 8, hoksem 6, jodoigne 6, kumtich 6, bierbeek 6, linter 6, zoutleeuw 4 |
| Bussen | `buses.json` | 7 bussen (`bus1`–`bus7`), capaciteit 30, start = de school |
| Verdeling | `scenarios/<naam>.json` | Welke leerling op welke bus staat, vast. De benchmark wijzigt alleen de stopvolgorde per bus |
| Reistijden | `matrix/` | Gecachte TomTom Matrix Routing v2, `departAt=any` (historisch profiel, geen specifieke verkeersdag). Per bus alleen de paren school + stops van die bus |

De drie scenario's, elk met alle 140 leerlingen en alle 7 bussen:

| Scenario | Verdeling in het bestand |
|---|---|
| `regiobus-per-zone` | Elke bus één streek. Bus6 = Leuven/Bierbeek, bus7 = Landen/Linter/Zoutleeuw. Ophalen aan huis |
| `opstapplaatsen` | Dezelfde streken. Tienen via station en Grote Markt, Leuven via het station |
| `spreiding-gemengd` | Leerlingen willekeurig over de bussen, zones door elkaar |

Score: `evaluate --offline` op die matrix, met de standaard stilstand (30 s + 10 s per leerling). Kilometers zijn hemelsbreed × 1,3. Er is geen tweede TomTom-`evaluate` op een verkeersdag gedraaid.

Alleen volgorde. Op `regiobus-per-zone` ontbreken 13.420 van de 18.496 paren tussen bussen, dus `--assign` (stops verplaatsen) is op dit pakket niet dezelfde vergelijking. De VROOM-demoserver en Google Route Optimization zijn niet aangeroepen (die demo gebruikt OSRM; voor Google is er geen GCP-project).

| Scenario | Solver | max rit (min) | gem. rit (min) | ritten > 60 min | km | rekentijd (s) |
|---|---|---:|---:|---:|---:|---:|
| regiobus-per-zone | stdlib | 110.0 | 40.9 | 32 | 230.4 | 0.29 |
| regiobus-per-zone | pyvroom | 117.7 | 42.2 | 37 | 226.2 | 1.10 |
| regiobus-per-zone | ortools | 117.7 | 44.0 | 37 | 229.7 | 7.12 |
| opstapplaatsen | stdlib | 99.3 | 34.1 | 18 | 205.2 | 0.19 |
| opstapplaatsen | pyvroom | 101.8 | 32.4 | 20 | 204.5 | 0.68 |
| opstapplaatsen | ortools | 102.9 | 34.0 | 20 | 206.9 | 7.10 |
| spreiding-gemengd | stdlib | 180.6 | 72.4 | 76 | 709.3 | 0.26 |
| spreiding-gemengd | pyvroom | 191.1 | 88.9 | 90 | 691.6 | 1.55 |
| spreiding-gemengd | ortools | 194.4 | 97.4 | 95 | 689.4 | 7.12 |

Stdlib is `optimize --order` (2-opt/or-opt op de langste kinderrit). pyvroom 1.15 minimaliseert route-duur, met een dalende `max_travel_time` tot de rit nog haalbaar is. OR-Tools 9.15 gebruikt een tijd-dimensie, boogkost = reistijd + dwell, en `GlobalSpanCost` (1 s zoektijd per bus). Rekentijd is de zoektocht op een matrix die al in het geheugen staat.

**Aanbeveling (22/09, alleen volgorde op echte cellen): de stdlib-solver blijft de plugin-solver.** Op alle drie de scenario's heeft hij de laagste langste rit en de minste ritten boven 60 minuten. pyvroom en OR-Tools rijden iets minder kilometers en maken de langste rit langer: zij optimaliseren routeduur, niet de rit van het kind. Op `opstapplaatsen` heeft pyvroom een lager gemiddelde (32,4 tegen 34,1) en toch een hogere maximumrit; de lexicografische doelfunctie kiest het maximum eerst.

**SR-68 (23/09): geen default wijzigen.** Een klassieke TSP (boogkost = afstand, depot = school) kan dezelfde tour in de richting "eerst dicht bij school" leggen. De bus wordt er niet korter van — een tour en zijn omgekeerde zijn even lang — maar de langste kinderrit wel langer. Tot v0.4.1 deed `--ordering haversine` dat via 2-opt op padkost. Sinds v0.5.0 oriënteert die zoektocht de open rit naar school (ver eerst); `from_school` is de spiegel. `optimize --order` en `ordering: auto` met matrix scoren `(langste rit, som van de ritten, busduur)`. Sorteren op afstand tot school, verste eerst, is op een Tienen-mix slechter dan die solver, omdat de volgorde binnen de verre cluster dan zigzag is. Cijfers en de niet-reproduceerbare ticketwaarden 84,5 / 92,7 min: [sr-68-ortools-objective.md](sr-68-ortools-objective.md).

### Vervolg (23/09/2026) — ook de verdeling

`--assign` staat in [solver-benchmark.md](solver-benchmark.md). De sample-matrix heeft nog steeds geen paren tussen bussen. Beide assen gebruiken daarom één lijn door de 4.956 bestaande cellen, zodat elke solver dezelfde reistijd ziet. Op de rit van het kind blijven pyvroom en OR-Tools in de buurt van stdlib; ze rijden minder kilometers omdat ze de busduur minimaliseren. De plugin-solver blijft stdlib. VROOM hosten volgt niet uit de cijfers. OR-Tools blijft een lokale bench.

Installatie (`uv sync --group bench`, niet in CI): OR-Tools ±66 MB, pyvroom-extensie ±10 MB plus numpy ±22 MB en pandas ±44 MB. `scripts/bench_solvers.py` blijft de vergelijking op de echte cellen. De verdeling staat in `scripts/bench_full.py` en [solver-benchmark.md](solver-benchmark.md); die wacht niet meer op `fetch-matrix`.

## Beslissingen (22/09/2026) — skill

- **Eén commando per vraag.** De scenario-evaluator-skill (`skills/scenario-evaluator/SKILL.md`, dezelfde tekst in de plugin) is een tabel: scenario-JSON, `evaluate --offline`, `optimize --order` of `--assign`, pas dan één `evaluate` (ongeveer 7 TomTom-calls), daarna `map.html` en `compare`. `data status` / `add-points` / `fetch-matrix --dry-run` voor het pakket.
- **Geen TomTom-connector in de skill.** Een losse reistijd is een scenario plus `evaluate --offline`. De connector activeren is geen stap meer voor deze evaluator.
- **Datapakket buiten de plugin.** `BUSROUTES_DATA_DIR` of `--data`, default `docs/samples/`. De fictieve set is alleen het voorbeeld. Echte leerlingdata komt niet in git en niet in de plugin.
- **Ontbrekend matrixpaar is een fout.** De voorbeeldmatrix dekt de drie referentiescenario's per bus, niet de paren tussen bussen. Dan `data status` en `fetch-matrix --dry-run`, niet stil terugvallen op haversine en niet de matrix opnieuw kopen zonder opdracht.
- **`--assign` tot ongeveer 150 stops.** De skill zet daar `--max-seconds 300` op: enkele minuten, binnen vijf minuten terug. `--max-seconds` (default 30) blijft de noodrem; `--max-perturbations` (default 1000) is het reproduceerbare stoppunt. De voorbeeldmatrix dekt de paren tussen bussen niet; zonder die paren stopt `--assign`.

## Voorgestelde stack

1. **Geocoding + verkeersbewuste reistijdmatrix**: TomTom REST, eenmaal opgeslagen in het datapakket. De skill spreekt TomTom daarna alleen aan voor de definitieve kaart (`evaluate`) of een nieuw punt (`data add-points`).
2. **Scenario-evaluatie**: `evaluate --offline` op de matrix, daarna één `evaluate` met echte wegen.
3. **Volledige optimalisatie**: stdlib-solver in `busroutes optimize` (langste rit per kind). Benchmark 23/09: ook de verdeling, op één matrix; pyvroom en OR-Tools blijven buiten de plugin. Zie [solver-benchmark.md](solver-benchmark.md).
4. **Visualisatie**: Leaflet-pagina per scenario (`out/<naam>/map.html`), gevoed met GeoJSON; OSM-basemap plus Overpass-overlay voor De Lijn / TEC / NMBS.

## Volgende stappen

1. ~~TomTom REST-toegang~~ ✅ 14/09/2026 (key in `.env`, Matrix v2 smoke-test OK). De TomTom Maps-connector activeren is geen stap meer voor de evaluator (beslissing 22/09).
2. ~~Fictieve testset opbouwen~~ ✅ 14/09/2026 — `docs/samples/` (140 leerlingpunten, 7 bussen, 3 referentiescenario's, `expected/`).
3. ~~Eerste versie van de scenario-evaluator~~ ✅ 14/09/2026 — `busroutes` CLI (`evaluate`/`compare`) + skill. Vervolgwensen staan onderaan `.agent/plans/2026-09-14-testset-en-evaluator-v1.md`.
4. ~~Offline-modus + matrix in het datapakket~~ ✅ 16/09/2026 — `evaluate --offline`, `busroutes data status|fetch-matrix|add-points`, matrix in `docs/samples/matrix/`.
5. ~~Stdlib-solver (`busroutes optimize`)~~ ✅ 16/09/2026 (WP3) — `optimize --order|--assign` op de matrix, zonder TomTom.
6. ~~Benchmark pyvroom / OR-Tools~~ ✅ 22/09/2026 volgorde op echte cellen; ✅ 23/09/2026 ook `--assign`, op één lijn door die cellen (`docs/solver-benchmark.md`). Stdlib blijft de plugin-solver.
7. ~~Skill herschreven naar één beslissingstabel~~ ✅ 22/09/2026 (WP5).
8. ~~Schaalfix `optimize --assign`~~ ✅ 22/09/2026 — 140 stops binnen 35 s, 150 stops binnen 90 s op een synthetische matrix; skill vraagt `--max-seconds 300` voor een volledige schoolset.
9. Zodra de school data levert (WP6): adressen of coördinaten, buscapaciteiten, beltijd, eventuele vaste opstapplaatsen. Daarna `data geocode` en `fetch-matrix` (eerst `--dry-run`). Google's route-optimization-demo op een eigen GCP-project hoort niet bij dit pad.
