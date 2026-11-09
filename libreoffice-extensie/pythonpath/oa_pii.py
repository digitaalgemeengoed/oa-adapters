# -*- coding: utf-8 -*-
"""Anonimiseren in het document, voor Writer (zoals de MIRA-demo).

Elke plaatshouder ([PERSOON 1]) staat in de tekst met een bladwijzer
eromheen. De naam van de bladwijzer draagt de plek, de plaatshouder en of
het nog een voorvertoning is:

    oa-pii p12 [PERSOON 1] v      (voorvertoning)
    oa-pii p12 [PERSOON 1]        (bevestigd)

De tekst krijgt de kleur van het niveau (art. 6 groen, art. 9 oranje,
art. 10 rood); een voorvertoning heeft een gestippelde rand. Terugzetten:
de bladwijzer weg, de tekst terug, de opmaak terug naar die van de alinea.

Klikt de medewerker in een plaatshouder, dan onthoudt de selectieluisteraar
welke; het paneel vraagt dat regelmatig op (/pii-klik). Het rechtermuismenu
krijgt "Anonimiseer selectie (Assistent)".
"""
import functools
import re

import uno
import unohelper
from com.sun.star.ui import XContextMenuInterceptor
from com.sun.star.ui.ContextMenuInterceptorAction import EXECUTE_MODIFIED, IGNORED
from com.sun.star.view import XSelectionChangeListener

from oa_tekst import icu_patroon

VOORVOEGSEL = "oa-pii "
NAAM = re.compile(r"^oa-pii (p\d+) (\[[^\]]+\])( v)?$")
ACHTERGROND = {1: 0xE3F1E6, 2: 0xFDF0D8, 3: 0xFBE3E3}
KLEUR = {1: 0x1E6B33, 2: 0x8A5300, 3: 0xA4001D}
OPMAAK = ("CharBackColor", "CharColor", "CharLeftBorder", "CharRightBorder", "CharTopBorder", "CharBottomBorder")
OPDRACHT = "service:nl.digitaalgemeengoed.oa.Assistent?module:anon-selectie"


def _lijn(kleur, gestippeld):
    l = uno.createUnoStruct("com.sun.star.table.BorderLine2")
    if gestippeld:
        l.Color = kleur
        l.LineWidth = 18
        l.LineStyle = 2  # DASHED
        l.OuterLineWidth = 18
    return l


def _kleur(rng, ppl, voorvertoning):
    rng.CharBackColor = ACHTERGROND.get(ppl, ACHTERGROND[1])
    rng.CharColor = KLEUR.get(ppl, KLEUR[1])
    for kant in ("CharLeftBorder", "CharRightBorder", "CharTopBorder", "CharBottomBorder"):
        setattr(rng, kant, _lijn(KLEUR.get(ppl, KLEUR[1]), voorvertoning))


def _wis_opmaak(rng):
    try:
        rng.setPropertiesToDefault(OPMAAK)
    except Exception:
        for naam in OPMAAK:
            try:
                rng.setPropertyToDefault(naam)
            except Exception:
                pass


def _bladwijzers(document):
    bw = document.getBookmarks()
    uit = []
    for naam in bw.getElementNames():
        m = NAAM.match(naam)
        if m:
            uit.append((m, bw.getByName(naam)))
    return uit


def _plek_nummer(m):
    return int(m.group(1)[1:])


def _volgorde(a, b):
    """Volgorde in het document; tussen verschillende teksten (tabel, kop) op nummer."""
    ra, rb = a[1].getAnchor(), b[1].getAnchor()
    try:
        if ra.getText() == rb.getText():
            c = ra.getText().compareRegionStarts(ra, rb)
            if c:
                return -c
    except Exception:
        pass
    return _plek_nummer(a[0]) - _plek_nummer(b[0])


def lees_plekken(document):
    gesorteerd = sorted(_bladwijzers(document), key=functools.cmp_to_key(_volgorde))
    return [{"plek": m.group(1), "plaatshouder": m.group(2), "voorvertoning": bool(m.group(3))} for m, _ in gesorteerd]


def markeer(document, markeringen):
    """Vervangt elke waarde (als heel woord, de langste eerst) door een gemarkeerde plaatshouder."""
    volg = max([_plek_nummer(m) for m, _ in _bladwijzers(document)] or [0])
    nieuw = []
    gezien = set()
    for mk in sorted(markeringen, key=lambda x: -len(x.get("van", ""))):
        van = mk.get("van", "")
        if not van.strip() or van in gezien:
            continue
        gezien.add(van)
        d = document.createSearchDescriptor()
        d.SearchString = icu_patroon(van)
        d.SearchRegularExpression = True
        d.SearchCaseSensitive = True
        gevonden = document.findAll(d)
        for i in range(gevonden.getCount()):
            rng = gevonden.getByIndex(i)
            if _in_plaatshouder(document, rng):
                continue
            volg += 1
            plek = "p%d" % volg
            tekst = rng.getText()
            cursor = tekst.createTextCursorByRange(rng)
            cursor.setString(mk["plaatshouder"])
            _kleur(cursor, int(mk.get("ppl", 1)), bool(mk.get("voorvertoning")))
            bw = document.createInstance("com.sun.star.text.Bookmark")
            bw.setName("%s%s %s%s" % (VOORVOEGSEL, plek, mk["plaatshouder"], " v" if mk.get("voorvertoning") else ""))
            tekst.insertTextContent(cursor, bw, True)
            nieuw.append({"plek": plek, "plaatshouder": mk["plaatshouder"], "voorvertoning": bool(mk.get("voorvertoning"))})
    return nieuw


def _in_plaatshouder(document, rng):
    for _m, bw in _bladwijzers(document):
        a = bw.getAnchor()
        try:
            t = a.getText()
            if t == rng.getText() and t.compareRegionStarts(a, rng) >= 0 and t.compareRegionEnds(rng, a) >= 0:
                return True
        except Exception:
            continue
    return False


def _zoek(document, plek):
    for m, bw in _bladwijzers(document):
        if m.group(1) == plek:
            return m, bw
    return None, None


def herstel(document, plekken):
    for p in plekken:
        _m, bw = _zoek(document, p["plek"])
        if bw is None:
            continue
        a = bw.getAnchor()
        cursor = a.getText().createTextCursorByRange(a)
        cursor.setString(p["waarde"])
        _wis_opmaak(cursor)
        a.getText().removeTextContent(bw)


def zet_definitief(document):
    for m, bw in _bladwijzers(document):
        if not m.group(3):
            continue
        bw.setName("%s%s %s" % (VOORVOEGSEL, m.group(1), m.group(2)))
        a = bw.getAnchor()
        for kant in ("CharLeftBorder", "CharRightBorder", "CharTopBorder", "CharBottomBorder"):
            setattr(a, kant, _lijn(0, False))


def toon(document, plek):
    _m, bw = _zoek(document, plek)
    if bw is not None:
        document.getCurrentController().select(bw.getAnchor())


def plek_bij_cursor(document):
    """De plaatshouder waarin de cursor staat, of None."""
    vc = document.getCurrentController().getViewCursor()
    ingeklapt = vc.isCollapsed()
    for m, bw in _bladwijzers(document):
        a = bw.getAnchor()
        try:
            t = a.getText()
            if t != vc.getText():
                continue
            begin, eind = t.compareRegionStarts(a, vc), t.compareRegionEnds(vc, a)
            # Een cursor zonder selectie telt alleen echt binnenin: ernaast typen is geen klik.
            if (ingeklapt and begin > 0 and eind > 0) or (not ingeklapt and begin >= 0 and eind >= 0):
                return {"plek": m.group(1), "plaatshouder": m.group(2), "voorvertoning": bool(m.group(3))}
        except Exception:
            continue
    return None


class Klikken(unohelper.Base, XSelectionChangeListener, XContextMenuInterceptor):
    """Luistert naar de selectie (klik in een plaatshouder) en vult het rechtermuismenu aan."""

    def __init__(self, document):
        from oa_bladen import soort_van
        self.document = document
        self.tekst = soort_van(document) == "tekst"
        self.laatste = None
        self.teller = 0
        c = document.getCurrentController()
        c.addSelectionChangeListener(self)
        try:
            c.registerContextMenuInterceptor(self)
        except Exception:
            pass

    # XSelectionChangeListener
    def selectionChanged(self, _ev):
        try:
            p = plek_bij_cursor(self.document) if self.tekst else plek_bij_selectie(self.document)
        except Exception:
            p = None
        plek = p["plek"] if p else None
        if plek and plek != (self.laatste or {}).get("plek"):
            self.teller += 1
            self.laatste = p
        elif not plek:
            self.laatste = None

    def disposing(self, _ev):
        pass

    # XContextMenuInterceptor
    def notifyContextMenuExecute(self, ev):
        try:
            from oa_tekst import lees_selectie
            tekst = lees_selectie(self.document)
            if not tekst.strip():
                return IGNORED
            menu = ev.ActionTriggerContainer
            scheiding = menu.createInstance("com.sun.star.ui.ActionTriggerSeparator")
            item = menu.createInstance("com.sun.star.ui.ActionTrigger")
            item.setPropertyValue("Text", "Anonimiseer selectie (Assistent)")
            item.setPropertyValue("CommandURL", OPDRACHT)
            menu.insertByIndex(0, item)
            menu.insertByIndex(1, scheiding)
            return EXECUTE_MODIFIED
        except Exception:
            return IGNORED

    def stand(self):
        return {"n": self.teller, **(self.laatste or {})}


# ---------------------------------------------------------------------------
# Calc en Impress. Daar zijn geen bladwijzers: een plaatshouder is de tekst
# [SOORT n] zelf, in een cel of tekstvak. De plek is het vak plus het hoeveelste
# voorkomen erin (s0c2r5#0, d1s3#0). Of het nog een voorvertoning is, weet het
# register; in het document is dat een gestippelde onderstreping.
# ---------------------------------------------------------------------------

PLAATSHOUDER = re.compile(r"\[[A-Z][A-Z-]* \d+\]")
STIPPEL = 5  # com.sun.star.awt.FontUnderline.DASH


def _vakken(document):
    """(kenmerk, vak met tekst) voor elke cel met tekst of elk tekstvak."""
    from oa_bladen import soort_van
    if soort_van(document) == "rekenblad":
        from com.sun.star.sheet.CellFlags import STRING
        bladen = document.getSheets()
        for i in range(bladen.getCount()):
            reeksen = bladen.getByIndex(i).queryContentCells(STRING)
            cellen = reeksen.getCells().createEnumeration()
            gevonden = []
            while cellen.hasMoreElements():
                cel = cellen.nextElement()
                a = cel.getCellAddress()
                gevonden.append(((a.Row, a.Column), "s%dc%dr%d" % (a.Sheet, a.Column, a.Row), cel))
            for _k, kenmerk, cel in sorted(gevonden, key=lambda x: x[0]):
                yield kenmerk, cel
    else:
        from oa_tekst import _tekstvakken
        paginas = document.getDrawPages()
        for i in range(paginas.getCount()):
            for j, vak in enumerate(_tekstvakken(paginas.getByIndex(i))):
                yield "d%ds%d" % (i, j), vak


def _vak(document, kenmerk):
    for k, v in _vakken(document):
        if k == kenmerk:
            return v
    return None


def _cursor(vak, begin, lengte):
    c = vak.createTextCursor()
    c.gotoStart(False)
    c.goRight(begin, False)
    c.goRight(lengte, True)
    return c


def lees_plekken_bladen(document):
    uit = []
    for kenmerk, vak in _vakken(document):
        for i, m in enumerate(PLAATSHOUDER.finditer(vak.getString())):
            uit.append({"plek": "%s#%d" % (kenmerk, i), "plaatshouder": m.group(0), "voorvertoning": False})
    return uit


def markeer_bladen(document, markeringen):
    voor = {p["plek"] for p in lees_plekken_bladen(document)}
    geordend = sorted([m for m in markeringen if m.get("van", "").strip()], key=lambda x: -len(x["van"]))
    for _kenmerk, vak in _vakken(document):
        tekst = vak.getString()
        bezet = [m.span() for m in PLAATSHOUDER.finditer(tekst)]
        nieuw = []
        for mk in geordend:
            for m in re.finditer(r"(?<!\w)" + re.escape(mk["van"]) + r"(?!\w)", tekst):
                b, e = m.span()
                if not any(b < x[1] and e > x[0] for x in bezet):
                    bezet.append((b, e))
                    nieuw.append((b, e, mk))
        for b, e, mk in sorted(nieuw, key=lambda x: -x[0]):
            c = _cursor(vak, b, e - b)
            c.setString(mk["plaatshouder"])
            c.CharColor = KLEUR.get(int(mk.get("ppl", 1)), KLEUR[1])
            c.CharUnderline = STIPPEL if mk.get("voorvertoning") else 0
    return [p for p in lees_plekken_bladen(document) if p["plek"] not in voor]


def _splits(plek):
    kenmerk, _, n = plek.rpartition("#")
    return kenmerk, int(n or 0)


def herstel_bladen(document, plekken):
    # Per vak van achter naar voren, zodat de nummering van de andere plekken klopt.
    for p in sorted(plekken, key=lambda x: (_splits(x["plek"])[0], -_splits(x["plek"])[1])):
        kenmerk, n = _splits(p["plek"])
        vak = _vak(document, kenmerk)
        if vak is None:
            continue
        treffers = list(PLAATSHOUDER.finditer(vak.getString()))
        if n >= len(treffers):
            continue
        b, e = treffers[n].span()
        c = _cursor(vak, b, e - b)
        c.setString(p["waarde"])
        for naam in ("CharColor", "CharUnderline"):
            try:
                c.setPropertyToDefault(naam)
            except Exception:
                pass


def zet_definitief_bladen(document):
    for _kenmerk, vak in _vakken(document):
        for m in PLAATSHOUDER.finditer(vak.getString()):
            b, e = m.span()
            _cursor(vak, b, e - b).CharUnderline = 0


def toon_bladen(document, plek):
    from oa_bladen import soort_van
    vak = _vak(document, _splits(plek)[0])
    if vak is None:
        return
    c = document.getCurrentController()
    if soort_van(document) == "presentatie":
        kenmerk = _splits(plek)[0]
        c.setCurrentPage(document.getDrawPages().getByIndex(int(kenmerk[1:kenmerk.index("s")])))
    c.select(vak)


def plek_bij_selectie(document):
    """De eerste plaatshouder in de geselecteerde cel of het geselecteerde tekstvak."""
    sel = document.getCurrentController().getSelection()
    if sel is None:
        return None
    kandidaten = []
    if hasattr(sel, "getCellAddress"):
        kandidaten = [sel]
    elif hasattr(sel, "getCount") and hasattr(sel, "getByIndex") and not hasattr(sel, "getRangeAddress"):
        kandidaten = [sel.getByIndex(i) for i in range(sel.getCount())]
    for kenmerk, vak in _vakken(document):
        for k in kandidaten:
            try:
                zelfde = (k == vak) or (hasattr(k, "getCellAddress") and hasattr(vak, "getCellAddress")
                                         and (k.getCellAddress().Sheet, k.getCellAddress().Column, k.getCellAddress().Row)
                                         == (vak.getCellAddress().Sheet, vak.getCellAddress().Column, vak.getCellAddress().Row))
            except Exception:
                zelfde = False
            if zelfde:
                m = PLAATSHOUDER.search(vak.getString())
                if m:
                    return {"plek": "%s#0" % kenmerk, "plaatshouder": m.group(0), "voorvertoning": False}
    return None
