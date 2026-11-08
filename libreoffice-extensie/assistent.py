# -*- coding: utf-8 -*-
"""Office Assistent voor LibreOffice Writer: zijpaneel en menu.

Het tabblad "Assistent" in de zijbalk maakt PaneelFabriek hieronder voor
elk venster (oa_zijpaneel.py). Daarin staat het webpaneel van de server in
een webweergave (oa_webview.py); lukt dat niet, of staat in
instellingen.json "paneel": "eigen", dan het eigen paneel met de
schermelementen van LibreOffice.

"Office Assistent → Assistent in de browser openen" opent het webpaneel in
de browser, met de lokale brug (oa_brug.py) naar dit document.
"""

import json
import os
import threading
import traceback

import uno
import unohelper
from com.sun.star.task import XJobExecutor
from com.sun.star.ui import XUIElementFactory

from oa_brug import Brug

IMPLEMENTATIE = "nl.digitaalgemeengoed.oa.Assistent"
FABRIEK = "nl.digitaalgemeengoed.oa.PaneelFabriek"
DECK = "OfficeAssistentDeck"
EXTENSIE = "nl.digitaalgemeengoed.office-assistent"


VOORKEUR = os.path.join(os.path.expanduser("~"), ".config", "office-assistent", "voorkeur.json")


def _voorkeur():
    try:
        with open(VOORKEUR, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _zet_voorkeur(**k):
    v = _voorkeur()
    v.update(k)
    os.makedirs(os.path.dirname(VOORKEUR), exist_ok=True)
    with open(VOORKEUR, "w", encoding="utf-8") as f:
        json.dump(v, f)


def _instellingen(ctx):
    """instellingen.json uit de extensie: het adres van de integratielaag."""
    try:
        pip = ctx.getByName("/singletons/com.sun.star.deployment.PackageInformationProvider")
        map_ = uno.fileUrlToSystemPath(pip.getPackageLocation(EXTENSIE))
        with open(os.path.join(map_, "instellingen.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"basis": "https://oa.example.org"}


_brug = None
_slot = threading.Lock()


def open_assistent(ctx, document):
    """Start (of herstart) de brug voor dit document en geeft het adres van het paneel."""
    global _brug
    with _slot:
        if _brug is not None:
            _brug.stop()
        _brug = Brug(ctx, document, _instellingen(ctx)["basis"])
        return _brug.paneeladres()


def stop_assistent():
    global _brug
    with _slot:
        if _brug is not None:
            _brug.stop()
            _brug = None


class Assistent(unohelper.Base, XJobExecutor):
    """Het menu "Office Assistent" in Writer."""

    def __init__(self, ctx):
        self.ctx = ctx

    def trigger(self, opdracht):
        try:
            if opdracht == "tonen":
                self._toon_zijpaneel()
                return
            if opdracht in ("paneel-web", "paneel-eigen"):
                _zet_voorkeur(paneel=opdracht.split("-")[1])
                self._bericht("Het zijpaneel gebruikt voortaan %s. Dat geldt voor documenten die je hierna opent (of herstart LibreOffice)." % (
                    "het webpaneel van de server" if opdracht == "paneel-web" else "het eigen paneel van LibreOffice"))
                return
            if opdracht == "stoppen":
                stop_assistent()
                self._bericht("De verbinding met de assistent is verbroken.")
                return
            desktop = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)
            document = desktop.getCurrentComponent()
            if document is None or not document.supportsService("com.sun.star.text.TextDocument"):
                self._bericht("Open eerst een tekstdocument.")
                return
            adres = open_assistent(self.ctx, document)
            shell = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
            shell.execute(adres, "", 1)  # 1 = URIS_ONLY
        except Exception as e:
            traceback.print_exc()
            self._bericht("De assistent kon niet starten: %s" % e)

    def _toon_zijpaneel(self):
        desktop = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)
        controller = desktop.getCurrentFrame().getController()
        zijbalk = controller.getSidebar()
        zijbalk.setVisible(True)
        decks = zijbalk.getDecks()
        if decks.hasByName(DECK):
            decks.getByName(DECK).activate(True)

    def _bericht(self, tekst):
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)
            venster = desktop.getCurrentFrame().getContainerWindow()
            tk = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
            vak = tk.createMessageBox(venster, uno.Enum("com.sun.star.awt.MessageBoxType", "INFOBOX"), 1, "Office Assistent", tekst)
            vak.execute()
        except Exception:
            pass


class PaneelFabriek(unohelper.Base, XUIElementFactory):
    """Maakt het zijpaneel voor een venster (Factories.xcu, Sidebar.xcu)."""

    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, argumenten):
        import oa_zijpaneel

        arg = {a.Name: a.Value for a in argumenten}
        oa_zijpaneel.log("createUIElement", url, sorted(arg))
        ouder = arg.get("ParentWindow")
        frame = arg.get("Frame")
        if ouder is None or frame is None:
            raise RuntimeError("Het zijpaneel heeft een venster nodig.")
        try:
            inst = _instellingen(self.ctx)
            soort = os.environ.get("OA_PANEEL") or _voorkeur().get("paneel") or inst.get("paneel") or "web"
            return oa_zijpaneel.Paneel(self.ctx, frame, ouder, arg.get("Sidebar"), url, inst["basis"], soort)
        except Exception:
            traceback.print_exc()
            raise


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Assistent, IMPLEMENTATIE, ("com.sun.star.task.Job",))
g_ImplementationHelper.addImplementation(PaneelFabriek, FABRIEK, ("com.sun.star.ui.UIElementFactory",))
