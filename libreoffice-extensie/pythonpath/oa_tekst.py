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


def _vervang_in_opmerkingen(document, paren):
    """Zoeken en vervangen van LibreOffice slaat opmerkingen over; die apart."""
    aantal = 0
    try:
        velden = document.getTextFields().createEnumeration()
    except Exception:
        return 0
    while velden.hasMoreElements():
        v = velden.nextElement()
        if not v.supportsService("com.sun.star.text.textfield.Annotation"):
            continue
        tekst = v.Content or ""
        nieuw = tekst
        for van, naar in paren:
            nieuw, n = re.subn(r"(?<!\w)" + re.escape(van) + r"(?!\w)", lambda _m, naar=naar: naar, nieuw)
            aantal += n
        if nieuw != tekst:
            v.Content = nieuw
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
        return _vervang_met_zoeken([document], paren) + _vervang_in_opmerkingen(document, paren)
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


def lees_selectie(document, klembord=True, ctx=None):
    """De geselecteerde tekst; in Calc de geselecteerde cellen met tekst.

    Werkt de medewerker in een opmerking (Writer), dan geeft LibreOffice geen
    selectie door (None). Dan kopieert de assistent de selectie even via het
    klembord, en zet daarna terug wat er op het klembord stond."""
    sel = document.getCurrentController().getSelection()
    tekst = _tekst_van(sel)
    if sel is None and klembord and soort_van(document) == "tekst":
        tekst = _selectie_via_klembord(document, ctx)
    return re.sub(r"\s+", " ", tekst).strip()[:500]


_KLEMBORD_TEKST = "text/plain;charset=utf-16"


def _klembord_tekst(inhoud):
    if inhoud is None:
        return None
    try:
        for f in inhoud.getTransferDataFlavors():
            if f.MimeType.startswith(_KLEMBORD_TEKST):
                return inhoud.getTransferData(f)
    except Exception:
        return None
    return None


def _selectie_via_klembord(document, ctx=None):
    """Kopieert de selectie (ook in een opmerking) en geeft de tekst; het klembord blijft zoals het was."""
    import uno
    import unohelper
    from com.sun.star.datatransfer import XTransferable, DataFlavor

    class Markering(unohelper.Base, XTransferable):
        """Iets wat niemand kopieert: staat het er na Kopiëren nog, dan was er niets geselecteerd."""
        WAARDE = "\u2063oa-geen-selectie\u2063"

        def getTransferData(self, _f):
            return self.WAARDE

        def getTransferDataFlavors(self):
            f = DataFlavor()
            f.MimeType, f.HumanPresentableName = _KLEMBORD_TEKST, "Tekst"
            f.DataType = uno.getTypeByName("string")
            return (f,)

        def isDataFlavorSupported(self, f):
            return f.MimeType.startswith(_KLEMBORD_TEKST)

    ctx = ctx or uno.getComponentContext()
    smgr = ctx.ServiceManager
    try:
        kb = smgr.createInstanceWithContext("com.sun.star.datatransfer.clipboard.SystemClipboard", ctx)
        oud = kb.getContents()
        kb.setContents(Markering(), None)
        try:
            helper = smgr.createInstanceWithContext("com.sun.star.frame.DispatchHelper", ctx)
            helper.executeDispatch(document.getCurrentController().getFrame(), ".uno:Copy", "", 0, ())
            tekst = _klembord_tekst(kb.getContents()) or ""
        finally:
            try:
                kb.setContents(oud, None) if oud is not None else None
            except Exception:
                pass
        return "" if Markering.WAARDE in tekst else tekst
    except Exception:
        return ""
