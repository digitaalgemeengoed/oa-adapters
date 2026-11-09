# Wijzigingen

## 0.12.0 — 2026-11-09

**LibreOffice Writer: anonimiseren in het document** (extensie 0.10.0).

- Plaatshouders staan in de tekst met een bladwijzer eromheen (`oa-pii p12 [PERSOON 1] v`), gekleurd per niveau en met een gestippelde rand zolang het een voorvertoning is (`oa_pii.py`).
- Klik je in een plaatshouder, dan opent het paneel de kaart (selectieluisteraar; het paneel vraagt het elke 0,7 seconde op, via het kanaal van de zijbalk of via http). Een cursor direct naast een plaatshouder telt niet.
- Rechtermuisknop op een selectie: "Anonimiseer selectie (Assistent)"; ook als knop in de werkbalk Assistent.
- Het versienummer als eigen documenteigenschap Versie (Bestand → Eigenschappen).
- Met een oudere extensie werkt anonimiseren zoals in 0.10.0 (voorbeeld in het paneel), met een melding om de nieuwe te installeren.
- De brug noemt de versie uit description.xml.

Getest tegen een echte LibreOffice (zonder scherm) met het paneel in de browser: zoeken, klikken, laat staan, selectie toevoegen, bevestigen. Niet getest: het rechtermuismenu (vraagt een LibreOffice met scherm). Calc en Impress volgen.

## 0.11.0 — 2026-11-09

- Demo-werkomgeving: plaatshouders als gemarkeerde elementen in het document (kleur per niveau, gestippeld bij voorvertoning), klik naar het paneel, per plek terugzetten, eigenschap Versie. Rechtermuisknop op een selectie: "Anonimiseer selectie".
- Werkbalk: knop Anonimiseer selectie (waar de werkomgeving de selectie kan doorgeven).

## 0.10.0 — 2026-11-09

Anonimiseren bij de bron: de vermogens `tekst-vervangen` en `selectie-lezen`, in alle werkomgevingen. Vervangen gaat altijd als heel woord ("Jan" niet in "Janssen"), hoofdlettergevoelig, de langste waarde eerst.

| Werkomgeving | Vervangen | Selectie |
|---|---|---|
| Demo (rijk) | tekstknopen | ja |
| Word | `body.search` (heel woord) + `insertText` | ja |
| Excel | per cel met vaste tekst, niet in formules | geselecteerde cellen |
| PowerPoint | per tekstvak met `getSubstring` (PowerPointApi 1.4); de rest van de opmaak blijft | geselecteerde tekst (1.5) |
| LibreOffice Writer, Calc | zoeken en vervangen van LibreOffice (ICU, woordgrens) | ja |
| LibreOffice Impress | per tekstvak met een tekstcursor | ja |
| Collabora | `.uno:ExecuteSearch` via postMessage; telt voor en na in het opgeslagen bestand | nee |

LibreOffice-extensie 0.9.0: nieuwe vragen `/tekst-vervangen` en `/selectie` (`oa_tekst.py`). Een oudere extensie geeft een duidelijke melding: installeer de nieuwe versie.

## 0.9.1 — 2026-11-09

Paneel 0.6.0 met de module Anonimiseren. De knop Anonimiseren in de werkbalk van LibreOffice heet niet meer "(volgt)"; extensie 0.8.1.

## 0.9.0 — 2026-11-09

**Knoppen van de assistent in de werkbalk**, in elke werkomgeving: Paneel, de modules, Beoordelen (zoals de demo).

- LibreOffice (Writer, Calc, Impress): werkbalk **Assistent** (`Addons.xcu`, `*WindowState.xcu`, pictogrammen in `icons/`). Een knop opent de zijbalk op de module; het webpaneel krijgt de opdracht via WebKit. In de zijbalk staan de knoppen van het paneel bovenaan (rechts staan de tabbladen van LibreOffice zelf). Extensie 0.8.0.
- Collabora: knoppen in de werkbalk van Collabora zelf (postMessage `Insert_Button`, terug `Clicked_Button`); pictogrammen van ons eigen adres (`statisch/iconen/`).
- Demo-werkomgeving: een groep knoppen in de werkbalk.
- Word, Excel en PowerPoint: functies voor de knoppen op het tabblad Assistent (gedeelde runtime; de integratielaag 0.7.0 levert het manifest).
- `src/host/assistentknoppen.ts`, `scripts/maak-iconen.mjs`.
- LibreOffice: een knop werkt in het venster waarin hij werd ingedrukt; het webpaneel tekent na het openklappen opnieuw (in Calc bleef de bovenrand anders leeg).

## 0.8.0 — 2026-11-08

- **Excel en PowerPoint**: de invoegtoepassing werkt ook in Excel en PowerPoint (één manifest, één takenvenster; de integratielaag 0.6.0 levert het manifest). `ExcelAdapter` en `PowerPointAdapter` (`src/office/`) leveren bladen en dia's als secties, zoals LibreOffice en Collabora, en herstellen op een plek: blad hernoemen, titel van een dia (zonder titel: een tekstvak "Titel"), alternatieve tekst. Origineel als xlsx of pptx; de afdruk in de instellingen van de invoegtoepassing.
- Het takenvenster controleert de versie per programma (WordApi 1.3, ExcelApi 1.9, PowerPointApi 1.4).
- Getest tegen een nagebootst Office.js (`test/office.test.ts`), niet in een echte Excel of PowerPoint.

## 0.7.0 — 2026-11-08

- **Collabora**: nieuwe voorbeelden als tekst, rekenblad of presentatie. Voor ods en odp herstelt de adapter op een plek via de integratielaag (`/segment`) en laadt Collabora daarna opnieuw.

- **LibreOffice Calc en Impress**: het zijpaneel staat ook in Calc en Impress. `oa_bladen.py` levert een rekenblad als bladen en een presentatie als dia's (secties met de naam of titel als kop) en herstelt op een plek: blad hernoemen, titel van een dia (ook als de dia geen titelvak heeft), alternatieve tekst. Het origineel is .ods of .odp.
- `LibreOfficeBladenAdapter` voor het webpaneel; de brug kent `/html`, `/segment` en `/plek`.
- Het eigen paneel (optie 2) werkt nog alleen in Writer en zegt dat in Calc en Impress.
- Getest in LibreOffice 24.2 met de regels van oa-services 0.3.0 (`test/test_bladen.py`) en met het webpaneel in de zijbalk.

## 0.6.0 — 2026-11-08

- **Het webpaneel van de server in de zijbalk van Writer** (optie 1, zoals MIRA): een WebKitGTK-webweergave in het vlak van het zijpaneel, met hetzelfde React-paneel als in de browser en Word. Linux met de GTK-weergave van LibreOffice; vereist `python3-gi` en `gir1.2-webkit2-4.1`.
- Berichtkanaal van WebKit naar de brug (`window.webkit.messageHandlers.oaBrug`), omdat een https-pagina geen http naar 127.0.0.1 mag; de pagina kiest het vanzelf.
- Het eigen paneel blijft als alternatief (optie 2) en als terugval op Windows, macOS of zonder WebKitGTK; kiezen via het menu Office Assistent.
- `/libreoffice` met `#…&ingebed=1`: zonder kopbalk, over de volle breedte.
- De brug staat in `pythonpath/oa_brug.py`; extensie 0.6.0.

## 0.5.0 — 2026-11-08

- **Zijpaneel in LibreOffice Writer**: een eigen tabblad *Assistent* in de zijbalk, met de eigen schermelementen van LibreOffice. Metadata met voorstellen, registreren, versies, toegankelijkheid (beoordelen, tonen, herstellen), geschiedenis. Metadata klapt in na het registreren; aanvullende velden achter *Meer velden*.
- `oa_kern.py`: de regels van `oa-kern` en `semantisch.ts` in Python, met een kruistest tegen TypeScript.
- Aanmelden voor het zijpaneel via de browser (`/libreoffice#aanmelden=…`), met de sessiesleutel van `/api/auth/koppel` naar `127.0.0.1`.
- Menu: *Assistent tonen*; het paneel in de browser blijft als *Assistent in de browser openen*. Extensie 0.5.0, vanaf LibreOffice 7.2.

## 0.4.0 — 2026-11-08

Het origineel: Word levert het .docx (getFileAsync), LibreOffice het .odt (via de brug, `GET /bestand`), Collabora het werkbestand. Allemaal met vermogen `bestand-opleveren`.

## 0.3.0 — 2026-11-08

- Drie echte werkomgevingen: Microsoft Word (invoegtoepassing, ook Word voor het web), Collabora Online (WOPI, postMessage) en LibreOffice Writer op de eigen computer (extensie met lokale brug).
- `semantisch.ts` en `StructuurAdapter`: Word en LibreOffice leveren hun structuur als blokken; herstellingen gaan terug als opdracht (kopniveau, kopregel, alternatieve tekst, linktekst), zodat de opmaak blijft staan.
- Pagina's voor alle werkomgevingen worden samen gebouwd naar `dist/web`.

## 0.1.0 — 2026-11-07

Fase 1 van het werkende prototype: contract, minimaal platform, integratielaag met twee ingangen, assistentkern, paneel en een demo-werkomgeving met de modules metadateren en toegankelijkheid.
