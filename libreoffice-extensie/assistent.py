# -*- coding: utf-8 -*-
"""Office Assistent voor LibreOffice Writer: zijpaneel, menu en lokale brug.

Het zijpaneel "Assistent" (oa_zijpaneel.py) staat als eigen tabblad in de
zijbalk; PaneelFabriek hieronder maakt het voor elk venster.

"Office Assistent → Assistent in de browser openen" start een kleine
webserver op 127.0.0.1 (alleen deze computer) en opent het paneel in de
browser. Het paneel praat met de integratielaag zoals altijd, en met het
document via deze brug. De brug:

- luistert alleen op 127.0.0.1, op een willekeurige vrije poort;
- eist bij elke vraag een sleutel die alleen in het adres van het paneel
  staat (na het #-teken, dus niet naar een server gestuurd);
- antwoordt alleen aan het adres van de eigen integratielaag (CORS);
- werkt alleen met het document waarvoor hij is geopend.

Elke bewerking van het document gaat via de hoofdthread van LibreOffice
(AsyncCallback), niet vanuit de thread van de webserver.
"""

import json
import os
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import uno
import unohelper
from com.sun.star.awt import XCallback
from com.sun.star.task import XJobExecutor
from com.sun.star.ui import XUIElementFactory

import oa_document as od

IMPLEMENTATIE = "nl.digitaalgemeengoed.oa.Assistent"
FABRIEK = "nl.digitaalgemeengoed.oa.PaneelFabriek"
DECK = "OfficeAssistentDeck"
EXTENSIE = "nl.digitaalgemeengoed.office-assistent"


def _instellingen(ctx):
    """instellingen.json uit de extensie: het adres van de integratielaag."""
    try:
        pip = ctx.getByName("/singletons/com.sun.star.deployment.PackageInformationProvider")
        map_ = uno.fileUrlToSystemPath(pip.getPackageLocation(EXTENSIE))
        with open(os.path.join(map_, "instellingen.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"basis": "https://oa.example.org"}


class _Hoofdthread(unohelper.Base, XCallback):
    """Voert een functie uit op de hoofdthread van LibreOffice en wacht op de uitkomst."""

    def __init__(self, ctx):
        self.async_ = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx)
        self.taken = {}
        self.teller = 0
        self.slot = threading.Lock()

    def notify(self, nummer):
        # UNO geeft alleen eenvoudige waarden door; de taak zelf staat hier.
        with self.slot:
            taak = self.taken.pop(nummer, None)
        if taak:
            taak()

    def voer_uit(self, functie, tijd=30):
        uitkomst = {}
        klaar = threading.Event()

        def taak():
            try:
                uitkomst["waarde"] = functie()
            except Exception as e:  # doorgeven aan de webserver
                uitkomst["fout"] = e
            finally:
                klaar.set()

        if self.async_ is None:
            taak()
        else:
            with self.slot:
                self.teller += 1
                nummer = self.teller
                self.taken[nummer] = taak
            self.async_.addCallback(self, nummer)
            if not klaar.wait(tijd):
                raise TimeoutError("LibreOffice reageert niet.")
        if "fout" in uitkomst:
            raise uitkomst["fout"]
        return uitkomst.get("waarde")


class Brug:
    """De webserver op 127.0.0.1 voor één document."""

    def __init__(self, ctx, document, herkomst):
        self.ctx = ctx
        self.document = document
        self.herkomst = herkomst.rstrip("/")
        self.sleutel = secrets.token_urlsafe(24)
        self.hoofd = _Hoofdthread(ctx)
        brug = self

        class Afhandeling(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _kop(self, status, lichaam=None):
                data = json.dumps(lichaam if lichaam is not None else {}, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                if self.headers.get("Origin") == brug.herkomst:
                    self.send_header("Access-Control-Allow-Origin", brug.herkomst)
                    self.send_header("Vary", "Origin")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                if self.headers.get("Origin") != brug.herkomst:
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", brug.herkomst)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT")
                self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Vary", "Origin")
                self.end_headers()

            def _toegestaan(self):
                herkomst = self.headers.get("Origin")
                if herkomst is not None and herkomst != brug.herkomst:
                    return False
                kop = self.headers.get("Authorization", "")
                return secrets.compare_digest(kop, "Bearer " + brug.sleutel)

            def _lichaam(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n > 20 * 1024 * 1024:
                    raise ValueError("Te groot")
                return json.loads(self.rfile.read(n) or b"{}")

            def _behandel(self, methode):
                if not self._toegestaan():
                    return self._kop(401, {"fout": "geen-toegang", "melding": "Deze brug hoort bij een ander paneel."})
                pad = self.path.split("?", 1)[0]
                try:
                    lichaam = self._lichaam() if methode in ("POST", "PUT") else None
                    uit = brug.vraag(methode, pad, lichaam, self.path)
                    return self._kop(200, uit)
                except od.Gewijzigd as e:
                    return self._kop(409, {"fout": "gewijzigd", "melding": str(e)})
                except _Onbekend:
                    return self._kop(404, {"fout": "onbekend", "melding": "Deze vraag kent de brug niet."})
                except _Weg:
                    return self._kop(410, {"fout": "document-weg", "melding": "Het document is gesloten. Open de assistent opnieuw vanuit LibreOffice."})
                except Exception as e:
                    traceback.print_exc()
                    return self._kop(500, {"fout": "intern", "melding": str(e)})

            def do_GET(self):
                self._behandel("GET")

            def do_POST(self):
                self._behandel("POST")

            def do_PUT(self):
                self._behandel("PUT")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Afhandeling)
        self.poort = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, name="oa-brug", daemon=True)
        self.thread.start()

    def vraag(self, methode, pad, lichaam, volledig):
        doc = self.document
        try:
            doc.getText()
        except Exception:
            raise _Weg()
        h = self.hoofd.voer_uit
        if methode == "GET" and pad == "/status":
            return {"naam": h(lambda: od.naam_van(doc)), "versie": "0.5.0"}
        if methode == "GET" and pad == "/blokken":
            return h(lambda: od.lees_blokken(doc))
        if methode == "GET" and pad == "/bestand":
            return h(lambda: od.bestand(doc))
        if methode == "POST" and pad == "/opdracht":
            h(lambda: od.voer_uit(doc, lichaam))
            return {}
        if methode == "POST" and pad == "/toon":
            h(lambda: od.toon(doc, lichaam))
            return {}
        if methode == "POST" and pad == "/vervang":
            h(lambda: od.vervang_alles(doc, lichaam["html"]))
            return {}
        if pad == "/eigenschap":
            if methode == "GET":
                from urllib.parse import parse_qs, urlparse
                naam = parse_qs(urlparse(volledig).query).get("naam", [""])[0]
                return {"waarde": h(lambda: od.lees_eigenschap(doc, naam))}
            if methode == "PUT":
                h(lambda: od.schrijf_eigenschap(doc, lichaam["naam"], lichaam["waarde"]))
                return {}
        raise _Onbekend()

    def paneeladres(self):
        return "%s/libreoffice#brug=%d&sleutel=%s" % (self.herkomst, self.poort, self.sleutel)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class _Onbekend(Exception):
    pass


class _Weg(Exception):
    pass


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
            return oa_zijpaneel.Paneel(self.ctx, frame, ouder, arg.get("Sidebar"), url, _instellingen(self.ctx)["basis"])
        except Exception:
            traceback.print_exc()
            raise


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Assistent, IMPLEMENTATIE, ("com.sun.star.task.Job",))
g_ImplementationHelper.addImplementation(PaneelFabriek, FABRIEK, ("com.sun.star.ui.UIElementFactory",))
