# 🚌 Schoolbus Routeplanner · "de pass" Hoegaarden

[![Claude Plugin](https://img.shields.io/badge/Claude_Plugin-v0.5.0-6366f1?style=flat&logo=anthropic)](https://github.com/markminnoye/de-pass-routeplanning/releases/latest)
[![GDPR Compliant](https://img.shields.io/badge/GDPR-Privacy_by_Design-059669?style=flat)](#-privacy-gdpr--data-integriteit)

> **AI-gestuurde routeplanning voor de 7 schoolbussen van buitengewoon onderwijs "de pass" in Hoegaarden. Niet gericht op de laagste vlootkost, maar op wat écht telt: een zo kort mogelijke rit per kind.**

---

## 🎯 Waarom deze tool?

De school **"de pass"** in Hoegaarden brengt dagelijks zo'n 140 leerlingen met 7 bussen naar school en weer thuis. 

Klassieke navigatiesoftware berekent routes meestal voor transportbedrijven: zo min mogelijk diesel voor de busmaatschappij. Het gevolg in de praktijk is dat sommige kinderen vandaag **meer dan 2 uur** op de bus zitten voor een enkele rit — nodeloos lang voor een rit van amper enkele tientallen kilometers.

**Deze tool draait de prioriteit om:**

- 🧒 **Het kind staat centraal:** we zoeken altijd naar routes die de individuele reistijd minimaliseren en extreme uitschieters wegwerken.
- ⚡ **Direct scenario's vergelijken:** binnen enkele seconden zie je het effect van een wijziging (bijvoorbeeld een regiobus of een vaste opstapplaats).
- 💬 **Geen programmeerkennis nodig:** je praat gewoon in je eigen taal met Claude.

---

## ✨ Wat kan je met deze tool?

In plaats van handmatig puzzelen met spreadsheets of dure adviesbureaus in te schakelen, stel je direct vragen aan Claude in mensentaal:

* 📍 **Regiobussen uittesten:** *"Wat gebeurt er als bus 3 alle leerlingen rond Tienen ophaalt via een snelle verbinding?"*
* 🚏 **Vaste opstapplaatsen simuleren:** *"Wat als we in Leuven een centrale opstapplaats gebruiken aan het station in plaats van deur-aan-deur?"*
* 🔄 **Bussen herverdelen:** *"Verdeel de leerlingen opnieuw over bus 1 en 2 zodat niemand langer dan 45 minuten op de bus zit."*
* 🗺️ **Interactieve kaarten bekijken:** bekijk de echte wegen inclusief haltes van De Lijn en TEC.

---

## 🚀 Hoe het werkt

De routeplanner volgt een heldere, betrouwbare flow:

![Overzicht werkwijze](docs/images/overzicht-werkwijze.svg)

```mermaid
flowchart LR
    A["📁 1. Geanonimiseerde data<br/><i>(GPS-punten & bussen)</i>"] --> B["💬 2. Vraag in Claude<br/><i>(In je eigen taal)</i>"]
    B --> C["⚡ 3. Slimme Rekenhulp<br/><i>(Kortste rit per kind)</i>"]
    C --> D["🗺️ 4. Kaart & Cijfers<br/><i>(Echte wegen & tijden)</i>"]
```

1. **Geanonimiseerde gegevens (éénmalig):** De school gebruikt een lijst met de 7 bussen en anonieme GPS-punten (zonder namen, straatnamen of huisnummers).
2. **Vraag stellen:** Je typt in Claude wat je wilt onderzoeken (gewoon in je eigen taal).
3. **Slimme berekening:** De plugin berekent razendsnel verschillende combinaties om de ritten zo kort mogelijk te maken.
4. **Visuele kaart:** Claude toont direct een vergelijkingstabel én een interactieve kaart met de echte straten en haltes.

---

## 💡 Wat doet deze plugin onder de motorkap?

Voor wie benieuwd is wat de code achter de schermen doet:

> **De plugin fungeert als het gespecialiseerde routebrein voor Claude.**
>
> 1. **Matrix-rekenkracht:** De code berekent en bewaart de reistijden tussen alle haltepunten. 
> 2. **Wiskundige optimalisatie:** Zodra je een vraag stelt, doorzoekt het algoritme razendsnel tienduizenden combinaties om de optimale volgorde van stops te vinden waarbij geen enkel kind nodeloos lang onderweg is.
> 3. **Echte wegendata via TomTom:** Pas wanneer een scenario op punt staat, berekent de plugin éénmalig de exacte bochten, straten en keertijden via TomTom.
> 4. **Kaartgenerator:** Tot slot genereert de code een complete, interactieve routekaart (`map.html`) die je direct in Claude of in je browser kunt bekijken.

---

## 📊 Wat levert het op? (Voorbeeld)

Door een slimme herverdeling of het toevoegen van strategische opstapplaatsen worden ritten merkbaar korter en aangenamer:

![Voorbeeldvergelijking](docs/images/scenario-vergelijking-visual.svg)

| Criterium | Huidige situatie | Met geoptimaliseerd scenario | Winst per kind |
|:---|:---:|:---:|:---:|
| ⏱️ **Langste rit per kind** | > 120 min (meer dan 2u) | **48 min** | **> 1 uur korter** 🎉 |
| 🌅 **Vroegste vertrekuur** | **05:50** 's ochtends | **07:15** 's ochtends | **+1u25 nachtrust** |
| 🚌 **Gemiddelde rit per kind** | 42 min | **26 min** | **-16 min winst** |
| 🛣️ **Totale kilometers vloot** | 295 km | **248 km** | **-47 km minder uitstoot** |

---

## 💻 Installeren in Claude Desktop

Deze tool is direct beschikbaar als een **Claude Plugin** (`.plugin`). Je hoeft niets te programmeren of te compileren.

### Stappenplan:
1. **Download de plugin:**  
   Download het bestand `de-pass-routeplanning.plugin` van de [meest recente release](https://github.com/markminnoye/de-pass-routeplanning/releases/latest).
2. **Open Claude Desktop:**  
   Open de Claude Desktop-applicatie op je computer.
3. **Plugin toevoegen:**  
   Ga naar het menu **Settings** (Instellingen) ➔ **Plugins** (of kies *Add Plugin*). Selecteer het gedownloade `.plugin`-bestand.
4. **Koppel je datamap:**  
   Plaats de gegevensmap van de school (met anonieme haltecoördinaten en buscapaciteiten) in een map op je computer en verwijs ernaar in Claude.
5. **Klaar voor gebruik!**  
   Open een nieuw gesprek en begin direct met vragen stellen.

---

## 💬 Voorbeeldvragen voor Claude

Zodra de plugin actief is, kan je Claude vragen:

* *"Reken de huidige situatie door en geef me de 3 langste ritten."*
* *"Wat als we een centrale opstapplaats voorzien aan het station van Tienen voor bus 3?"*
* *"Zoek een betere volgorde voor bus 6 zodat de reistijd daalt."*
* *"Toon me de interactieve kaart met alle haltes van scenario 2."*
* *"Vergelijk het huidige scenario met het voorstel voor regiobussen in een tabel."*

---

## 🔒 Privacy, GDPR & Data-integriteit

Thuisadressen en identiteiten van minderjarige leerlingen zijn gevoelige informatie:

* 🛡️ **Zero PII (Geen persoonsgegevens):** Er worden nergens namen, voornamen, straatnamen of huisnummers opgeslagen of uitgewisseld.
* 📍 **100% Geanonimiseerd:** Leerlingen worden uitsluitend geregistreerd met willekeurige identificatienummers (zoals `s001`, `s002`) en anonieme GPS-coördinaten (bv. een straathoek of opstapplaats).
* 🔒 **Privacy by Design:** Zowel intern in het rekenalgoritme als bij het opvragen van reistijden bij TomTom worden uitsluitend anonieme coördinaten gebruikt. Er worden geen persoonsgegevens gebruikt of opgeslagen.
