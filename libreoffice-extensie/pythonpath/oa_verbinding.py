# -*- coding: utf-8 -*-
"""De verbinding van het zijpaneel met de integratielaag, en het aanmelden.

Het zijpaneel praat, net als elk ander paneel, alleen met de integratielaag
(oa-kern/src/verbinding.ts). In LibreOffice is er geen cookie; de sessie
gaat mee als "Authorization: Bearer", zoals bij de Word-invoegtoepassing.

Aanmelden gaat via de browser: inloggen bij Keycloak (wachtwoord en
authenticator-app) kan alleen daar. De extensie start daarvoor een kleine
webserver op 127.0.0.1 die maar één ding aanneemt: de sessiesleutel, van de
eigen integratielaag, met een eenmalige sleutel die alleen in het adres van
de aanmeldpagina staat (na het #-teken, dus niet naar een server gestuurd).
De sessie blijft alleen in het geheugen van LibreOffice; sluit je
LibreOffice, dan meld je de volgende keer opnieuw aan.

Geen UNO: deze module is zonder LibreOffice te testen.
"""

import json
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LEES = {
    "wie": "/api/lees/wie-ben-ik",
    "objecttype": "/api/lees/objecttypen/%s",
    "object": "/api/lees/objecten/%s",
    "gebeurtenissen": "/api/lees/objecten/%s/gebeurtenissen",
    "toegankelijkheid": "/api/lees/toegankelijkheid",
}
VASTLEG = {
    "objecten": "/api/vastleg/objecten",
    "metadata": "/api/vastleg/objecten/%s/metadata",
    "versies": "/api/vastleg/objecten/%s/versies",
}


class VerbindingsFout(Exception):
    def __init__(self, status, code, melding, details=None):
        super().__init__(melding)
        self.status, self.code, self.melding, self.details = status, code, melding, details

    @property
    def niet_bereikbaar(self):
        """Platform of dienst weg: de assistent biedt niet aan wat zij niet kan waarmaken."""
        return self.status in (0, 502, 503, 504)

    @property
    def niet_ingelogd(self):
        return self.status == 401 or self.code == "niet-ingelogd"


def _id(x):
    return urllib.parse.quote(x, safe="")


class Verbinding:
    def __init__(self, basis, sessie, open_url=None, tijd=60, bij_aanroep=None):
        self.basis = basis.rstrip("/")
        self.sessie = sessie
        self.tijd = tijd
        self._open = open_url or self._standaard_open
        self.bij_aanroep = bij_aanroep

    @staticmethod
    def _standaard_open(verzoek, tijd):
        return urllib.request.urlopen(verzoek, timeout=tijd, context=ssl.create_default_context())

    def vraag(self, methode, pad, lichaam=None):
        data = json.dumps(lichaam).encode("utf-8") if lichaam is not None else None
        kop = {"x-oa-verzoek": "1", "authorization": "Bearer " + self.sessie, "accept": "application/json"}
        if data is not None:
            kop["content-type"] = "application/json"
        verzoek = urllib.request.Request(self.basis + pad, data=data, method=methode, headers=kop)
        status = 0
        try:
            with self._open(verzoek, self.tijd) as r:
                status = r.status
                return json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                f = json.loads(e.read().decode("utf-8"))
            except Exception:
                f = {}
            raise VerbindingsFout(e.code, f.get("fout", "fout"), f.get("melding") or "Fout %d" % e.code, f.get("details"))
        except (urllib.error.URLError, OSError) as e:
            reden = getattr(e, "reason", e)
            if isinstance(reden, ssl.SSLCertVerificationError):
                raise VerbindingsFout(0, "certificaat", "Het certificaat van de server wordt niet vertrouwd. Vraag je beheerder om hulp.")
            raise VerbindingsFout(0, "niet-bereikbaar", "De assistent kan de server nu niet bereiken.")
        finally:
            if self.bij_aanroep:
                self.bij_aanroep(methode, pad, status)

    def wie_ben_ik(self):
        return self.vraag("GET", LEES["wie"])

    def objecttype(self, naam):
        return self.vraag("GET", LEES["objecttype"] % _id(naam))

    def object(self, identificatie):
        return self.vraag("GET", LEES["object"] % _id(identificatie))

    def gebeurtenissen(self, identificatie):
        return self.vraag("GET", LEES["gebeurtenissen"] % _id(identificatie))

    def toegankelijkheid(self, inhoud, taal=None, bestand=None):
        lichaam = {"inhoud": inhoud}
        if taal:
            lichaam["taal"] = taal
        if bestand:
            lichaam["bestand"] = bestand
        return self.vraag("POST", LEES["toegankelijkheid"], lichaam)

    def maak_object(self, objecttype, metadata, inhoud, weergave=None):
        lichaam = {"objecttype": objecttype, "metadata": metadata, "inhoud": inhoud}
        if weergave:
            lichaam["weergave"] = weergave
        return self.vraag("POST", VASTLEG["objecten"], lichaam)

    def leg_metadata_vast(self, identificatie, metadata, verwacht=None):
        lichaam = {"metadata": metadata}
        if verwacht is not None:
            lichaam["verwachteVolgnummer"] = verwacht
        return self.vraag("PUT", VASTLEG["metadata"] % _id(identificatie), lichaam)

    def voeg_versie_toe(self, identificatie, inhoud, weergave=None):
        lichaam = {"inhoud": inhoud}
        if weergave:
            lichaam["weergave"] = weergave
        return self.vraag("POST", VASTLEG["versies"] % _id(identificatie), lichaam)


# ---------------------------------------------------------------------------
# Aanmelden via de browser
# ---------------------------------------------------------------------------


class Aanmelder:
    """
    Wacht op de sessiesleutel van de aanmeldpagina. Eén keer bruikbaar,
    hoogstens `geldig` seconden, alleen vanaf 127.0.0.1 en alleen van de
    eigen integratielaag (Origin) met de eenmalige sleutel.
    """

    def __init__(self, herkomst, klaar, geldig=600):
        self.herkomst = herkomst.rstrip("/")
        self.sleutel = secrets.token_urlsafe(24)
        self.klaar = klaar
        self.gebruikt = False
        self.einde = time.time() + geldig
        aanmelder = self

        class Afhandeling(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _antwoord(self, status, lichaam=None):
                data = json.dumps(lichaam or {}).encode("utf-8")
                self.send_response(status)
                if self.headers.get("Origin") == aanmelder.herkomst:
                    self.send_header("Access-Control-Allow-Origin", aanmelder.herkomst)
                    self.send_header("Vary", "Origin")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                if self.headers.get("Origin") != aanmelder.herkomst:
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", aanmelder.herkomst)
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Vary", "Origin")
                self.end_headers()

            def do_GET(self):
                self._antwoord(404, {"fout": "onbekend"})

            def do_POST(self):
                if self.path != "/sessie" or self.headers.get("Origin") != aanmelder.herkomst:
                    return self._antwoord(403, {"fout": "geen-toegang", "melding": "Dit verzoek komt niet van de aanmeldpagina."})
                if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + aanmelder.sleutel):
                    return self._antwoord(403, {"fout": "geen-toegang", "melding": "Deze aanmelding hoort bij een andere LibreOffice."})
                if aanmelder.gebruikt or time.time() > aanmelder.einde:
                    return self._antwoord(410, {"fout": "verlopen", "melding": "Deze aanmelding is al gebruikt of verlopen. Kies in LibreOffice opnieuw Aanmelden."})
                try:
                    n = min(int(self.headers.get("Content-Length") or 0), 4096)
                    sessie = json.loads(self.rfile.read(n)).get("sessie", "")
                except Exception:
                    sessie = ""
                if not isinstance(sessie, str) or not (8 <= len(sessie) <= 512):
                    return self._antwoord(400, {"fout": "ongeldig", "melding": "Geen sessie ontvangen."})
                aanmelder.gebruikt = True
                aanmelder.klaar(sessie)  # eerst overdragen, dan pas "gelukt" zeggen
                self._antwoord(200, {"ok": True})
                threading.Thread(target=aanmelder.stop, daemon=True).start()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Afhandeling)
        self.poort = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, name="oa-aanmelden", daemon=True).start()
        self._timer = threading.Timer(geldig, self.stop)
        self._timer.daemon = True
        self._timer.start()

    def adres(self):
        return "%s/libreoffice#aanmelden=%d&sleutel=%s" % (self.herkomst, self.poort, self.sleutel)

    def stop(self):
        self._timer.cancel()
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
