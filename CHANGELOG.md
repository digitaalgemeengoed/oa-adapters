# Wijzigingen

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
