# Wijzigingen

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
