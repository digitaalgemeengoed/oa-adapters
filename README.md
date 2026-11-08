# oa-adapters

**Adapters per werkomgeving** voor de Office Assistent. Een adapter is de dunne schakel tussen één werkomgeving en de assistent: levert de inhoud, neemt haar terug en zegt wat de omgeving kan. Hij heeft geen sleutels, geen tokens en geen gegevens. Het paneel is in elke werkomgeving hetzelfde.

> Onderdeel van het werkende prototype van de Office Assistent. Een prototype, geen product.

## Werkomgevingen

| Werkomgeving | Adapter | Vermogens | Pagina |
|---|---|---|---|
| Demo-tekstverwerker | `DemoEditorAdapter` (rijk of beperkt) | alle, of alleen de drie basisvermogens | `/werkomgeving` |
| Microsoft Word, ook Word voor het web | `StructuurAdapter` + `WordTekstverwerker` (Office.js, WordApi 1.3) | basis, segment-vervangen, plek-tonen, afdruk-schrijven | `/word/taskpane.html`, manifest op `/word/manifest.xml` |
| LibreOffice Writer op de eigen computer | `StructuurAdapter` + `LibreOfficeTekstverwerker` (extensie met lokale brug) | basis, segment-vervangen, plek-tonen, afdruk-schrijven | `/libreoffice` |
| Collabora Online | `CollaboraAdapter` (postMessage en WOPI) | basis, afdruk-schrijven | `/collabora` |

Collabora laat zien hoe de assistent terugvalt: deelvervangen kan daar niet, dus vervangt hij het hele document en laadt het opnieuw.

## Hoe Word en LibreOffice werken

Word en LibreOffice beschrijven een document als alinea's met een stijl, lijsten, tabellen, afbeeldingen en links. De adapter leest die structuur als **blokken** (`src/semantisch.ts`) en maakt er semantische html van; daar werken de assistent-services mee. Een herstelling komt terug als html-segment; `segmentNaarOpdracht` maakt daar een **opdracht** van die de tekstverwerker zelf uitvoert:

| Bevinding | Opdracht in Word en LibreOffice |
|---|---|
| Vette tekst die een kop is; overgeslagen kopniveau | Kopstijl zetten (Heading N) |
| Tabel zonder kopcellen | Eerste rij als kopregel (Word: headerRowCount; Writer: "kop herhalen") |
| Afbeelding zonder alternatieve tekst | Alternatieve tekst van de afbeelding |
| Vage linktekst | Linktekst vervangen, adres blijft |

Zo blijft de opmaak van het document staan. Voor elke opdracht controleert de adapter of de alinea nog dezelfde tekst heeft; is het document intussen gewijzigd, dan vraagt hij om opnieuw te beoordelen.

### Word

Een invoegtoepassing met een takenvenster. In Word voor het web staat dat venster in een iframe van office.com; daar komt het cookie van de integratielaag niet aan. Het inloggen gebeurt daarom in een apart venster van Office (`/word/aanmelden.html`), dat na het inloggen een sessiesleutel aan het takenvenster geeft; die gaat als `Authorization`-kop mee, alleen in het geheugen.

### LibreOffice

`libreoffice-extensie/` is een Python-extensie (`.oxt`). Het menu **Office Assistent → Assistent openen bij dit document** start een kleine webserver op `127.0.0.1` en opent het paneel in de browser, met poort en sleutel na het `#` in het adres. De brug antwoordt alleen met die sleutel, alleen aan het adres van de eigen integratielaag, en alleen over dat ene document; elke bewerking loopt via de hoofdthread van LibreOffice. De integratielaag levert de extensie uit met haar eigen adres erin (`/libreoffice/office-assistent.oxt`).

### Collabora Online

Collabora draait in een iframe. De integratielaag is de bestandsserver (WOPI) van de werkbestanden; deze pagina praat met Collabora via postMessage (`Host_PostmessageReady`, `Action_Save`). Voor de assistent zet de integratielaag het werkbestand met Collabora om naar html, en bij de terugval weer naar docx.

## Bouwen en testen

```
npm run build     # dist/web: alle pagina's, plus dist/web/libreoffice/office-assistent-basis.oxt
npm test          # typecontrole en de tests van semantisch.ts en StructuurAdapter
npm run dev       # ontwikkelserver; /api gaat naar de integratielaag op poort 3000
```

De extensie is getest tegen een echte LibreOffice (headless): start `soffice --headless --accept="socket,host=127.0.0.1,port=2002;urp;"` en draai `python3 libreoffice-extensie/test/test_document.py` en `test_brug.py`.

**Nog niet getest:** de Word-invoegtoepassing in een echte Word (Office.js is hier niet te draaien) en Collabora Online zelf (de pagina en de WOPI-host wel, tegen een nagebootste Collabora die met LibreOffice omzet).

## Een adapter toevoegen

Implementeer `Adapter` uit `@digitaalgemeengoed/oa-contract` en geef in `werkomgeving()` eerlijk op welke vermogens de omgeving heeft. Alleen de drie basisvermogens zijn verplicht. Heeft de omgeving een structuur zoals Word, implementeer dan `Tekstverwerker` en gebruik `StructuurAdapter`.

## Licentie

© 2026 Gemeente Haarlem. EUPL 1.2, zie `LICENSE`.

Gemaakt door Erik Hoekstra, programma-architect en senior consultant, afdeling i-Ontwikkeling, Gemeente Haarlem, met assistentie van Claude (Anthropic).
