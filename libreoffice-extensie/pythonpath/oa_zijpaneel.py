# -*- coding: utf-8 -*-
"""Het zijpaneel "Assistent" in Writer, met de eigen schermelementen van LibreOffice.

LibreOffice heeft geen browser in de zijbalk; dit paneel tekent zichzelf
met UNO-besturingselementen (tekst, invoervelden, keuzelijsten, knoppen).
Wat het paneel weet en doet, staat in oa_paneelmodel.Model; hier staat
alleen hoe het eruitziet.

Draaiboek:
- De zijbalk vraagt de fabriek (assistent.py, PaneelFabriek) om een paneel
  voor een venster; per document is er één model, ook als de zijbalk het
  paneel opnieuw maakt.
- Een knop start de actie in een eigen thread; het model leest en wijzigt
  het document via WriterDocument, dat UNO op de hoofdthread aanroept.
- Na elke wijziging tekent het paneel zich opnieuw, op de hoofdthread.
"""

import os
import threading
import time
import traceback
from datetime import datetime

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback, XItemListener, XTextListener, XWindowListener
from com.sun.star.awt import Size
from com.sun.star.lang import XComponent
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, LayoutSize

import oa_document as od
from oa_paneelmodel import SESSIES, Model
from oa_verbinding import Aanmelder

def log(*a):
    """Het logboek (Office Assistent → Logboek openen); zie oa_logboek.py."""
    from oa_logboek import log as _log
    _log("paneel", *a)


MARGE = 12
RUIMTE = 6

KLEUREN = {
    "ok": (0xDFF6DD, 0x0B5A08),
    "info": (0xE8F1FB, 0x0B3D6E),
    "waarschuwing": (0xFFF4CE, 0x5C4400),
    "fout": (0xFDE7E9, 0xA4262C),
}
BADGE = {
    "veilig": (0x0B7A2E, 0xFFFFFF),
    "let-op": (0xF3C300, 0x1B1B1B),
    "gevaar": (0xC1121F, 0xFFFFFF),
    "neutraal": (0x5A5A5A, 0xFFFFFF),
}
GRIJS = 0x5A5A5A
REEKSEN = {"StringItemList": "[]string", "SelectedItems": "[]short"}
GROEN = 0x18A303

GEBEURTENISSEN = {
    "object.aangemaakt": "Geregistreerd",
    "metadata.vastgelegd": "Metadata vastgelegd",
    "versie.vastgelegd": "Versie vastgelegd",
    "weergave.toegevoegd": "Weergave toegevoegd",
    "versie.gewaarmerkt": "Versie gewaarmerkt",
    "binding.vastgelegd": "Gekoppeld",
    "object.onleesbaar-gemaakt": "Onleesbaar gemaakt",
}


# ---------------------------------------------------------------------------
# Hoofdthread
# ---------------------------------------------------------------------------


class Hoofdthread(unohelper.Base, XCallback):
    """Werk op de hoofdthread van LibreOffice: wachtend (document) of los (hertekenen)."""

    def __init__(self, ctx):
        self.async_ = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx)
        self.taken = {}
        self.teller = 0
        self.slot = threading.Lock()
        # Het nummer van de hoofdthread. threading.current_thread() is hier
        # onbetrouwbaar: voor een thread die LibreOffice zelf startte, maakt
        # Python een nepobject dat niet steeds hetzelfde is.
        self.hoofd = threading.get_ident()

    def notify(self, nummer):
        with self.slot:
            taak = self.taken.pop(nummer, None)
        if taak:
            taak()

    def later(self, functie):
        with self.slot:
            self.teller += 1
            nummer = self.teller
            self.taken[nummer] = functie
        self.async_.addCallback(self, nummer)

    def voer_uit(self, functie, tijd=60):
        if threading.get_ident() == self.hoofd:
            return functie()
        uitkomst = {}
        klaar = threading.Event()

        def taak():
            try:
                uitkomst["waarde"] = functie()
            except Exception as e:
                uitkomst["fout"] = e
            finally:
                klaar.set()

        self.later(taak)
        if not klaar.wait(tijd):
            raise TimeoutError("LibreOffice reageert niet.")
        if "fout" in uitkomst:
            raise uitkomst["fout"]
        return uitkomst.get("waarde")


class WriterDocument:
    """Het document voor het model; elke UNO-aanroep op de hoofdthread."""

    def __init__(self, document, hoofd):
        self.doc = document
        self.h = hoofd.voer_uit

    def lees_blokken(self):
        return self.h(lambda: od.lees_blokken(self.doc))

    def bestand(self):
        return self.h(lambda: od.bestand(self.doc))

    def bestand_ooxml(self):
        return self.h(lambda: od.bestand(self.doc, ooxml=True))

    def voer_uit(self, opdracht):
        return self.h(lambda: od.voer_uit(self.doc, opdracht))

    def toon(self, doel):
        return self.h(lambda: od.toon(self.doc, doel))

    def lees_eigenschap(self, naam):
        return self.h(lambda: od.lees_eigenschap(self.doc, naam))

    def schrijf_eigenschap(self, naam, waarde):
        return self.h(lambda: od.schrijf_eigenschap(self.doc, naam, waarde))

    def naam(self):
        return self.h(lambda: od.naam_van(self.doc))


# ---------------------------------------------------------------------------
# Eén model per document, en het aanmelden voor alle documenten
# ---------------------------------------------------------------------------

_modellen = {}
_aanmelden = {"aanmelder": None}
_slot = threading.Lock()


def model_voor(ctx, document, basis, hoofd):
    sleutel = document.RuntimeUID
    with _slot:
        m = _modellen.get(sleutel)
        if m is None:
            m = Model(WriterDocument(document, hoofd), basis)
            _modellen[sleutel] = m
            nieuw = True
        else:
            nieuw = False
    return m, nieuw


# Open panelen per document, voor de knoppen in de werkbalk.
_panelen = {}


def paneel_van(document):
    with _slot:
        return _panelen.get(document.RuntimeUID)


def vergeet_document(document):
    with _slot:
        _modellen.pop(document.RuntimeUID, None)


def _bij_aanmelden():
    """Een nieuwe sessie: alle open panelen opnieuw opstarten."""
    with _slot:
        modellen = list(_modellen.values())
    for m in modellen:
        threading.Thread(target=m.start, name="oa-start", daemon=True).start()


SESSIES.luister(_bij_aanmelden)


# ---------------------------------------------------------------------------
# Luisteraars
# ---------------------------------------------------------------------------


class _Knop(unohelper.Base, XActionListener):
    def __init__(self, actie, label=""):
        self.actie = actie
        self.label = label

    def actionPerformed(self, ev):
        log("knop", self.label, "thread", threading.get_ident())
        try:
            self.actie()
        except Exception:
            traceback.print_exc()

    def disposing(self, ev):
        pass


class _Tekst(unohelper.Base, XTextListener):
    def __init__(self, zet):
        self.zet = zet

    def textChanged(self, ev):
        try:
            self.zet(ev.Source.getText())
        except Exception:
            traceback.print_exc()

    def disposing(self, ev):
        pass


class _Keuze(unohelper.Base, XItemListener):
    def __init__(self, zet):
        self.zet = zet

    def itemStateChanged(self, ev):
        try:
            self.zet(ev.Source.getSelectedItemPos())
        except Exception:
            traceback.print_exc()

    def disposing(self, ev):
        pass


class _Formaat(unohelper.Base, XWindowListener):
    def __init__(self, paneel):
        self.paneel = paneel

    def windowResized(self, ev):
        self.paneel.bij_formaat()


class _DocumentFormaat(unohelper.Base, XWindowListener):
    """
    Het documentvenster verandert van maat, bijvoorbeeld als er onderin een
    werkbalk bijkomt (zoeken met Ctrl+F) of verdwijnt. De zijbalk geeft het
    paneel dan uit zichzelf geen nieuwe maat: de webweergave hield haar oude
    hoogte en de onderkant viel weg achter de werkbalk. Vraag daarom om een
    nieuwe opmaak; dan volgt bij_formaat.
    """

    def __init__(self, paneel):
        self.paneel = paneel

    def windowResized(self, ev):
        self.paneel.bij_documentformaat()

    def windowMoved(self, ev):
        pass

    def windowShown(self, ev):
        pass

    def windowHidden(self, ev):
        pass

    def disposing(self, ev):
        pass

    def windowMoved(self, ev):
        pass

    def windowShown(self, ev):
        self.paneel.bij_zichtbaar()

    def windowHidden(self, ev):
        pass

    def disposing(self, ev):
        pass


# ---------------------------------------------------------------------------
# Het paneel
# ---------------------------------------------------------------------------


class Paneel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent):
    def __init__(self, ctx, frame, ouder, zijbalk, url, basis, soort="web"):
        self.ctx = ctx
        self.smgr = ctx.ServiceManager
        self.frame = frame
        self.ouder = ouder
        self.zijbalk = zijbalk
        self.url = url
        self.basis = basis.rstrip("/")
        self.hoofd = Hoofdthread(ctx)
        log("paneel gemaakt, thread", threading.get_ident())
        self.document = frame.getController().getModel()
        self.breedte = max(ouder.getPosSize().Width, 240)
        self.hoogte = 200
        self.besturing = []
        self.teller = 0
        self.weg = False
        self._hertekenen_gepland = False
        self.antwoordvelden = {}
        self._wacht = None

        tk = self.smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
        self.vlak = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControlContainer", ctx)
        model = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControlContainerModel", ctx)
        self.vlak.setModel(model)
        self.vlak.createPeer(tk, ouder)
        self.vlak.setPosSize(0, 0, self.breedte, self.hoogte, 12)  # alleen de maat: de positie is van de zijbalk (schuiven)
        self.vlak.setVisible(True)
        ouder.addWindowListener(_Formaat(self))
        self._documentvenster = None
        self._documentluisteraar = _DocumentFormaat(self)
        try:
            self._documentvenster = frame.getComponentWindow()
            self._documentvenster.addWindowListener(self._documentluisteraar)
        except Exception as e:
            log("documentvenster niet te volgen:", e)

        self._meet()
        self.model, self._nieuw_model = model_voor(ctx, self.document, self.basis, self.hoofd)
        with _slot:
            _panelen[self.document.RuntimeUID] = self
        self.model.bij_wijziging = self.wijziging
        # Optie 1: het webpaneel van de server in een webweergave. Lukt dat
        # niet (of staat "paneel": "eigen" in de instellingen), dan het eigen
        # paneel met de schermelementen van LibreOffice (optie 2).
        self.web = None
        self.brug = None
        self.modus = "web-bezig" if soort == "web" else "eigen"
        if self.modus == "web-bezig":
            self.vlak.setVisible(False)
            self.hoofd.later(self._start_web)
        else:
            self._start_eigen()

    # -- webpaneel of eigen paneel --------------------------------------------

    def _start_web(self):
        if self.weg:
            return
        import oa_webview
        from oa_brug import Brug
        try:
            from oa_logboek import kop, map_
            log("webpaneel starten;", kop())
            self.brug = Brug(self.ctx, self.document, self.basis)
            adres = self.brug.paneeladres() + "&ingebed=1"
            opslag = os.path.join(map_(), "webweergave")
            self.web = oa_webview.maak(self.ouder, adres, opslag, self._extern_openen, self.brug, self.basis, self.hoofd.later)
            self.modus = "web"
            if self._wacht:
                self.web.stuur(self._wacht)
            p = self.ouder.getPosSize()
            self._na(400, lambda: self.web is not None and self.web.ververs(p.Width, p.Height))
            self._vraag_opmaak()
        except Exception as e:
            log("webpaneel lukt niet:", e)
            if self.brug is not None:
                self.brug.stop()
                self.brug = None
            self.modus = "eigen"
            if not isinstance(e, oa_webview.NietBeschikbaar):
                traceback.print_exc()
            self.vlak.setVisible(True)
            self._start_eigen()
            if not self.model.melding:
                reden = str(e).strip().rstrip(".")
                reden = reden[:1].lower() + reden[1:]
                self.model.melding = {"soort": "info", "tekst": "Het webpaneel kan hier niet: %s. Je ziet het eigen paneel van LibreOffice. Alles (ook anonimiseren in het document) kan via Assistent in de browser openen. Details: Office Assistent → Logboek openen." % reden}
                self.teken()

    def _start_eigen(self):
        import oa_bladen
        if oa_bladen.soort_van(self.document) != "tekst":
            # Het eigen paneel kan (nog) alleen tekst; rekenblad en presentatie
            # gaan via het webpaneel of het paneel in de browser.
            self.alleen_melding = ("Het eigen paneel van LibreOffice werkt nog alleen in Writer. Voor rekenbladen en presentaties: "
                                   "kies Office Assistent → Zijpaneel: webpaneel van de server (Linux), of Assistent in de browser openen.")
        self.teken()
        if self._nieuw_model:
            self._op_achtergrond(self.model.start)

    def _open_browser(self):
        """Het webpaneel in de browser, met een brug naar dit document (zolang dit paneel bestaat)."""
        from oa_brug import Brug
        if self.brug is None:
            self.brug = Brug(self.ctx, self.document, self.basis)
        shell = self.smgr.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
        shell.execute(self.brug.paneeladres(), "", 1)  # 1 = URIS_ONLY

    def _extern_openen(self, adres):
        if not adres or not adres.startswith("https://"):
            return
        shell = self.smgr.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
        shell.execute(adres, "", 1)  # 1 = URIS_ONLY

    # -- XUIElement / XToolPanel / XSidebarPanel ---------------------------------

    def getRealInterface(self):
        return self

    @property
    def Frame(self):
        return self.frame

    @property
    def ResourceURL(self):
        return self.url

    @property
    def Type(self):
        return uno.getConstantByName("com.sun.star.ui.UIElementType.TOOLPANEL")

    def getWindow(self):
        return self.vlak

    def createAccessible(self, ouder):
        return None

    def getHeightForWidth(self, breedte):
        if self.modus != "eigen":
            # De webweergave scrolt zelf: neem de hele hoogte van de zijbalk.
            return LayoutSize(300, 100000, 300)
        log("getHeightForWidth", breedte, "->", self.hoogte)
        self._nieuwe_breedte(breedte)
        return LayoutSize(self.hoogte, self.hoogte, self.hoogte)

    def getMinimalWidth(self):
        return 240

    def opdracht(self, opdracht):
        """Een knop in de werkbalk. Het webpaneel toont de module; het eigen paneel heeft geen modules."""
        if self.modus == "web" and self.web is not None:
            self.hoofd.later(lambda: self.web.stuur(opdracht))
            self._ververs_straks()
        else:
            self._wacht = opdracht  # webpaneel nog in aanbouw; het eigen paneel negeert het

    def dispose(self):
        self.weg = True
        if self._documentvenster is not None:
            try:
                self._documentvenster.removeWindowListener(self._documentluisteraar)
            except Exception:
                pass
        with _slot:
            if _panelen.get(self.document.RuntimeUID) is self:
                _panelen.pop(self.document.RuntimeUID, None)
        if self.web is not None:
            self.web.weg()
        if self.brug is not None:
            self.brug.stop()
        if self.model.bij_wijziging == self.wijziging:
            self.model.bij_wijziging = lambda: None
        try:
            self._leeg()
            self.vlak.dispose()
        except Exception:
            pass

    def addEventListener(self, l):
        pass

    def removeEventListener(self, l):
        pass

    # -- verversen ----------------------------------------------------------------

    def wijziging(self):
        """Het model is veranderd (vaak vanuit een andere thread): één keer hertekenen."""
        if self.weg or self._hertekenen_gepland:
            return
        self._hertekenen_gepland = True

        def doe():
            self._hertekenen_gepland = False
            if not self.weg:
                self.teken()

        self.hoofd.later(doe)

    def _ververs_straks(self, ms=500):
        """Na het openklappen van de zijbalk: opnieuw tekenen als de maat vaststaat."""
        def doe():
            if self.web is not None and not self.weg:
                p = self.ouder.getPosSize()
                self.web.ververs(p.Width, p.Height)
            return False

        self._na(ms, doe)

    def _na(self, ms, functie):
        """Over ms milliseconden op de hoofdthread (op elk systeem; geen GLib nodig)."""
        threading.Timer(ms / 1000.0, lambda: self.hoofd.later(functie)).start()

    def bij_zichtbaar(self):
        if self.web is not None:
            p = self.ouder.getPosSize()
            self.hoofd.later(lambda: self.web.ververs(p.Width, p.Height))

    def bij_formaat(self):
        if self.web is not None:
            p = self.ouder.getPosSize()
            self.web.maat(p.Width, p.Height)
            # Kleiner geworden: de webweergave tekent anders niet opnieuw en de onderkant blijft weg.
            self._ververs_straks(150)
            return
        if self.modus != "eigen":
            return
        self._nieuwe_breedte(self.ouder.getPosSize().Width)

    def bij_documentformaat(self):
        if self.web is not None and not self.weg:
            self.hoofd.later(self._vraag_opmaak)

    def _nieuwe_breedte(self, b):
        """
        Een andere breedte: later opnieuw tekenen, nooit midden in een
        opmaakronde van de zijbalk (dan verdwijnt bijvoorbeeld de knop waar
        net op wordt geklikt). Smaller altijd; breder pas vanaf 20 pixels,
        zodat een schuifbalk die komt en gaat geen pingpong geeft.
        """
        if b <= 0:
            return
        if b < self.breedte - 1 or b > self.breedte + 20:
            self.breedte = b
            self.wijziging()

    def _op_achtergrond(self, f, *a):
        threading.Thread(target=f, args=a, name="oa-actie", daemon=True).start()

    # -- bouwstenen ------------------------------------------------------------------

    def _meet(self):
        """Hoe hoog knoppen en velden in deze LibreOffice zijn (GTK, Qt en Windows verschillen)."""
        self.y = 0
        maten = {}
        for soort, eig in (("Button", {"Label": "Xg"}), ("Edit", {"Text": "Xg", "Border": 1}), ("ListBox", {"Dropdown": True, "Border": 1})):
            try:
                c = self._maak(soort, 0, 0, 100, 20, **eig)
                maten[soort] = c.getPreferredSize().Height
            except Exception:
                maten[soort] = 0
        self._leeg()
        self.knop_h = max(26, maten.get("Button", 0))
        self.invoer_h = max(24, maten.get("Edit", 0))
        self.keuze_h = max(24, maten.get("ListBox", 0))
        log("maten", maten)

    def _leeg(self):
        for b in self.besturing:
            try:
                self.vlak.removeControl(b)
                b.dispose()
            except Exception:
                pass
        self.besturing = []
        self.antwoordvelden = {}

    def _maak(self, soort, x, y, b, h, **eig):
        self.teller += 1
        model = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControl%sModel" % soort, self.ctx)
        for k, w in eig.items():
            if k in REEKSEN:
                # Een tuple wordt []any; UNO wil hier een reeks van een vast type.
                uno.invoke(model, "setPropertyValue", (k, uno.Any(REEKSEN[k], tuple(w))))
            else:
                model.setPropertyValue(k, w)
        c = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControl%s" % soort, self.ctx)
        c.setModel(model)
        self.vlak.addControl("c%d" % self.teller, c)
        c.setPosSize(x, y, b, h, 15)
        self.besturing.append(c)
        return c

    def tekst(self, t, grootte=9.0, vet=False, kleur=None, achter=None, x=None, b=None, uitlijnen=0, rand=0):
        """Een tekst over de volle breedte (of van x, b breed); geeft de hoogte."""
        x = MARGE if x is None else x
        b = (self.breedte - 2 * MARGE) if b is None else b
        eig = {"Label": t, "MultiLine": True, "FontDescriptor": self._letter(grootte, vet), "Align": uitlijnen, "Border": rand}
        if kleur is not None:
            eig["TextColor"] = kleur
        if achter is not None:
            eig["BackgroundColor"] = achter
        c = self._maak("FixedText", x, self.y, b, 20, **eig)
        h = self._hoogte_van(c, b, grootte, t)
        c.setPosSize(x, self.y, b, h, 15)
        return h

    def _letter(self, grootte, vet=False):
        f = uno.createUnoStruct("com.sun.star.awt.FontDescriptor")
        f.Height = int(round(grootte))
        f.Weight = 150.0 if vet else 100.0
        return f

    def _hoogte_van(self, c, b, grootte, t):
        try:
            s = c.calcAdjustedSize(Size(b, 0))
            if s.Height > 0:
                return s.Height + 2
        except Exception:
            pass
        regel = int(grootte * 1.9)
        per_regel = max(10, int(b / (grootte * 0.62)))
        regels = sum(max(1, -(-len(r) // per_regel)) for r in t.split("\n"))
        return regels * regel

    def regel(self, t, **k):
        self.y += self.tekst(t, **k) + RUIMTE

    def kop(self, t):
        self.y += 6
        self._maak("FixedLine", MARGE, self.y, self.breedte - 2 * MARGE, 4)
        self.y += 8
        self.y += self.tekst(t, grootte=11, vet=True) + RUIMTE

    def knop(self, label, actie, aan=True, x=None, b=None, standaard=False):
        x = MARGE if x is None else x
        if b is None:
            b = min(self.breedte - 2 * MARGE, max(90, int(len(label) * 7.2) + 24))
        eig = {"Label": label, "Enabled": bool(aan), "DefaultButton": standaard}
        c = self._maak("Button", x, self.y, b, self.knop_h, **eig)
        c.addActionListener(_Knop(actie, label))
        try:
            nodig = c.getPreferredSize().Width + 8
            if nodig > b:
                b = min(self.breedte - x - MARGE, nodig)
                c.setPosSize(x, self.y, b, self.knop_h, 15)
        except Exception:
            pass
        return b

    def knoppenregel(self, knoppen):
        """Knoppen naast elkaar; past het niet, dan onder elkaar."""
        x = MARGE
        for label, actie, aan in knoppen:
            b = min(self.breedte - 2 * MARGE, max(80, int(len(label) * 7.2) + 24))
            if x > MARGE and x + b > self.breedte - MARGE:
                x = MARGE
                self.y += self.knop_h + RUIMTE
            b = self.knop(label, actie, aan, x=x, b=b)
            x += b + RUIMTE
        self.y += self.knop_h + RUIMTE

    def badge(self, t, soort, x):
        achter, voor = BADGE[soort]
        b = int(len(t) * 6.4) + 14
        self._maak("FixedText", x, self.y, b, 18, Label=t, FontDescriptor=self._letter(8, True), Align=1, BackgroundColor=achter, TextColor=voor, VerticalAlign=uno.Enum("com.sun.star.style.VerticalAlignment", "MIDDLE"))
        return b

    def gegeven(self, sleutel, waarde=None, badge=None):
        """Een regel "Sleutel   waarde" (of een badge)."""
        kb = 92
        self.tekst(sleutel, kleur=GRIJS, b=kb - 4)
        x = MARGE + kb
        if badge:
            self.badge(badge[0], badge[1], x)
            self.y += 18 + 4
        else:
            self.y += self.tekst(waarde, x=x, b=self.breedte - MARGE - x) + 4

    def invoer(self, veld, waarde, fout):
        naam = veld["naam"]
        b = self.breedte - 2 * MARGE
        zet = lambda w, n=naam: self.model.zet_veld(n, w)  # noqa: E731
        if veld["soort"] == "keuze":
            opties = veld.get("opties") or []
            items = ("Kies…",) + tuple(opties)
            sel = opties.index(waarde) + 1 if waarde in opties else 0
            c = self._maak("ListBox", MARGE, self.y, b, self.keuze_h, Dropdown=True, StringItemList=items, SelectedItems=(sel,), LineCount=min(12, len(items)), Border=1)
            c.addItemListener(_Keuze(lambda i, o=opties: zet(o[i - 1] if i >= 1 else "")))
            self.y += self.keuze_h + RUIMTE
        elif veld["soort"] == "lange-tekst":
            eig = {"Text": waarde, "MultiLine": True, "VScroll": True, "Border": 0}
            if veld.get("maxLengte"):
                eig["MaxTextLen"] = int(veld["maxLengte"])
            h = max(64, 2 * self.invoer_h)
            c = self._maak("Edit", MARGE + 1, self.y + 1, b - 2, h - 2, **eig)
            # Een eigen rand: GTK tekent om een tekstvak van meer regels geen kader.
            for x, y, bb, hh in ((MARGE, self.y, b, 1), (MARGE, self.y + h - 1, b, 1), (MARGE, self.y, 1, h), (MARGE + b - 1, self.y, 1, h)):
                self._vlak(x, y, bb, hh, 0x9A9A9A)
            c.addTextListener(_Tekst(zet))
            self.y += h + RUIMTE
        else:
            if veld["soort"] == "datum":
                self.regel("Als jjjj-mm-dd, bijvoorbeeld 2026-11-09.", grootte=8.5, kleur=GRIJS)
            eig = {"Text": waarde, "Border": 1}
            if veld.get("maxLengte"):
                eig["MaxTextLen"] = int(veld["maxLengte"])
            c = self._maak("Edit", MARGE, self.y, b, self.invoer_h, **eig)
            c.addTextListener(_Tekst(zet))
            self.y += self.invoer_h + RUIMTE
        if fout:
            self.regel(fout, grootte=8.5, kleur=KLEUREN["fout"][1])

    # -- tekenen --------------------------------------------------------------------

    def teken(self, melden=True):
        if self.modus != "eigen":
            return
        oud = self.hoogte
        try:
            self.vlak.setVisible(False)
            self._leeg()
            self.y = MARGE
            m = self.model
            if getattr(self, "alleen_melding", None):
                self._kopregel()
                self.regel(self.alleen_melding)
                self.knop("Assistent in de browser openen", self._open_browser)
                self.y += self.knop_h + RUIMTE
            elif m.fase == "aanmelden":
                self._teken_aanmelden()
            else:
                self._teken_assistent()
            self.hoogte = self.y + MARGE
            self.vlak.setPosSize(0, 0, self.breedte, self.hoogte, 12)  # alleen de maat: de positie is van de zijbalk (schuiven)
        except Exception:
            traceback.print_exc()
        finally:
            self.vlak.setVisible(True)
        o, v = self.ouder.getPosSize(), self.vlak.getPosSize()
        log("teken", self.model.fase, self.breedte, "x", self.hoogte, "ouder", (o.X, o.Y, o.Width, o.Height), "vlak", (v.X, v.Y, v.Width, v.Height))
        if melden and self.zijbalk is not None and self.hoogte != oud:
            self._vraag_opmaak()
            # Nog een keer als de zijbalk klaar is: anders blijft een deel van
            # het paneel soms onklikbaar na een grote verandering in hoogte.
            self.hoofd.later(self._vraag_opmaak)

    def _vraag_opmaak(self):
        if self.weg or self.zijbalk is None:
            return
        try:
            self.zijbalk.requestLayout()
        except Exception:
            pass

    def _kopregel(self, onder=None):
        self.y += self.tekst("Assistent", grootte=14, vet=True, kleur=GROEN) + 2
        if onder:
            self.regel(onder, grootte=8.5, kleur=GRIJS)

    def _vlak(self, x, y, b, h, kleur):
        return self._maak("FixedText", x, y, b, h, Label="", BackgroundColor=kleur)

    def _melding(self):
        """Een melding met een gekleurde streep links, zoals een Alert in NL Design System."""
        m = self.model.melding
        if not m:
            return
        achter, voor = KLEUREN.get(m["soort"], KLEUREN["info"])
        b = self.breedte - 2 * MARGE
        boven = self.y
        self.y += 6
        h = self.tekst(m["tekst"], kleur=voor, achter=achter, x=MARGE + 12, b=b - 20)
        # Geen overlap: niet elke weergave tekent overlappende vlakken in dezelfde volgorde.
        self._vlak(MARGE, boven, 4, h + 12, voor)
        self._vlak(MARGE + 4, boven, b - 4, 6, achter)
        self._vlak(MARGE + 4, boven + 6, 8, h, achter)
        self._vlak(MARGE + b - 8, boven + 6, 8, h, achter)
        self._vlak(MARGE + 4, boven + 6 + h, b - 4, 6, achter)
        self.y = boven + h + 12 + RUIMTE

    def _teken_aanmelden(self):
        self._kopregel()
        self._melding()
        bezig = _aanmelden["aanmelder"] is not None and not _aanmelden["aanmelder"].gebruikt
        if bezig:
            self.regel("Meld je aan in de browser die net openging. Daarna verschijnt de assistent hier vanzelf.")
            self.knoppenregel([("Browser opnieuw openen", self.open_aanmelden, True), ("Annuleren", self.annuleer_aanmelden, True)])
        else:
            self.regel("Meld je aan om de assistent te gebruiken. Dat gaat via je browser, met je gewone inlog en je authenticator-app.")
            self.knop("Aanmelden", self.aanmelden, standaard=True)
            self.y += self.knop_h + RUIMTE
            self.regel("Je blijft aangemeld tot je LibreOffice sluit.", grootte=8.5, kleur=GRIJS)

    def _teken_assistent(self):
        m = self.model
        omgeving = "LibreOffice Writer"
        if m.wie:
            self._kopregel("%s · %s · in %s" % (m.wie.get("naam"), m.wie.get("gemeente"), omgeving))
        else:
            self._kopregel("in %s" % omgeving)
        self._melding()
        if m.bezig:
            self.regel("Bezig: %s…" % m.bezig.split("-")[0], grootte=8.5, kleur=GRIJS)
        if m.fase == "laden" and not m.wie:
            if not m.bezig and m.onbereikbaar:
                self.knop("Opnieuw proberen", lambda: self._op_achtergrond(m.start))
                self.y += self.knop_h + RUIMTE
            return
        uit = m.uit or m.bezig is not None

        # Dit stuk
        self.kop("Dit stuk")
        if m.object:
            o = m.object
            versies = o.get("versies") or []
            self.gegeven("Identificatie", o["identificatie"][:8] + "…")
            self.gegeven("Versie", str(versies[-1]["nummer"]) if versies else "geen")
            if versies:
                from oa_kern import bestandsomschrijving
                self.gegeven("Bestand", bestandsomschrijving(versies[-1]))
            if o.get("onleesbaarGemaakt"):
                self.gegeven("Inhoud", badge=("onleesbaar gemaakt", "gevaar"))
            elif o.get("versleuteld"):
                self.gegeven("Inhoud", badge=("versleuteld, eigen sleutel", "veilig"))
            else:
                self.gegeven("Inhoud", "niet versleuteld")
            vol = o.get("volledigheid") or {"volledig": True, "ontbreekt": []}
            self.gegeven("Metadata", badge=("volledig", "veilig") if vol.get("volledig") else ("%d verplicht open" % len(vol.get("ontbreekt") or []), "let-op"))
            if o.get("onleesbaarGemaakt"):
                self.regel("De sleutel van dit stuk is vernietigd. De registratie blijft bestaan; nieuwe versies kunnen niet meer worden vastgelegd.", grootte=8.5)
            self.y += 2
            self.knop("Versie vastleggen", lambda: self._op_achtergrond(m.leg_versie_vast), aan=not uit and not o.get("onleesbaarGemaakt"))
            self.y += self.knop_h + RUIMTE
        else:
            self.regel("Dit stuk is nog niet geregistreerd. Vul de metadata in en registreer het; het platform geeft het dan een eigen identificatie.")

        # Metadata: na het registreren ingeklapt; aanvullende velden achter "Meer velden".
        self.kop("Metadata")
        ui = m.__dict__.setdefault("ui", {})
        open_md = ui.get("metadata_open", not m.geregistreerd) or bool(m.fouten)
        if not open_md:
            gevuld = sum(1 for v in m.velden if m.metadata.get(v["naam"]))
            self.regel("%d van %d velden ingevuld." % (gevuld, len(m.velden)), grootte=8.5, kleur=GRIJS)
            self.knop("Metadata bekijken of wijzigen", lambda: self._zet_ui("metadata_open", True))
            self.y += self.knop_h + RUIMTE
        else:
            alle = ui.get("alle_velden", False) or any(m.fouten.get(v["naam"]) for v in m.velden if not v["verplicht"])
            extra = [v for v in m.velden if not v["verplicht"]]
            for v in m.velden:
                if not v["verplicht"] and not alle and not m.metadata.get(v["naam"]) and v["naam"] not in m.voorstellen:
                    continue
                self._veld(v)
            verborgen = [v for v in extra if not alle and not m.metadata.get(v["naam"]) and v["naam"] not in m.voorstellen]
            if verborgen:
                self.knop("Meer velden (%d)" % len(verborgen), lambda: self._zet_ui("alle_velden", True))
                self.y += self.knop_h + RUIMTE
            if m.geregistreerd:
                self.knoppenregel([("Metadata vastleggen", lambda: self._op_achtergrond(m.leg_metadata_vast), not uit),
                                   ("Inklappen", lambda: self._zet_ui("metadata_open", False), True)])
            else:
                self.knop("Registreren", lambda: self._op_achtergrond(m.registreer), aan=not uit, standaard=True)
                self.y += self.knop_h + RUIMTE
            open_ = m.ontbreekt
            if open_:
                namen = ", ".join(b["melding"].replace(" is nog niet ingevuld.", "") for b in open_)
                self.regel("Nog open: %s. Registreren kan al; het stuk heet dan onvolledig." % namen, grootte=8.5, kleur=GRIJS)

        # Toegankelijkheid
        self.kop("Toegankelijkheid")
        self.regel("Beoordelen leest alleen en legt niets vast.", grootte=8.5, kleur=GRIJS)
        self.knop("Opnieuw beoordelen" if m.bevindingen is not None else "Beoordelen", lambda: self._op_achtergrond(m.beoordeel), aan=not uit)
        self.y += self.knop_h + RUIMTE
        if m.bevindingen is not None and not m.bevindingen:
            self.regel("Geen bevindingen. Het stuk voldoet aan de gecontroleerde punten.")
        for b in m.bevindingen or []:
            self._bevinding(b, uit)

        # Geschiedenis
        if m.geschiedenis:
            self.kop("Geschiedenis")
            for g in list(reversed(m.geschiedenis))[:5]:
                wie = (g.get("actor") or {}).get("naam") or (g.get("actor") or {}).get("sub") or ""
                self.regel("%s — %s, %s" % (GEBEURTENISSEN.get(g.get("type"), g.get("type")), wie, _tijd(g.get("tijdstip"))), grootte=8.5)

        self.y += 4
        self._maak("FixedLine", MARGE, self.y, self.breedte - 2 * MARGE, 4)
        self.y += 8
        self.knoppenregel([("Vernieuwen", lambda: self._op_achtergrond(m.start), m.bezig is None), ("Afmelden", self.afmelden, m.bezig is None)])

    def _veld(self, v):
        m = self.model
        self.y += self.tekst(v["label"] + (" (verplicht)" if v["verplicht"] else ""), vet=True) + 1
        if v.get("beschrijving"):
            self.y += self.tekst(v["beschrijving"], grootte=8, kleur=GRIJS) + 2
        voorstel = m.voorstellen.get(v["naam"])
        if voorstel and not m.metadata.get(v["naam"]):
            tb = self.breedte - 2 * MARGE - 100
            h = self.tekst("Voorstel: ‘%s’" % voorstel, grootte=8.5, b=tb)
            self.knop("Overnemen", lambda n=v["naam"]: m.neem_voorstel_over(n), x=self.breedte - MARGE - 94, b=94)
            self.y += max(h, self.knop_h) + 2
        self.invoer(v, m.metadata.get(v["naam"], ""), m.fouten.get(v["naam"]))

    def _zet_ui(self, sleutel, waarde):
        self.model.__dict__.setdefault("ui", {})[sleutel] = waarde
        self.teken()

    def _bevinding(self, b, uit):
        m = self.model
        self.y += 4
        soort = {"fout": "gevaar", "waarschuwing": "let-op"}.get(b.get("ernst"), "neutraal")
        self.badge(b.get("ernst", ""), soort, MARGE)
        self.y += 18 + 4
        self.y += self.tekst(b.get("melding", "")) + 2
        plek = b.get("plek")
        bron = " · uit het bestand" if b.get("bron") == "bestand" else ""
        self.regel(b.get("regel", "") + (" · " + plek["beschrijving"] if plek else "") + bron, grootte=8, kleur=GRIJS)
        # Zonder pad (een bevinding uit het bestand) kan de assistent de plek niet aanwijzen of herstellen.
        plek = plek if plek and plek.get("pad") else None
        v = b.get("voorstel") or {}
        if v.get("beschrijving"):
            self.regel(v["beschrijving"], grootte=8.5)
        vraag = v.get("vraag")
        if vraag:
            c = self._maak("Edit", MARGE, self.y, self.breedte - 2 * MARGE, self.invoer_h, Text=m.antwoorden.get(b["id"], ""), Border=1, HelpText=vraag.get("label", ""))
            c.addTextListener(_Tekst(lambda w, i=b["id"]: m.antwoorden.__setitem__(i, w)))
            self.y += self.invoer_h + 2
            self.regel(vraag.get("label", ""), grootte=8, kleur=GRIJS)
        knoppen = []
        if plek:
            knoppen.append(("Toon", lambda i=b["id"]: self._op_achtergrond(m.toon, i), True))
        if (v.get("vervanging") or vraag) and plek:
            knoppen.append(("Toepassen" if vraag else "Herstellen", lambda i=b["id"]: self._herstel(i), not uit))
        if knoppen:
            self.knoppenregel(knoppen)

    def _herstel(self, i):
        b = next((x for x in (self.model.bevindingen or []) if x["id"] == i), None)
        if b and not self.model.kan_herstellen(b):
            self.model.melding = {"soort": "info", "tekst": "Vul eerst het antwoord in."}
            self.teken()
            return
        self._op_achtergrond(self.model.herstel, i)

    # -- aanmelden ---------------------------------------------------------------------

    def aanmelden(self):
        a = _aanmelden["aanmelder"]
        if a is not None:
            a.stop()

        def klaar(sessie):
            _aanmelden["aanmelder"] = None
            SESSIES.zet(sessie)

        _aanmelden["aanmelder"] = Aanmelder(self.basis, klaar)
        self.open_aanmelden()
        self.teken()

    def open_aanmelden(self):
        a = _aanmelden["aanmelder"]
        if a is None:
            return
        shell = self.smgr.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
        shell.execute(a.adres(), "", 1)  # 1 = URIS_ONLY

    def annuleer_aanmelden(self):
        a = _aanmelden["aanmelder"]
        _aanmelden["aanmelder"] = None
        if a is not None:
            a.stop()
        self.teken()

    def afmelden(self):
        SESSIES.sleutel = None
        with _slot:
            modellen = list(_modellen.values())
        for m in modellen:
            m.afgemeld()


def _tijd(iso):
    try:
        t = datetime.fromisoformat((iso or "").replace("Z", "+00:00")).astimezone()
        maanden = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
        return "%d %s %02d:%02d" % (t.day, maanden[t.month - 1], t.hour, t.minute)
    except Exception:
        return iso or ""
