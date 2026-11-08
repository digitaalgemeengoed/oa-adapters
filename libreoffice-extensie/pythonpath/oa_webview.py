# -*- coding: utf-8 -*-
"""Het webpaneel van de server in de zijbalk van Writer (optie 1).

Het paneel van de Office Assistent is één webcomponent, in elke
werkomgeving hetzelfde (MIRA, Techniek). LibreOffice heeft geen webweergave
in de zijbalk; deze module hangt er een in:

- Linux met de GTK-weergave van LibreOffice (de gewone op Ubuntu, Debian,
  Fedora): een WebKitGTK-webweergave, in hetzelfde proces, in het vlak dat
  LibreOffice voor het paneel maakt. GTK draait daar al; de webweergave
  wordt een gewoon onderdeel van het venster.
- Elders (Windows, macOS, of LibreOffice zonder GTK): nog niet. Het
  zijpaneel valt dan terug op het eigen paneel (oa_zijpaneel.py).

Het webpaneel praat met de integratielaag zoals altijd (inloggen met het
cookie in de webweergave) en met het document via de lokale brug
(oa_brug.py), net als het paneel in de browser.

Nodig op Linux: PyGObject en WebKitGTK met introspectie
(Ubuntu en Debian: python3-gi en gir1.2-webkit2-4.1).
"""

import json
import os
import secrets
import sys
import threading


def log(*a):
    pad = os.environ.get("OA_LOG")
    if pad:
        import time
        with open(pad, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + "webview " + " ".join(str(x) for x in a) + "\n")


class NietBeschikbaar(Exception):
    """Hier kan geen webweergave in de zijbalk; de reden staat in de melding."""


def _gtk_weergave():
    """Draait LibreOffice met de GTK-weergave (gtk3)? Alleen dan delen we de GTK-lus."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        with open("/proc/self/maps", encoding="utf-8", errors="replace") as f:
            return "libvclplug_gtk3" in f.read()
    except OSError:
        return False


def _laad_gi():
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("WebKit2", "4.1")
        except ValueError:
            gi.require_version("WebKit2", "4.0")
        from gi.repository import Gtk, WebKit2
        return Gtk, WebKit2
    except Exception as e:
        raise NietBeschikbaar("WebKitGTK ontbreekt (%s). Installeer python3-gi en gir1.2-webkit2-4.1." % e)


def _xid_van(venster):
    """Het X11-venster onder een UNO-venster, als dat er is."""
    try:
        import uno
        soort = uno.getConstantByName("com.sun.star.lang.SystemDependent.SYSTEM_XWINDOW")
        h = venster.getWindowHandle(uno.ByteSequence(bytes(16)), soort)
        h = getattr(h, "value", h)
        return getattr(h, "WindowHandle", None)
    except Exception as e:
        log("geen xid:", e)
        return None


def _alle(w):
    yield w
    if hasattr(w, "get_children"):
        for c in w.get_children():
            yield from _alle(c)


def _vind_vlak(Gtk, ouder):
    """
    Het GTK-vlak (OOoFixed) waarin LibreOffice het paneel tekent. Eerst op
    X11-venster; anders (Wayland) aan de vorm: een kindframe in de zijbalk
    (Box > EventBox > Grid > EventBox > OOoFixed) met de breedte van het paneel.
    """
    xid = _xid_van(ouder)
    kandidaten = []
    for top in Gtk.Window.list_toplevels():
        for w in _alle(top):
            if type(w).__name__ != "OOoFixed":
                continue
            if xid:
                try:
                    gw = w.get_window()
                    if gw is not None and hasattr(gw, "get_xid") and gw.get_xid() == xid:
                        return w
                except Exception:
                    pass
            keten = []
            p = w.get_parent()
            while p is not None and len(keten) < 4:
                keten.append(type(p).__name__)
                p = p.get_parent()
            if keten[:4] == ["EventBox", "Grid", "EventBox", "Box"]:
                kandidaten.append((top, w))
    breedte = ouder.getPosSize().Width
    passend = [(t, w) for t, w in kandidaten if abs(w.get_allocation().width - breedte) <= 2 and not w.get_children()]
    actief = [w for t, w in passend if t.is_active()]
    log("kandidaten", len(kandidaten), "passend", len(passend), "actief", len(actief), "xid", xid)
    if len(actief) == 1:
        return actief[0]
    if len(passend) == 1:
        return passend[0][1]
    return None


class Webweergave:
    """Een WebKitGTK-webweergave in het vlak van één zijpaneel."""

    def __init__(self, ouder, adres, opslag, extern_openen, brug=None, herkomst=""):
        if not _gtk_weergave():
            raise NietBeschikbaar("Deze LibreOffice gebruikt geen GTK-weergave.")
        Gtk, WebKit2 = _laad_gi()
        vlak = _vind_vlak(Gtk, ouder)
        if vlak is None:
            raise NietBeschikbaar("Het vlak van het zijpaneel is niet gevonden.")
        self.vlak = vlak
        # Eigen opslag voor cookies en cache, zodat je ingelogd blijft zolang
        # de sessie van de server geldt, los van je gewone browser.
        os.makedirs(opslag, exist_ok=True)
        beheer = WebKit2.WebsiteDataManager(base_data_directory=os.path.join(opslag, "data"), base_cache_directory=os.path.join(opslag, "cache"))
        context = WebKit2.WebContext.new_with_website_data_manager(beheer)
        context.get_cookie_manager().set_persistent_storage(os.path.join(opslag, "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE)
        if os.environ.get("OA_PROEF_TLS_NEGEREN") == "ja":
            # Alleen voor de proef met een eigen certificaat op deze computer.
            beheer.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.IGNORE)
        self.web = WebKit2.WebView.new_with_context(context)
        instellingen = self.web.get_settings()
        instellingen.set_enable_developer_extras(bool(os.environ.get("OA_LOG")))
        instellingen.set_javascript_can_open_windows_automatically(False)
        # Een nieuw venster (target=_blank, window.open) opent in de gewone browser.
        self.web.connect("create", lambda _w, actie: (extern_openen(actie.get_request().get_uri()), None)[1])
        self.web.connect("load-failed", lambda _w, _e, uri, fout: log("laden mislukt", uri, fout.message) and False)
        # Toetsen: LibreOffice stuurt toetsaanslagen naar het GTK-onderdeel met
        # de focus. Geef de webweergave die focus zodra erin wordt geklikt;
        # anders gaat getypte tekst naar het document.
        from gi.repository import GLib
        self.web.set_can_focus(True)

        def focus(*_a):
            # Meteen, en nog eens als LibreOffice klaar is met de klik: VCL
            # pakt bij een klik soms zelf de focus terug.
            self._pak_focus()
            GLib.idle_add(self._pak_focus)
            return False

        self.web.connect("button-press-event", focus)
        self.web.connect("focus-in-event", lambda *_a: log("focus in") and False)
        self.web.connect("focus-out-event", lambda *_a: log("focus uit") and False)
        # Het kanaal naar het document: een https-pagina mag geen http naar
        # 127.0.0.1 (gemengde inhoud), dus praat het paneel in de webweergave
        # via een berichtkanaal van WebKit met de brug, niet via http.
        self.brug = brug
        self.herkomst = herkomst.rstrip("/")
        if brug is not None:
            ucm = self.web.get_user_content_manager()
            ucm.register_script_message_handler("oaBrug")
            ucm.connect("script-message-received::oaBrug", self._bericht)
        p = ouder.getPosSize()
        self.maat(p.Width, p.Height)
        vlak.put(self.web, 0, 0)
        self.web.show()
        self.web.load_uri(adres)
        log("ingebed", p.Width, "x", p.Height, adres.split("#")[0])

    def _bericht(self, _ucm, js):
        try:
            waarde = js.get_js_value() if hasattr(js, "get_js_value") else js
            v = json.loads(waarde.to_json(0))
        except Exception as e:
            log("onleesbaar bericht", e)
            return
        uri = self.web.get_uri() or ""
        if not uri.startswith(self.herkomst + "/") or not secrets.compare_digest(str(v.get("sleutel", "")), self.brug.sleutel):
            log("bericht geweigerd van", uri.split("#")[0])
            return
        nummer = v.get("id")
        methode, pad, lichaam = str(v.get("methode", "GET")), str(v.get("pad", "/")), v.get("lichaam")

        def werk():
            # Buiten de hoofdthread: de brug zet het werk aan het document zelf
            # op de hoofdthread en wacht daarop.
            status, uit = self.brug.antwoord(methode, pad, lichaam)
            from gi.repository import GLib
            GLib.idle_add(self._antwoord, nummer, status, uit)

        threading.Thread(target=werk, name="oa-kanaal", daemon=True).start()

    def _antwoord(self, nummer, status, uit):
        script = "window.__oaBrugAntwoord && window.__oaBrugAntwoord(%s, %s)" % (json.dumps(nummer), json.dumps({"status": status, "lichaam": uit}))
        try:
            if hasattr(self.web, "evaluate_javascript"):
                self.web.evaluate_javascript(script, -1, None, None, None, None, None)
            else:
                self.web.run_javascript(script, None, None, None)
        except Exception as e:
            log("antwoord niet bezorgd", e)
        return False

    def _pak_focus(self):
        top = self.web.get_toplevel()
        if not self.web.has_focus():
            self.web.grab_focus()
        log("focus nu", type(top.get_focus()).__name__ if hasattr(top, "get_focus") and top.get_focus() else None)
        return False

    def maat(self, breedte, hoogte):
        if breedte > 0 and hoogte > 0:
            self.web.set_size_request(breedte, hoogte)

    def herlaad(self):
        self.web.reload()

    def weg(self):
        try:
            self.web.destroy()
        except Exception:
            pass
