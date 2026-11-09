# -*- coding: utf-8 -*-
"""Het webpaneel in de zijbalk op Windows en macOS: wat beide delen.

LibreOffice tekent een paneel van de zijbalk zelf; een webweergave van het
systeem (WebView2 op Windows, WKWebView op macOS) heeft een eigen venster
nodig. Daarom maken we in het paneel een "systemchildwindow": een echt
systeemvenster (HWND, NSView) dat LibreOffice met het paneel meeschuift. De
webweergave hangt daarin (oa_webview_win.py, oa_webview_mac.py).

Het paneel praat met het document via hetzelfde berichtkanaal als op Linux:
window.webkit.messageHandlers.oaBrug (op Windows nagebootst bovenop
chrome.webview), antwoorden via window.__oaBrugAntwoord. Aan de kant van het
paneel (libreoffice/main.ts) verandert dus niets.
"""
import ctypes
import json
import secrets
import sys
import threading

import uno

from oa_logboek import log as _log


def log(*a):
    _log("webview", *a)


class NietBeschikbaar(Exception):
    """Hier kan geen webweergave in de zijbalk; de reden staat in de melding."""


def proces_id():
    """De globale proces-id van LibreOffice (16 bytes); getWindowHandle vraagt die ter controle."""
    namen = ["sal3.dll"] if sys.platform.startswith("win") else ["libuno_sal.dylib.3", "libuno_sal.dylib"]
    for naam in namen:
        try:
            sal = ctypes.CDLL(naam)
            buf = (ctypes.c_uint8 * 16)()
            sal.rtl_getGlobalProcessId(buf)
            return bytes(buf)
        except Exception as e:
            log("geen proces-id via", naam, e)
    return bytes(16)


def systeemkind(ouder, breedte, hoogte):
    """Een systeemvenster in het paneel, waar de webweergave in komt."""
    ctx = uno.getComponentContext()
    tk = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
    d = uno.createUnoStruct("com.sun.star.awt.WindowDescriptor")
    d.Type = uno.Enum("com.sun.star.awt.WindowClass", "SIMPLE")
    d.WindowServiceName = "systemchildwindow"
    d.ParentIndex = -1
    d.Parent = ouder
    d.Bounds = uno.createUnoStruct("com.sun.star.awt.Rectangle", 0, 0, max(breedte, 1), max(hoogte, 1))
    d.WindowAttributes = uno.getConstantByName("com.sun.star.awt.WindowAttribute.SHOW")
    kind = tk.createWindow(d)
    if kind is None:
        raise NietBeschikbaar("LibreOffice maakte geen systeemvenster voor het paneel")
    kind.setVisible(True)
    return kind


def handle(kind, soort):
    """Het venster van het systeem onder een systeemvenster: HWND (Windows) of NSView (macOS)."""
    waarde = kind.getWindowHandle(uno.ByteSequence(proces_id()), uno.getConstantByName("com.sun.star.lang.SystemDependent." + soort))
    waarde = getattr(waarde, "value", waarde)
    if not isinstance(waarde, int) or not waarde:
        raise NietBeschikbaar("LibreOffice gaf het systeemvenster niet door (%r)" % (waarde,))
    return waarde


class SysteemWebweergave:
    """De gedeelde helft: kanaal naar de brug, opdrachten, maat. De rest per systeem."""

    SOORT = ""  # SYSTEM_WIN32 of SYSTEM_MAC

    def __init__(self, ouder, adres, opslag, extern_openen, brug=None, herkomst="", later=None):
        self.later = later or (lambda f: f())
        self.brug = brug
        self.herkomst = herkomst.rstrip("/")
        self.extern_openen = extern_openen
        self.wacht = None
        p = ouder.getPosSize()
        self.breedte, self.hoogte = p.Width, p.Height
        self.kind = systeemkind(ouder, p.Width, p.Height)
        try:
            h = handle(self.kind, self.SOORT)
            log("systeemvenster", hex(h), p.Width, "x", p.Height)
            self._start(h, p.Width, p.Height, adres, opslag)
        except Exception:
            try:
                self.kind.dispose()
            except Exception:
                pass
            raise

    # -- per systeem ------------------------------------------------------
    def _start(self, handle, breedte, hoogte, adres, opslag):
        raise NotImplementedError

    def _voer_uit(self, script):
        raise NotImplementedError

    def _maat(self, breedte, hoogte):
        pass

    def _herlaad(self):
        pass

    def _weg(self):
        pass

    # -- gedeeld ----------------------------------------------------------
    def bericht(self, tekst, uri):
        """Een bericht van het paneel (hoofdthread). Alleen van onze eigen pagina, met de sleutel van de brug."""
        try:
            v = json.loads(tekst) if isinstance(tekst, str) else tekst
        except Exception as e:
            log("onleesbaar bericht", e)
            return
        if self.brug is None:
            return
        if not (uri or "").startswith(self.herkomst + "/") or not secrets.compare_digest(str(v.get("sleutel", "")), self.brug.sleutel):
            log("bericht geweigerd van", (uri or "").split("#")[0])
            return
        nummer = v.get("id")
        methode, pad, lichaam = str(v.get("methode", "GET")), str(v.get("pad", "/")), v.get("lichaam")

        def werk():
            # Buiten de hoofdthread: de brug zet het werk aan het document zelf op de hoofdthread.
            status, uit = self.brug.antwoord(methode, pad, lichaam)
            script = "window.__oaBrugAntwoord && window.__oaBrugAntwoord(%s, %s)" % (json.dumps(nummer), json.dumps({"status": status, "lichaam": uit}))
            self.later(lambda: self._veilig(script))

        threading.Thread(target=werk, name="oa-kanaal", daemon=True).start()

    def _veilig(self, script):
        try:
            self._voer_uit(script)
        except Exception as e:
            log("script niet uitgevoerd", e)

    @staticmethod
    def _opdrachtscript(opdracht):
        o = json.dumps(opdracht)
        return "window.__oaWacht = %s; window.dispatchEvent(new CustomEvent('oa-assistent', {detail: %s}));" % (o, o)

    def geladen(self):
        """De pagina is geladen: een opdracht die al wachtte, nu sturen."""
        if self.wacht:
            self._veilig(self._opdrachtscript(self.wacht))

    def stuur(self, opdracht):
        self.wacht = opdracht
        self._veilig(self._opdrachtscript(opdracht))

    def maat(self, breedte, hoogte):
        if breedte <= 0 or hoogte <= 0:
            return
        self.breedte, self.hoogte = breedte, hoogte
        try:
            self.kind.setPosSize(0, 0, breedte, hoogte, 15)
        except Exception as e:
            log("maat systeemvenster", e)
        self._maat(breedte, hoogte)

    def ververs(self, breedte, hoogte):
        self.maat(breedte, hoogte)

    def herlaad(self):
        self._herlaad()

    def weg(self):
        try:
            self._weg()
        finally:
            try:
                self.kind.dispose()
            except Exception:
                pass
