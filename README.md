# oa-adapters

**Adapters per werkomgeving** voor de Office Assistent, en een demo-werkomgeving. Een adapter is de dunne schakel tussen één werkomgeving en de assistent: levert de inhoud, neemt haar terug en zegt wat de omgeving kan. Hij heeft geen sleutels, geen tokens en geen gegevens.

> Onderdeel van het werkende prototype van de Office Assistent. Een prototype, geen product.

## Adapters

| Adapter | Werkomgeving | Status |
|---|---|---|
| `DemoEditorAdapter` | Demo-tekstverwerker (bewerkbaar html) | fase 1 |
| Collabora | Collabora Online via postMessage | gepland, fase 2 |
| Office | Word en Outlook via Office.js | gepland |
| Nextcloud | Zijbalk in Nextcloud Files | gepland |
| Webmail | Mailomgeving | gepland, met ELSA |

De demo-adapter kent twee standen. **Rijk** levert alle optionele vermogens; **beperkt** alleen de drie basisvermogens. Zo is in één werkomgeving te zien hoe de assistent terugvalt: het hele document opnieuw laden in plaats van één deel vervangen, geen sprong naar de plek, en geen identificatie in het bestand.

## Demo-werkomgeving

`werkomgeving/` is een eenvoudige tekstverwerker met het paneel ernaast en een verzonnen raadsvoorstel met bewuste toegankelijkheidsfouten. De werkomgeving bewaart haar eigen document en de eigenschappen ervan in de browser, zoals een tekstverwerker een bestand op schijf bewaart; de assistent bewaart niets.

```
npm run build     # dist/werkomgeving, uitgeleverd door de integratielaag op /werkomgeving
npm run dev       # ontwikkelserver; /api gaat naar de integratielaag op poort 3000
```

## Een adapter toevoegen

Implementeer `Adapter` uit `@oa/contract` en geef in `werkomgeving()` eerlijk op welke vermogens de omgeving heeft. Alleen de drie basisvermogens zijn verplicht. Een omgeving die niets anders kan dan een mededeling tonen, kan zo toch meedoen.

## Licentie

© 2026 Gemeente Haarlem. EUPL 1.2, zie `LICENSE`.

Gemaakt door Erik Hoekstra, programma-architect en senior consultant, afdeling i-Ontwikkeling, Gemeente Haarlem, met assistentie van Claude (Anthropic).
