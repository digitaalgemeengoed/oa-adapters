# oa-adapters

**Adapters per werkomgeving** voor de Office Assistent. Een adapter is de dunne schakel tussen één werkomgeving en de assistent: levert de inhoud, neemt haar terug en zegt wat de omgeving kan. Hij heeft geen sleutels, geen tokens en geen gegevens. Het paneel is in elke werkomgeving hetzelfde.

> Onderdeel van het werkende prototype van de Office Assistent. Een prototype, geen product.

## Werkomgevingen

| Werkomgeving | Adapter | Vermogens | Pagina |
|---|---|---|---|
| Demo-tekstverwerker | `DemoEditorAdapter` (rijk of beperkt) | alle, of alleen de drie basisvermogens | `/werkomgeving` |
| Microsoft Word, ook Word voor het web | `StructuurAdapter` + `WordTekstverwerker` (Office.js, WordApi 1.3) | basis, segment-vervangen, plek-tonen, afdruk-schrijven | `/word/taskpane.html`, manifest op `/word/manifest.xml` |
| LibreOffice Writer op de eigen computer | zijpaneel in Writer (Python, zelfde regels als `semantisch.ts` en `oa-kern`); of het paneel in de browser via `StructuurAdapter` + `LibreOfficeTekstverwerker` | basis, segment-vervangen, plek-tonen, afdruk-schrijven, bestand-opleveren | zijbalk **Assistent**; `/libreoffice` |
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

`libreoffice-extensie/` is een Python-extensie (`.oxt`) met twee manieren om de assistent te gebruiken.

**Het zijpaneel (standaard).** Een eigen tabblad **Assistent** in de zijbalk van Writer, naast de Navigator. LibreOffice heeft geen browser in de zijbalk, dus dit paneel is gebouwd met de eigen schermelementen van LibreOffice (`pythonpath/oa_zijpaneel.py`). Het doet hetzelfde als het paneel in de browser: metadata met voorstellen, registreren (het .odt is de versie, de html de weergave), versies vastleggen, toegankelijkheid beoordelen, een plek tonen en herstellen.

- `oa_kern.py` bevat de regels van `oa-kern` (metadateren, herstellen) en `src/semantisch.ts` in Python. `test/test_kern.py` vergelijkt beide op dezelfde voorbeelden (`test/kruis.json`): wie de ene wijzigt, ziet de test falen tot de andere mee is.
- `oa_paneelmodel.py` is wat het paneel weet en doet, zonder UNO (getest met een nepdocument); `oa_verbinding.py` praat met de integratielaag, met de sessie als `Authorization: Bearer` en `x-oa-verzoek`, net als de Word-invoegtoepassing.
- **Aanmelden** gaat één keer via de browser (Keycloak met tweede factor). De extensie start dan een server op `127.0.0.1` die alleen de sessiesleutel aanneemt, met een eenmalige sleutel na het `#` van `/libreoffice#aanmelden=…`, alleen van de eigen integratielaag, binnen tien minuten. De pagina vraagt de sessie op bij `/api/auth/koppel` en geeft hem door. De sessie staat alleen in het geheugen van LibreOffice.
- Acties lopen in een eigen thread; het document wordt alleen op de hoofdthread gelezen en gewijzigd (`AsyncCallback`). Het paneel tekent zich daarna opnieuw, nooit midden in een opmaakronde van de zijbalk.
- Getest in een echte LibreOffice 24.2 (GTK en X11) op een virtueel scherm: aanmelden, registreren, beoordelen, tonen, herstellen (kop, alternatieve tekst, kopregel), versie vastleggen, opslaan en heropenen.

![Het zijpaneel Assistent in LibreOffice Writer](docs/zijpaneel-libreoffice.png)

**Het paneel in de browser.** **Office Assistent → Assistent in de browser openen** start een kleine webserver op `127.0.0.1` en opent het paneel in de browser, met poort en sleutel na het `#` in het adres. De brug antwoordt alleen met die sleutel, alleen aan het adres van de eigen integratielaag, en alleen over dat ene document; elke bewerking loopt via de hoofdthread van LibreOffice.

De integratielaag levert de extensie uit met haar eigen adres erin (`/libreoffice/office-assistent.oxt`).

```
npm run build     # dist/web: alle pagina's, plus dist/web/libreoffice/office-assistent-basis.oxt
npm test          # typecontrole en de tests van semantisch.ts en StructuurAdapter
npm run dev       # ontwikkelserver; /api gaat naar de integratielaag op poort 3000
```

De extensie is getest tegen een echte LibreOffice (headless): start `soffice --headless --accept="socket,host=127.0.0.1,port=2002;urp;"` en draai `python3 -m pytest libreoffice-extensie/test` (de kruistest heeft ook node nodig).

**Nog niet getest:** de Word-invoegtoepassing in een echte Word (Office.js is hier niet te draaien) en Collabora Online zelf (de pagina en de WOPI-host wel, tegen een nagebootste Collabora die met LibreOffice omzet).

## Een adapter toevoegen

Implementeer `Adapter` uit `@digitaalgemeengoed/oa-contract` en geef in `werkomgeving()` eerlijk op welke vermogens de omgeving heeft. Alleen de drie basisvermogens zijn verplicht. Heeft de omgeving een structuur zoals Word, implementeer dan `Tekstverwerker` en gebruik `StructuurAdapter`.

## Licentie

© 2026 Gemeente Haarlem. EUPL 1.2, zie `LICENSE`.

Gemaakt door Erik Hoekstra, programma-architect en senior consultant, afdeling i-Ontwikkeling, Gemeente Haarlem, met assistentie van Claude (Anthropic).
