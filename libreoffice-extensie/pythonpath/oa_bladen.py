# -*- coding: utf-8 -*-
"""Rekenbladen (Calc) en presentaties (Impress) voor de Office Assistent.

Leest het document als semantische html, zoals de assistent-services die
verwachten (oa-services, toegankelijkheid.ts):

- rekenblad: per blad <section data-oa="blad"> met de naam als <h2>, het
  gebruikte bereik als <table> en afbeeldingen en grafieken als <img>;
- presentatie: per dia <section data-oa="dia"> met de titel als <h2> (geen
  titel = geen <h2>), tekst als <p> of <ul>, afbeeldingen als <img>.

En voert een herstelling uit op een plek ("body/2/0"): een blad hernoemen,
de titel van een dia zetten, alternatieve tekst bij een afbeelding. De plek
wordt bij het uitvoeren opnieuw opgezocht; is het document intussen
veranderd, dan stopt de opdracht.

Werkt alleen met UNO; de vertaling van de html staat in oa_kern.
"""

import re

from oa_kern import NietUitvoerbaar, eerste_element, pad_delen

MAX_RIJEN = 200
MAX_KOLOMMEN = 30
ONGELDIG_IN_BLADNAAM = re.compile(r"[\[\]*?:/\\]")


class Gewijzigd(Exception):
    """Het document is veranderd sinds het werd gelezen."""


def soort_van(document):
    if document.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
        return "rekenblad"
    if document.supportsService("com.sun.star.presentation.PresentationDocument"):
        return "presentatie"
    if document.supportsService("com.sun.star.text.TextDocument"):
        return "tekst"
    return "onbekend"


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s):
    return _esc(s).replace('"', "&quot;")


def _alt(vorm):
    return getattr(vorm, "Title", "") or getattr(vorm, "Description", "") or ""


def _img(vorm, grafiek=False):
    extra = ' data-oa="grafiek"' if grafiek else ""
    alt = _alt(vorm)
    # Geen alt-attribuut = niet beschreven; dat is wat de regel zoekt.
    return '<img%s alt="%s">' % (extra, _esc_attr(alt)) if alt else "<img%s>" % extra


def _is_beeld(vorm):
    t = vorm.getShapeType()
    return t in ("com.sun.star.drawing.GraphicObjectShape", "com.sun.star.presentation.GraphicObjectShape") or t.endswith("OLE2Shape") or t.endswith("ChartShape")


def _is_grafiek(vorm):
    """Een OLE-object met het klasse-id van een LibreOffice-grafiek."""
    try:
        return vorm.CLSID.upper().startswith("12DCAE26")
    except Exception:
        return vorm.getShapeType().endswith("ChartShape")


def _vormen(pagina):
    return [pagina.getByIndex(i) for i in range(pagina.getCount())]


# ---------------------------------------------------------------------------
# Lezen
# ---------------------------------------------------------------------------


def _blad_html(blad):
    """Een blad als sectie; geeft (html, onderdelen) met per element wat het is."""
    delen = ['<h2>%s</h2>' % _esc(blad.getName())]
    onderdelen = [("naam", None)]
    cursor = blad.createCursor()
    cursor.gotoEndOfUsedArea(False)
    eind = cursor.getRangeAddress()
    rijen = min(eind.EndRow + 1, MAX_RIJEN)
    kolommen = min(eind.EndColumn + 1, MAX_KOLOMMEN)
    if rijen and kolommen and not (rijen == 1 and kolommen == 1 and not blad.getCellByPosition(0, 0).getString()):
        data = blad.getCellRangeByPosition(0, 0, kolommen - 1, rijen - 1).getDataArray()
        regels = []
        for rij in data:
            regels.append("<tr>%s</tr>" % "".join("<td>%s</td>" % _esc(_celtekst(w)) for w in rij))
        delen.append("<table><tbody>%s</tbody></table>" % "".join(regels))
        onderdelen.append(("tabel", None))
    for i, vorm in enumerate(_vormen(blad.getDrawPage())):
        if _is_beeld(vorm):
            delen.append(_img(vorm, _is_grafiek(vorm)))
            onderdelen.append(("beeld", i))
    return '<section data-oa="blad">%s</section>' % "".join(delen), onderdelen


def _celtekst(w):
    if isinstance(w, float):
        return ("%d" % w) if w == int(w) else ("%s" % w)
    return str(w)


def _titelvorm(dia):
    for i, vorm in enumerate(_vormen(dia)):
        if vorm.getShapeType() == "com.sun.star.presentation.TitleTextShape":
            return i, vorm
    return None, None


def _dia_html(dia):
    delen, onderdelen = [], []
    ti, titel = _titelvorm(dia)
    if titel is not None and titel.getString().strip():
        delen.append("<h2>%s</h2>" % _esc(re.sub(r"\s+", " ", titel.getString()).strip()))
        onderdelen.append(("titel", ti))
    for i, vorm in enumerate(_vormen(dia)):
        if i == ti:
            continue
        t = vorm.getShapeType()
        if _is_beeld(vorm):
            delen.append(_img(vorm, _is_grafiek(vorm)))
            onderdelen.append(("beeld", i))
        elif t.startswith("com.sun.star.presentation.") and t.endswith(("OutlinerShape",)):
            regels = [r.strip() for r in vorm.getString().split("\n") if r.strip()]
            if regels:
                delen.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _esc(r) for r in regels))
                onderdelen.append(("tekst", i))
        elif hasattr(vorm, "getString") and t not in ("com.sun.star.presentation.NotesShape", "com.sun.star.presentation.PageShape"):
            try:
                tekst = vorm.getString().strip()
            except Exception:
                tekst = ""
            if tekst:
                delen.append("<p>%s</p>" % _esc(re.sub(r"\s+", " ", tekst)))
                onderdelen.append(("tekst", i))
    return '<section data-oa="dia">%s</section>' % "".join(delen), onderdelen


def _paginas(document, soort):
    if soort == "rekenblad":
        bladen = document.getSheets()
        return [bladen.getByIndex(i) for i in range(bladen.getCount())]
    paginas = document.getDrawPages()
    return [paginas.getByIndex(i) for i in range(paginas.getCount())]


def lees(document):
    """De html van het hele document, met een kaart van wat waar staat."""
    soort = soort_van(document)
    secties, kaart = [], []
    for p in _paginas(document, soort):
        html, onderdelen = _blad_html(p) if soort == "rekenblad" else _dia_html(p)
        secties.append(html)
        kaart.append(onderdelen)
    return "\n".join(secties), kaart


def html(document):
    return lees(document)[0]


# ---------------------------------------------------------------------------
# Herstellen en tonen
# ---------------------------------------------------------------------------


def _zoek(document, pad):
    """(soort, pagina, onderdeel, vorm-index) voor een plek, volgens de kaart van nu."""
    delen = pad_delen(pad)
    soort = soort_van(document)
    _html, kaart = lees(document)
    if not delen or delen[0] >= len(kaart):
        raise Gewijzigd("Dit deel van het document is niet meer gevonden. Beoordeel opnieuw.")
    pagina = _paginas(document, soort)[delen[0]]
    if len(delen) == 1:
        return soort, pagina, ("pagina", None)
    if delen[1] >= len(kaart[delen[0]]):
        raise Gewijzigd("Dit deel van het document is niet meer gevonden. Beoordeel opnieuw.")
    return soort, pagina, kaart[delen[0]][delen[1]]


def vervang_segment(document, pad, nieuw):
    """Voert de herstelling uit die het nieuwe element op deze plek beschrijft."""
    soort, pagina, (wat, index) = _zoek(document, pad)
    el = eerste_element(nieuw)
    if el.tag is None:
        raise NietUitvoerbaar("De wijziging is leeg.")
    if wat == "beeld" and el.tag == "img":
        vorm = pagina.getDrawPage().getByIndex(index) if soort == "rekenblad" else pagina.getByIndex(index)
        alt = el.attrs.get("alt") or ""
        vorm.Title = alt
        vorm.Description = alt
        return
    if soort == "rekenblad" and wat == "naam" and el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        naam = el.tekst.strip()
        if not naam or len(naam) > 31 or ONGELDIG_IN_BLADNAAM.search(naam):
            raise NietUitvoerbaar("Een bladnaam is 1 tot 31 tekens, zonder [ ] * ? : / of \\.")
        if document.getSheets().hasByName(naam) and naam != pagina.getName():
            raise NietUitvoerbaar("Er is al een blad met de naam %s." % naam)
        pagina.setName(naam)
        return
    if soort == "presentatie" and wat == "titel" and el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        pagina.getByIndex(index).setString(el.tekst.strip())
        return
    if soort == "presentatie" and wat == "pagina" and el.tag == "section" and el.attrs.get("titel"):
        _zet_titel(document, pagina, el.attrs["titel"].strip())
        return
    raise NietUitvoerbaar("Deze wijziging kan in deze werkomgeving nog niet automatisch. Pas het met de hand aan.")


def _zet_titel(document, dia, titel):
    if not titel:
        raise NietUitvoerbaar("Vul eerst een titel in.")
    _i, vorm = _titelvorm(dia)
    if vorm is None:
        # Geen titelvak in deze opmaak: een titelvak toevoegen, bovenaan de dia.
        from com.sun.star.awt import Point, Size
        vorm = document.createInstance("com.sun.star.presentation.TitleTextShape")
        dia.add(vorm)
        breedte = dia.Width - dia.BorderLeft - dia.BorderRight
        vorm.setPosition(Point(dia.BorderLeft, dia.BorderTop))
        vorm.setSize(Size(breedte, 2500))
    vorm.setString(titel)


def toon(document, pad):
    """Brengt de plek in beeld en selecteert wat er staat."""
    soort, pagina, (wat, index) = _zoek(document, pad)
    controller = document.getCurrentController()
    if soort == "rekenblad":
        controller.setActiveSheet(pagina)
        if wat == "beeld":
            controller.select(pagina.getDrawPage().getByIndex(index))
        elif wat == "tabel":
            controller.select(pagina.getCellRangeByPosition(0, 0, 0, 0))
        return
    controller.setCurrentPage(pagina)
    if index is not None:
        try:
            controller.select(pagina.getByIndex(index))
        except Exception:
            pass
