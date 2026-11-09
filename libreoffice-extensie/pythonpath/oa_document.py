# -*- coding: utf-8 -*-
"""Het document in LibreOffice Writer lezen en wijzigen, voor de Office Assistent.

Leest de structuur als "blokken" (zelfde vorm als de Word-adapter, zie
oa-adapters/src/semantisch.ts) en voert opdrachten uit: kopniveau,
kopregel van een tabel, alternatieve tekst, linktekst. Zo blijft de opmaak
van het document staan; de assistent zelf ziet alleen html.

Alleen alinea's en tabellen op het hoogste niveau tellen mee, in de
volgorde van het document. Een opdracht controleert eerst of de tekst van
de alinea nog dezelfde is; is het document intussen gewijzigd, dan stopt hij.
"""

import re
import tempfile
import os

import uno
from com.sun.star.beans import PropertyValue

GENUMMERD = re.compile(r"^(\d+|[a-zA-Z]{1,3}|[ivxlcIVXLC]+)[.)]$|^\d+$")
KOP = re.compile(r"^(?:heading|kop)(\d)$")


class Gewijzigd(Exception):
    """Het document is veranderd sinds het werd gelezen."""


def niveau_uit_stijl(stijl, overzichtsniveau=0):
    s = re.sub(r"\s+", "", (stijl or "")).lower()
    m = KOP.match(s)
    if m:
        return min(int(m.group(1)), 6)
    if s in ("title", "titel"):
        return 1
    if overzichtsniveau and 1 <= overzichtsniveau <= 6:
        return overzichtsniveau
    return 0


def _schoon(tekst):
    return re.sub(r"[\r\n\u000b]", " ", tekst or "").strip()


def _onderdelen(document):
    """Alinea's en tabellen op het hoogste niveau, met hun eigen volgnummer."""
    alinea, tabel = 0, 0
    opsomming = document.getText().createEnumeration()
    while opsomming.hasMoreElements():
        el = opsomming.nextElement()
        if el.supportsService("com.sun.star.text.Paragraph"):
            yield "alinea", alinea, el
            alinea += 1
        elif el.supportsService("com.sun.star.text.TextTable"):
            yield "tabel", tabel, el
            tabel += 1


def _stukken(alinea):
    opsomming = alinea.createEnumeration()
    while opsomming.hasMoreElements():
        yield opsomming.nextElement()


def _afbeeldingen(alinea):
    """Afbeeldingen in of aan deze alinea, in vaste volgorde."""
    gevonden = []
    gezien = set()

    def voeg_toe(inhoud):
        while inhoud.hasMoreElements():
            x = inhoud.nextElement()
            if x.supportsService("com.sun.star.text.TextGraphicObject") and x.Name not in gezien:
                gezien.add(x.Name)
                gevonden.append(x)

    for stuk in _stukken(alinea):
        if stuk.TextPortionType == "Frame":
            voeg_toe(stuk.createContentEnumeration("com.sun.star.text.TextContent"))
    voeg_toe(alinea.createContentEnumeration("com.sun.star.text.TextContent"))
    return gevonden


def _links(alinea):
    """Links als (tekst, adres, [stukken]); aaneengesloten stukken met hetzelfde adres zijn één link."""
    links = []
    for stuk in _stukken(alinea):
        if stuk.TextPortionType != "Text":
            continue
        url = stuk.HyperLinkURL
        if url:
            if links and links[-1][1] == url and links[-1][3]:
                links[-1][0] += stuk.getString()
                links[-1][2].append(stuk)
            else:
                links.append([stuk.getString(), url, [stuk], True])
        elif links:
            links[-1][3] = False
    return [(t, u, s) for t, u, s, _ in links]


def _heel(alinea, eigenschap, test):
    """Geldt `test` voor alle tekststukken van de alinea?"""
    stukken = [s for s in _stukken(alinea) if s.TextPortionType == "Text" and s.getString().strip()]
    return bool(stukken) and all(test(s.getPropertyValue(eigenschap)) for s in stukken)


def _alt(beeld):
    return beeld.Title or beeld.Description or ""


def lees_blokken(document):
    """De structuur van het document, als lijst van alinea's en tabellen (nog niet gegroepeerd)."""
    reeks = []
    for soort, index, el in _onderdelen(document):
        if soort == "tabel":
            rijen = []
            for r in range(el.getRows().getCount()):
                rij = []
                for k in range(el.getColumns().getCount()):
                    rij.append(el.getCellByPosition(k, r).getString())
                rijen.append(rij)
            # De kopregel van Writer: "Kop herhalen" met het aantal rijen. Dat
            # gaat als kopregel mee naar docx en getagde pdf; de alineastijl
            # "Table Heading" alleen niet.
            kop = el.HeaderRowCount if el.RepeatHeadline else 0
            reeks.append({"soort": "tabel", "bron": index, "rijen": rijen, "kopregels": kop})
            continue

        tekst = _schoon(el.getString())
        links = _links(el)
        beelden = _afbeeldingen(el)
        inline = [{"soort": "link", "tekst": t, "href": u, "index": i} for i, (t, u, _) in enumerate(links)]
        inline += [{"soort": "afbeelding", "alt": _alt(b), "index": i} for i, b in enumerate(beelden)]
        if not tekst and not inline:
            continue
        niveau = niveau_uit_stijl(el.ParaStyleName, el.OutlineLevel)
        lijst = None
        if niveau == 0 and el.NumberingIsNumber:
            label = (el.ListLabelString or "").strip()
            lijst = {"genummerd": bool(GENUMMERD.match(label))}
        reeks.append({
            "bron": index,
            "niveau": niveau,
            "tekst": tekst,
            "vet": _heel(el, "CharWeight", lambda w: w >= 150),
            "onderstreept": _heel(el, "CharUnderline", lambda u: u != 0),
            "inline": inline,
            "lijst": lijst,
        })
    return reeks


def _zoek(document, soort, index):
    for s, i, el in _onderdelen(document):
        if s == soort and i == index:
            return el
    raise Gewijzigd("Dit deel van het document is niet meer gevonden. Beoordeel opnieuw.")


def _alinea(document, index, verwacht):
    el = _zoek(document, "alinea", index)
    if _schoon(el.getString()) != verwacht:
        raise Gewijzigd("Het document is intussen gewijzigd. Beoordeel opnieuw.")
    return el


def voer_uit(document, o):
    soort = o["soort"]
    if soort == "niveau":
        el = _alinea(document, o["alinea"], o["tekst"])
        el.ParaStyleName = "Heading %d" % o["niveau"] if o["niveau"] else "Standard"
    elif soort == "tabelkop":
        t = _zoek(document, "tabel", o["tabel"])
        t.RepeatHeadline = True
        t.HeaderRowCount = 1
        for naam in t.getCellNames():
            if re.match(r"^[A-Z]+1$", naam):
                cel = t.getCellByName(naam).getText().createEnumeration()
                while cel.hasMoreElements():
                    cel.nextElement().ParaStyleName = "Table Heading"
    elif soort == "alt":
        beelden = _afbeeldingen(_alinea(document, o["alinea"], o["tekst"]))
        if o["afbeelding"] >= len(beelden):
            raise Gewijzigd("De afbeelding is niet meer gevonden. Beoordeel opnieuw.")
        b = beelden[o["afbeelding"]]
        b.Title = o["alt"]
        b.Description = o["alt"]
    elif soort == "linktekst":
        el = _alinea(document, o["alinea"], o["alineatekst"])
        links = _links(el)
        if o["link"] >= len(links):
            raise Gewijzigd("De link is niet meer gevonden. Beoordeel opnieuw.")
        _, adres, stukken = links[o["link"]]
        tekst = document.getText()
        cursor = tekst.createTextCursorByRange(stukken[0].getStart())
        cursor.gotoRange(stukken[-1].getEnd(), True)
        cursor.setString(o["tekst"])
        cursor.HyperLinkURL = adres or o.get("href", "")
    else:
        raise ValueError("Onbekende opdracht: %s" % soort)


def toon(document, doel):
    controller = document.getCurrentController()
    vc = controller.getViewCursor()
    soort = doel["soort"]
    if soort == "tabel":
        t = _zoek(document, "tabel", doel["tabel"])
        namen = t.getCellNames()
        vc.gotoRange(t.getCellByName(namen[0]).getStart(), False)
        vc.gotoRange(t.getCellByName(namen[-1]).getEnd(), True)
        return
    el = _zoek(document, "alinea", doel["alinea"])
    if soort == "afbeelding":
        beelden = _afbeeldingen(el)
        if doel["afbeelding"] < len(beelden):
            controller.select(beelden[doel["afbeelding"]])
            return
    if soort == "link":
        links = _links(el)
        if doel["link"] < len(links):
            stukken = links[doel["link"]][2]
            vc.gotoRange(stukken[0].getStart(), False)
            vc.gotoRange(stukken[-1].getEnd(), True)
            return
    vc.gotoRange(el.getStart(), False)
    vc.gotoRange(el.getEnd(), True)


def vervang_alles(document, html):
    """Terugval: het hele document vervangen door html. Kost opmaak en afbeeldingen."""
    for i in reversed(range(document.getTextTables().getCount())):
        document.getTextTables().getByIndex(i).dispose()
    tekst = document.getText()
    tekst.setString("")
    fd, pad = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><meta charset="utf-8"></head><body>%s</body></html>' % html)
        cursor = tekst.createTextCursor()
        filter_ = PropertyValue()
        filter_.Name = "FilterName"
        filter_.Value = "HTML (StarWriter)"
        cursor.insertDocumentFromURL(uno.systemPathToFileUrl(pad), (filter_,))
    finally:
        os.unlink(pad)


ODF = {
    "tekst": ("writer8", "odt", "application/vnd.oasis.opendocument.text"),
    "rekenblad": ("calc8", "ods", "application/vnd.oasis.opendocument.spreadsheet"),
    "presentatie": ("impress8", "odp", "application/vnd.oasis.opendocument.presentation"),
}


# Voor de toegankelijkheidscontrole van het bestand (oa-wcag leest alleen OOXML).
OOXML = {
    "tekst": ("MS Word 2007 XML", "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "rekenblad": ("Calc MS Excel 2007 XML", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "presentatie": ("Impress MS PowerPoint 2007 XML", "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}


def bestand(document, ooxml=False):
    """Het document als OpenDocument (.odt, .ods of .odp), of met ooxml=True als .docx, .xlsx of .pptx.
    De opslagplek van het document verandert niet (storeToURL maakt een kopie)."""
    import base64
    from oa_bladen import soort_van
    soorten = OOXML if ooxml else ODF
    filter_naam, ext, media = soorten.get(soort_van(document), soorten["tekst"])
    fd, pad = tempfile.mkstemp(suffix="." + ext)
    os.close(fd)
    try:
        filter_ = PropertyValue()
        filter_.Name = "FilterName"
        filter_.Value = filter_naam
        document.storeToURL(uno.systemPathToFileUrl(pad), (filter_,))
        with open(pad, "rb") as f:
            data = f.read()
    finally:
        os.unlink(pad)
    return {
        "formaat": ext,
        "mediaType": media,
        "codering": "base64",
        "data": base64.b64encode(data).decode("ascii"),
    }


def lees_eigenschap(document, naam):
    eigen = document.getDocumentProperties().getUserDefinedProperties()
    if eigen.getPropertySetInfo().hasPropertyByName(naam):
        return str(eigen.getPropertyValue(naam))
    return None


def schrijf_eigenschap(document, naam, waarde):
    eigen = document.getDocumentProperties().getUserDefinedProperties()
    if eigen.getPropertySetInfo().hasPropertyByName(naam):
        eigen.setPropertyValue(naam, waarde)
    else:
        eigen.addProperty(naam, 128, waarde)  # 128 = REMOVABLE


def naam_van(document):
    titel = document.getDocumentProperties().Title
    if titel:
        return titel
    url = document.getURL()
    return uno.fileUrlToSystemPath(url).rsplit(os.sep, 1)[-1] if url else "Naamloos document"
