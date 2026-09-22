# Routeplanning voor de schoolbussen van de pass

De plugin plant de zeven schoolbussen van de pass in Hoegaarden. Het doel is een zo kort mogelijke rit per kind.

Je stelt een vraag in gewone taal, bijvoorbeeld een bus die kinderen uit één streek ophaalt, vaste opstapplaatsen, of een andere verdeling over de bussen. De plugin volgt altijd dezelfde volgorde.

## De flow

Dezelfde volgorde staat uitgetekend in de [routepijplijn](docs/routepijplijn.html).

1. **De invoer, eenmalig.** Waar de school is en hoe laat de bussen er moeten zijn, waar elk kind opstapt, en hoeveel kinderen er in elke bus passen. Die map blijft bij de school en zit niet in de plugin.
2. **De matrix.** TomTom levert één keer de reistijd van elk punt naar elk ander punt. Die tabel blijft bij de school. Een nieuwe opstapplaats vult een rij en een kolom aan. Je ziet eerst hoeveel nieuwe reistijden TomTom daarvoor moet ophalen. Die haalt TomTom pas op nadat je akkoord geeft.
3. **Beschrijf het scenario.** Welke kinderen op welke bus, waar ze opstappen, en of een bus of een opstapplaats moet blijven zoals hij is.
4. **Eerst een schatting.** De tijden komen uit de matrix. De kaart toont nog rechte lijnen, en de kilometers zijn een schatting.
5. **Een kortere rit, als je dat wilt.** De plugin gebruikt dezelfde matrix: een betere volgorde van de stops, of een andere verdeling over de bussen. Een bus of een opstapplaats kun je vastzetten. Daarna opnieuw een schatting.
6. **De weg op de kaart.** Voor het scenario dat vastligt, rekent TomTom één keer de rit in de volgorde van de stops. Dezelfde vraag op dezelfde datum geeft dezelfde cijfers.
7. **Vergelijk.** Doorslaggevend zijn de langste rit en de gemiddelde rit per kind.

## Voorbeelden

- Reken dit scenario eerst uit: bus 3 haalt de kinderen uit Tienen op.
- Zoek een kortere rit voor bus 6. De andere bussen blijven zoals ze zijn.
- Verdeel de kinderen opnieuw. De opstapplaats in Leuven blijft op dezelfde bus.
- Geef me de echte tijden en de kaart voor dit scenario.

## Wat je nodig hebt

- Het plugin-bestand van de [laatste release](https://github.com/markminnoye/de-pass-routeplanning/releases/latest). Je vervangt de plugin in Claude via Plugin → Add.
- De map van de school met leerlingen, bussen en opstapplaatsen. Die map zit niet in de plugin.
- Een TomTom-sleutel, alleen voor de echte tijden en voor een nieuwe opstapplaats. Aanmaken op [developer.tomtom.com](https://developer.tomtom.com/).

## Privacy

Leerlinggegevens blijven in de map van de school. Ze horen niet in deze plugin en niet in git. TomTom krijgt coördinaten, alleen voor de echte tijden of een nieuw punt.

Op de releasepagina staat per versie wat er voor de school anders is.
