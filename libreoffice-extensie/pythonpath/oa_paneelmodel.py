# -*- coding: utf-8 -*-
"""Wat het zijpaneel weet en doet, los van hoe het eruitziet.

Dezelfde stappen als het paneel in de browser (oa-paneel/src/Paneel.tsx):
opstarten (wie ben ik, objecttype, waar staat dit stuk), registreren,
metadata vastleggen, een versie vastleggen, toegankelijkheid beoordelen,
een plek tonen en een bevinding herstellen.

Het model praat met de integratielaag (Verbinding) en met het document via
een Document-object (zie oa_zijpaneel.WriterDocument; in de tests een
nepdocument). Acties lopen buiten de hoofdthread van LibreOffice, zodat
Writer niet bevriest terwijl de server antwoordt; het Document zorgt zelf
dat UNO alleen op de hoofdthread wordt aangeroepen.

Geen UNO: deze module is zonder LibreOffice te testen.
"""

import json
import threading
import time

import oa_kern as kern
from oa_verbinding import Verbinding, VerbindingsFout

OBJECTTYPE = "document"
AFDRUK = "oa-afdruk"


class Sessies:
    """De sessie voor alle documenten in deze LibreOffice, alleen in het geheugen."""

    def __init__(self):
        self.sleutel = None
        self._luisteraars = []
        self._slot = threading.Lock()

    def luister(self, f):
        with self._slot:
            self._luisteraars.append(f)

    def vergeet_luisteraar(self, f):
        with self._slot:
            if f in self._luisteraars:
                self._luisteraars.remove(f)

    def zet(self, sleutel):
        with self._slot:
            self.sleutel = sleutel
            luisteraars = list(self._luisteraars)
        for f in luisteraars:
            try:
                f()
            except Exception:
                pass


SESSIES = Sessies()


class Model:
    def __init__(self, document, basis, sessies=SESSIES, verbinding_maken=None, bij_wijziging=None):
        self.document = document
        self.basis = basis
        self.sessies = sessies
        self._maak_verbinding = verbinding_maken or (lambda sleutel: Verbinding(self.basis, sleutel, bij_aanroep=self._aanroep))
        self.bij_wijziging = bij_wijziging or (lambda: None)
        self.aanroepen = []
        self._herstel()

    def _herstel(self):
        self.fase = "aanmelden" if not self.sessies.sleutel else "laden"
        self.wie = None
        self.type = None
        self.object = None
        self.afdruk = None
        self.metadata = {}
        self.voorstellen = {}
        self.fouten = {}
        self.bevindingen = None
        self.antwoorden = {}
        self.bezig = None
        self.melding = None
        self.onbereikbaar = False
        self.geschiedenis = []
        self.blokken = []
        self.terugval = None

    # -- afgeleid --------------------------------------------------------------

    @property
    def velden(self):
        return kern.velden(self.type) if self.type else []

    @property
    def ontbreekt(self):
        return kern.ontbrekend(self.type, self.metadata) if self.type else []

    @property
    def geregistreerd(self):
        return self.object is not None

    @property
    def uit(self):
        """Vastleggen en beoordelen kunnen nu niet."""
        return self.onbereikbaar or self.wie is None

    def _aanroep(self, methode, pad, status):
        self.aanroepen = ([{"methode": methode, "pad": pad, "status": status, "tijd": time.time()}] + self.aanroepen)[:12]

    @property
    def verbinding(self):
        return self._maak_verbinding(self.sessies.sleutel)

    # -- fouten -------------------------------------------------------------------

    def _fout(self, e):
        if isinstance(e, VerbindingsFout):
            if e.niet_bereikbaar:
                self.onbereikbaar = True
                self.melding = {"soort": "waarschuwing", "tekst": e.melding if e.code == "certificaat" else
                                "De assistent kan de server nu niet bereiken. Je kunt gewoon doorwerken; vastleggen kan weer zodra de verbinding terug is."}
                return
            if e.niet_ingelogd:
                self.sessies.sleutel = None
                self._herstel()
                self.melding = {"soort": "waarschuwing", "tekst": "Je bent niet (meer) aangemeld. Meld je opnieuw aan om de assistent te gebruiken."}
                return
            if e.code == "metadata-ongeldig" and isinstance(e.details, list):
                self.fouten = {d.get("veld"): d.get("melding") for d in e.details if isinstance(d, dict)}
            self.melding = {"soort": "fout", "tekst": e.melding}
            return
        if isinstance(e, kern.NietUitvoerbaar):
            self.melding = {"soort": "info", "tekst": str(e)}
            return
        self.melding = {"soort": "fout", "tekst": str(e) or e.__class__.__name__}

    def _voer_uit(self, naam, werk):
        if self.bezig:
            return
        self.bezig = naam
        self.melding = None
        self.bij_wijziging()
        try:
            werk()
        except Exception as e:  # alles naar de medewerker, nooit stil
            self._fout(e)
        finally:
            self.bezig = None
            self.bij_wijziging()

    # -- document -------------------------------------------------------------------

    def _lees_inhoud(self):
        self.blokken = kern.groepeer(self.document.lees_blokken())
        return kern.als_inhoud(self.blokken)

    def _te_bewaren(self):
        """Het origineel (odt) is de versie; de html gaat mee als weergave (MDTO)."""
        html = self._lees_inhoud()
        return self.document.bestand(), html

    def _lees_afdruk(self):
        w = self.document.lees_eigenschap(AFDRUK)
        if not w:
            return None
        try:
            a = json.loads(w)
            return a if isinstance(a, dict) and a.get("identificatie") else None
        except ValueError:
            return None

    def _schrijf_afdruk(self, obj):
        versies = obj.get("versies") or []
        self.afdruk = {"identificatie": obj["identificatie"], "versie": versies[-1]["nummer"] if versies else 0, "objecttype": obj["objecttype"]["naam"]}
        self.document.schrijf_eigenschap(AFDRUK, json.dumps(self.afdruk))

    def _laad_geschiedenis(self):
        if self.object:
            self.geschiedenis = self.verbinding.gebeurtenissen(self.object["identificatie"]) or []

    # -- acties -------------------------------------------------------------------------

    def start(self):
        """Wie ben ik, welk objecttype, waar staat dit stuk."""
        if not self.sessies.sleutel:
            self._herstel()
            self.bij_wijziging()
            return

        def werk():
            v = self.verbinding
            self.fase = "laden"
            self.wie = v.wie_ben_ik()
            self.type = v.objecttype(OBJECTTYPE)
            self.afdruk = self._lees_afdruk()
            self.object = None
            if self.afdruk:
                try:
                    self.object = v.object(self.afdruk["identificatie"])
                except VerbindingsFout as e:
                    if e.status != 404:
                        raise
                    self.afdruk = None
                    self.melding = {"soort": "info", "tekst": "Dit stuk draagt een identificatie die het platform niet kent (van een andere gemeente of omgeving). Registreer het opnieuw."}
            self.onbereikbaar = False
            self.metadata = {k: ("" if w is None else str(w)) for k, w in ((self.object or {}).get("metadata") or {}).items()}
            self.voorstellen = kern.suggesties(self._lees_inhoud(), self.metadata)
            self._laad_geschiedenis()
            self.fase = "klaar"

        self._voer_uit("starten", werk)

    def zet_veld(self, naam, waarde):
        self.metadata[naam] = waarde
        self.fouten.pop(naam, None)

    def neem_voorstel_over(self, naam):
        if naam in self.voorstellen:
            self.zet_veld(naam, self.voorstellen[naam])
            self.bij_wijziging()

    def registreer(self):
        def werk():
            self.fouten = {}
            inhoud, weergave = self._te_bewaren()
            obj = self.verbinding.maak_object(OBJECTTYPE, kern.opgeschoond(self.metadata), inhoud, weergave)
            self.object = obj
            self._schrijf_afdruk(obj)
            self.metadata = {k: ("" if w is None else str(w)) for k, w in (obj.get("metadata") or {}).items()}
            self.melding = {"soort": "ok", "tekst": "Het stuk is geregistreerd. Het platform heeft het een eigen identificatie gegeven."}
            self._laad_geschiedenis()

        self._voer_uit("registreren", werk)

    def leg_metadata_vast(self):
        def werk():
            self.fouten = {}
            obj = self.verbinding.leg_metadata_vast(self.object["identificatie"], kern.opgeschoond(self.metadata), self.object.get("volgnummer"))
            self.object = obj
            self.melding = {"soort": "ok", "tekst": "De metadata is vastgelegd."}
            self._laad_geschiedenis()

        self._voer_uit("metadata", werk)

    def leg_versie_vast(self):
        def werk():
            voor = len(self.object.get("versies") or [])
            inhoud, weergave = self._te_bewaren()
            obj = self.verbinding.voeg_versie_toe(self.object["identificatie"], inhoud, weergave)
            self.object = obj
            self._schrijf_afdruk(obj)
            versies = obj.get("versies") or []
            if len(versies) > voor:
                self.melding = {"soort": "ok", "tekst": "Versie %d is vastgelegd." % versies[-1]["nummer"]}
            else:
                self.melding = {"soort": "info", "tekst": "De inhoud is niet gewijzigd sinds de vorige versie. Er is geen nieuwe versie gemaakt."}
            self._laad_geschiedenis()

        self._voer_uit("versie", werk)

    def _beoordeel(self):
        r = self.verbinding.toegankelijkheid(self._lees_inhoud())
        self.bevindingen = r.get("bevindingen") or []

    def beoordeel(self):
        def werk():
            self._beoordeel()
            self.antwoorden = {}

        self._voer_uit("beoordelen", werk)

    def herstel(self, bevinding_id):
        b = next((x for x in (self.bevindingen or []) if x["id"] == bevinding_id), None)
        if not b:
            return

        def werk():
            # Vers lezen: de medewerker kan intussen hebben getypt.
            self._lees_inhoud()
            antwoord = self.antwoorden.get(b["id"])
            vraag = (b.get("voorstel") or {}).get("vraag")
            if antwoord is None and vraag and vraag.get("veld") == "alt":
                antwoord = ""  # leeg = decoratieve afbeelding
            opdracht = kern.herstel_opdracht(self.blokken, b, antwoord)
            self.document.voer_uit(opdracht)
            self._beoordeel()
            self.melding = {"soort": "ok", "tekst": "Hersteld in het document."}

        self._voer_uit("herstel-" + bevinding_id, werk)

    def toon(self, bevinding_id):
        b = next((x for x in (self.bevindingen or []) if x["id"] == bevinding_id), None)
        if not b or not b.get("plek"):
            return
        doel = kern.plek_naar_doel(self.blokken, b["plek"]["pad"]) if self.blokken else None
        if not doel:
            self.melding = {"soort": "info", "tekst": "%s: beoordeel eerst opnieuw om de plek te kunnen tonen." % b["plek"]["beschrijving"]}
            self.bij_wijziging()
            return
        try:
            self.document.toon(doel)
            self.melding = None
        except Exception as e:
            self._fout(e)
            self.bij_wijziging()

    def kan_herstellen(self, b):
        v = b.get("voorstel") or {}
        if not b.get("plek") or not (v.get("vervanging") or v.get("vraag")):
            return False
        vraag = v.get("vraag")
        return not (vraag and vraag.get("veld") != "alt" and not self.antwoorden.get(b["id"]))

    def afgemeld(self):
        """De sessie is vervallen of ingetrokken."""
        self._herstel()
        self.bij_wijziging()
