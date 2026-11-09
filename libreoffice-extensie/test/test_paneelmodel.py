"""Het model van het zijpaneel, met een nepdocument en een nepverbinding."""
import copy
import json
import os
import sys
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "pythonpath"))
import oa_paneelmodel as pm  # noqa: E402
from oa_verbinding import VerbindingsFout  # noqa: E402

TYPE = {"naam": "document", "schema": {"required": ["naam"], "properties": {"naam": {"title": "Naam"}, "taal": {"title": "Taal"}}}}


class NepDocument:
    def __init__(self):
        self.reeks = [
            {"bron": 0, "niveau": 1, "tekst": "Besluit", "inline": [], "lijst": None},
            {"bron": 1, "niveau": 0, "tekst": "Inleiding", "vet": True, "inline": [], "lijst": None},
            {"bron": 2, "niveau": 0, "tekst": "Plaatje", "inline": [{"soort": "afbeelding", "alt": "", "index": 0}], "lijst": None},
        ]
        self.eigenschappen = {}
        self.opdrachten = []
        self.getoond = []

    def lees_blokken(self):
        return copy.deepcopy(self.reeks)

    def bestand(self):
        return {"formaat": "odt", "mediaType": "application/vnd.oasis.opendocument.text", "codering": "base64", "data": "UEs="}

    def bestand_ooxml(self):
        return {"formaat": "docx", "mediaType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "codering": "base64", "data": "UEs="}

    def voer_uit(self, o):
        self.opdrachten.append(o)
        if o["soort"] == "niveau":
            self.reeks[o["alinea"]]["niveau"] = o["niveau"]

    def toon(self, doel):
        self.getoond.append(doel)

    def lees_eigenschap(self, naam):
        return self.eigenschappen.get(naam)

    def schrijf_eigenschap(self, naam, waarde):
        self.eigenschappen[naam] = waarde


class NepVerbinding:
    def __init__(self, server):
        self.s = server

    def wie_ben_ik(self):
        if self.s.weg:
            raise VerbindingsFout(0, "niet-bereikbaar", "weg")
        if self.s.uitgelogd:
            raise VerbindingsFout(401, "niet-ingelogd", "Log eerst in.")
        return {"naam": "Femke", "gemeente": "haarlem", "rollen": ["medewerker"], "sub": "x"}

    def objecttype(self, naam, versie=None):
        return TYPE

    def object(self, i):
        if i not in self.s.objecten:
            raise VerbindingsFout(404, "niet-gevonden", "Onbekend")
        return self.s.objecten[i]

    def gebeurtenissen(self, i):
        return [{"type": "geregistreerd", "tijdstip": "2026-11-08T20:00:00Z", "actor": {"naam": "Femke"}}]

    def toegankelijkheid(self, inhoud, taal=None, bestand=None):
        self.s.beoordeeld.append(inhoud["data"])
        self.s.bestanden = getattr(self.s, "bestanden", []) + [bestand]
        b = []
        if "<strong>Inleiding</strong>" in inhoud["data"]:
            b.append({"id": "kop", "module": "toegankelijkheid", "ernst": "waarschuwing", "regel": "WCAG 1.3.1", "melding": "Vet als kop", "plek": {"pad": "body/1", "beschrijving": "alinea 2"}, "voorstel": {"vervanging": "<h2>Inleiding</h2>"}})
        b.append({"id": "alt", "module": "toegankelijkheid", "ernst": "fout", "regel": "WCAG 1.1.1", "melding": "Geen alt", "plek": {"pad": "body/2/0", "beschrijving": "afbeelding"}, "voorstel": {"vraag": {"veld": "alt", "label": "Alt"}}})
        return {"bevindingen": b, "gecontroleerd": []}

    def maak_object(self, t, md, inhoud, weergave=None):
        self.s.bewaard.append((inhoud["formaat"], weergave and weergave["formaat"]))
        if not md.get("naam"):
            raise VerbindingsFout(422, "metadata-ongeldig", "Ongeldig", [{"veld": "naam", "melding": "Verplicht"}])
        o = {"identificatie": "abc-123", "objecttype": {"naam": t}, "metadata": md, "versies": [{"nummer": 1, "formaat": "odt", "grootte": 2000}], "volgnummer": 1, "volledigheid": {"volledig": True, "ontbreekt": []}}
        self.s.objecten["abc-123"] = o
        return o

    def leg_metadata_vast(self, i, md, verwacht=None):
        o = dict(self.s.objecten[i], metadata=md, volgnummer=self.s.objecten[i]["volgnummer"] + 1)
        self.s.objecten[i] = o
        return o

    def voeg_versie_toe(self, i, inhoud, weergave=None):
        o = self.s.objecten[i]
        if not self.s.gelijk:
            o = dict(o, versies=o["versies"] + [{"nummer": len(o["versies"]) + 1, "formaat": "odt", "grootte": 2100}])
        self.s.objecten[i] = o
        return o


class Server:
    def __init__(self):
        self.weg = False
        self.uitgelogd = False
        self.gelijk = False
        self.objecten = {}
        self.beoordeeld = []
        self.bewaard = []


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.doc = NepDocument()
        self.sessies = pm.Sessies()
        self.wijzigingen = 0
        self.m = pm.Model(self.doc, "https://oa.test", self.sessies, lambda s: NepVerbinding(self.server), self._gewijzigd)

    def _gewijzigd(self):
        self.wijzigingen += 1

    def test_zonder_sessie_eerst_aanmelden(self):
        self.m.start()
        self.assertEqual(self.m.fase, "aanmelden")

    def test_registreren_metadata_versie(self):
        self.sessies.zet("sessie-1234")
        self.m.start()
        self.assertEqual(self.m.fase, "klaar")
        self.assertEqual(self.m.voorstellen, {"naam": "Besluit", "taal": "nl"})
        self.assertEqual([b["id"] for b in self.m.ontbreekt], ["md-naam"])
        # Zonder naam: de fout komt bij het veld.
        self.m.registreer()
        self.assertEqual(self.m.fouten, {"naam": "Verplicht"})
        self.m.neem_voorstel_over("naam")
        self.m.registreer()
        self.assertTrue(self.m.geregistreerd)
        self.assertEqual(self.server.bewaard[-1], ("odt", "html"), "origineel als versie, html als weergave")
        self.assertEqual(json.loads(self.doc.eigenschappen["oa-afdruk"])["identificatie"], "abc-123")
        self.assertEqual(self.m.melding["soort"], "ok")
        self.m.zet_veld("taal", "en")
        self.m.leg_metadata_vast()
        self.assertEqual(self.server.objecten["abc-123"]["metadata"]["taal"], "en")
        self.m.leg_versie_vast()
        self.assertEqual(self.m.melding["tekst"], "Versie 2 is vastgelegd.")
        self.server.gelijk = True
        self.m.leg_versie_vast()
        self.assertIn("niet gewijzigd", self.m.melding["tekst"])
        # Heropenen: de afdruk in het bestand wijst naar het object.
        m2 = pm.Model(self.doc, "https://oa.test", self.sessies, lambda s: NepVerbinding(self.server))
        m2.start()
        self.assertEqual(m2.object["identificatie"], "abc-123")
        self.assertEqual(m2.metadata["taal"], "en")

    def test_beoordelen_herstellen_tonen(self):
        self.sessies.zet("sessie-1234")
        self.m.start()
        self.m.beoordeel()
        self.assertEqual([b["id"] for b in self.m.bevindingen], ["kop", "alt"])
        self.assertEqual(self.server.bestanden[-1]["formaat"], "docx", "het bestand gaat als docx mee naar de controle")
        self.m.toon("alt")
        self.assertEqual(self.doc.getoond, [{"soort": "afbeelding", "alinea": 2, "afbeelding": 0}])
        self.m.herstel("kop")
        self.assertEqual(self.doc.opdrachten[-1], {"soort": "niveau", "alinea": 1, "niveau": 2, "tekst": "Inleiding"})
        self.assertEqual([b["id"] for b in self.m.bevindingen], ["alt"], "opnieuw beoordeeld")
        self.assertTrue(self.m.kan_herstellen(self.m.bevindingen[0]), "alt mag leeg (decoratief)")
        self.m.antwoorden["alt"] = "Plattegrond"
        self.m.herstel("alt")
        self.assertEqual(self.doc.opdrachten[-1]["alt"], "Plattegrond")

    def test_server_weg_en_uitgelogd(self):
        self.sessies.zet("sessie-1234")
        self.server.weg = True
        self.m.start()
        self.assertTrue(self.m.onbereikbaar)
        self.assertEqual(self.m.melding["soort"], "waarschuwing")
        self.server.weg = False
        self.server.uitgelogd = True
        self.m.start()
        self.assertEqual(self.m.fase, "aanmelden")
        self.assertIsNone(self.sessies.sleutel)

    def test_onbekende_afdruk(self):
        self.sessies.zet("sessie-1234")
        self.doc.eigenschappen["oa-afdruk"] = json.dumps({"identificatie": "elders", "versie": 1, "objecttype": "document"})
        self.m.start()
        self.assertIsNone(self.m.object)
        self.assertIn("identificatie die het platform niet kent", self.m.melding["tekst"])


if __name__ == "__main__":
    unittest.main()
