# -*- coding: utf-8 -*-
"""Tekst vervangen en de selectie lezen, voor Writer, Calc en Impress.

Gebruikt bij anonimiseren: na bevestiging vervangt de assistent elk
persoonsgegeven in het document zelf door zijn plaatshouder ([PERSOON 1]).
Alleen hele woorden ("Jan" niet in "Janssen"), hoofdlettergevoelig, de
langste waarde eerst. De opmaak rond de vervangen tekst blijft staan.

Writer en Calc: zoeken en vervangen van LibreOffice zelf (ICU-reguliere
expressie), dus ook in tabellen, kop- en voetteksten en alle bladen.
Impress: per tekstvak met een tekstcursor, van achter naar voren.
"""
import re

from oa_bladen import soort_van
from oa_kern import NietUitvoerbaar

# Geen letter, cijfer of _ ervoor of erna; zelfde grens als tekstvervangen.ts.
_VOOR = r"(?<![\p{L}\p{N}_])"
_NA = r"(?![\p{L}\p{N}_])"


def orden(paren):
    gezien = set()
    uit = []
    for p in paren:
        van, naar = p.get("van", ""), p.get("naar", "")
        if not van.strip() or van == naar or van in gezien:
            continue
        gezien.add(van)
        uit.append((van, naar))
    return sorted(uit, key=lambda vn: -len(vn[0]))


def icu_patroon(van):
    """ICU: \\Q…\\E neemt de waarde letterlijk; een \\E in de waarde zelf apart."""
    return _VOOR + "\\Q" + van.replace("\\E", "\\E\\\\E\\Q") + "\\E" + _NA


def icu_vervanging(naar):
    """In de vervangtekst van LibreOffice zijn & en $ stuurtekens; een backslash
    is niet betrouwbaar te ontsnappen (\\n wordt een alinea). Plaatshouders
    hebben er nooit een."""
    if "\\" in naar:
        raise NietUitvoerbaar("Een vervangtekst met een backslash kan LibreOffice niet letterlijk invoegen.")
    return naar.replace("&", "\\&").replace("$", "\\$")


def _vervang_met_zoeken(doelen, paren):
    aantal = 0
    for van, naar in paren:
        for doel in doelen:
            d = doel.createReplaceDescriptor()
            d.SearchString = icu_patroon(van)
            d.ReplaceString = icu_vervanging(naar)
            d.SearchRegularExpression = True
            d.SearchCaseSensitive = True
            aantal += doel.replaceAll(d)
    return aantal


def _tekstvakken(vormen):
    for i in range(vormen.getCount()):
        v = vormen.getByIndex(i)
        if v.supportsService("com.sun.star.drawing.GroupShape"):
            yield from _tekstvakken(v)
        elif hasattr(v, "createTextCursor") and v.supportsService("com.sun.star.drawing.Text"):
            yield v


def _vervang_in_vak(vak, paren):
    tekst = vak.getString()
    bezet = []
    for van, naar in paren:
        for m in re.finditer(r"(?<!\w)" + re.escape(van) + r"(?!\w)", tekst):
            b, e = m.span()
            if not any(b < x[1] and e > x[0] for x in bezet):
                bezet.append((b, e, naar))
    for b, e, naar in sorted(bezet, key=lambda x: -x[0]):
        c = vak.createTextCursor()
        c.gotoStart(False)
        c.goRight(b, False)
        c.goRight(e - b, True)
        c.setString(naar)
    return len(bezet)


def vervang_tekst(document, paren):
    """Vervangt elk paar {van, naar} als heel woord; geeft het aantal vervangingen."""
    paren = orden(paren)
    if not paren:
        return 0
    soort = soort_van(document)
    if soort == "tekst":
        return _vervang_met_zoeken([document], paren)
    if soort == "rekenblad":
        bladen = document.getSheets()
        return _vervang_met_zoeken([bladen.getByIndex(i) for i in range(bladen.getCount())], paren)
    aantal = 0
    paginas = document.getDrawPages()
    for i in range(paginas.getCount()):
        for vak in _tekstvakken(paginas.getByIndex(i)):
            aantal += _vervang_in_vak(vak, paren)
    return aantal


def _tekst_van(sel):
    if sel is None:
        return ""
    if hasattr(sel, "getDataArray"):  # cellen in Calc
        return " ".join(str(c) for rij in sel.getDataArray() for c in rij if isinstance(c, str) and c.strip())
    if hasattr(sel, "getCount") and hasattr(sel, "getByIndex"):  # tekstbereiken, vormen
        return " ".join(_tekst_van(sel.getByIndex(i)) for i in range(sel.getCount())).strip()
    if hasattr(sel, "getString"):
        return sel.getString()
    return ""


def lees_selectie(document):
    """De geselecteerde tekst; in Calc de geselecteerde cellen met tekst."""
    tekst = _tekst_van(document.getCurrentController().getSelection())
    return re.sub(r"\s+", " ", tekst).strip()[:500]
