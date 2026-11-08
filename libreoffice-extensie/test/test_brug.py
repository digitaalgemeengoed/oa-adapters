# -*- coding: utf-8 -*-
"""Test de lokale brug (assistent.py) tegen een echte LibreOffice, via http."""
import json, os, sys, unittest, urllib.request, urllib.error

hier = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(hier, "..", "pythonpath"))
sys.path.insert(0, os.path.join(hier, ".."))
sys.path.insert(0, hier)
from test_document import verbind, maak_document
import assistent

HERKOMST = "https://oa.voorbeeld.nl"


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = verbind()
        cls.doc = maak_document(cls.ctx)
        cls.brug = assistent.Brug(cls.ctx, cls.doc, HERKOMST)
        cls.basis = "http://127.0.0.1:%d" % cls.brug.poort

    @classmethod
    def tearDownClass(cls):
        cls.brug.stop()
        cls.doc.close(True)

    def vraag(self, methode, pad, lichaam=None, sleutel=True, herkomst=HERKOMST):
        data = json.dumps(lichaam).encode() if lichaam is not None else None
        r = urllib.request.Request(self.basis + pad, data=data, method=methode)
        if sleutel:
            r.add_header("Authorization", "Bearer " + (self.brug.sleutel if sleutel is True else sleutel))
        if herkomst:
            r.add_header("Origin", herkomst)
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=20) as a:
                return a.status, dict(a.headers), json.loads(a.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), json.loads(e.read() or b"{}")

    def test_paneeladres(self):
        self.assertTrue(self.brug.paneeladres().startswith(HERKOMST + "/libreoffice#brug=%d&sleutel=" % self.brug.poort))

    def test_zonder_of_met_verkeerde_sleutel(self):
        self.assertEqual(self.vraag("GET", "/blokken", sleutel=False)[0], 401)
        self.assertEqual(self.vraag("GET", "/blokken", sleutel="fout")[0], 401)

    def test_andere_site_mag_niet(self):
        self.assertEqual(self.vraag("GET", "/blokken", herkomst="https://kwaadwillend.example")[0], 401)
        r = urllib.request.Request(self.basis + "/blokken", method="OPTIONS")
        r.add_header("Origin", "https://kwaadwillend.example")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(r, timeout=5)
        self.assertEqual(e.exception.code, 403)

    def test_voorvraag_van_het_paneel(self):
        r = urllib.request.Request(self.basis + "/opdracht", method="OPTIONS")
        r.add_header("Origin", HERKOMST)
        r.add_header("Access-Control-Request-Private-Network", "true")
        with urllib.request.urlopen(r, timeout=5) as a:
            self.assertEqual(a.status, 204)
            self.assertEqual(a.headers["Access-Control-Allow-Origin"], HERKOMST)
            self.assertEqual(a.headers["Access-Control-Allow-Private-Network"], "true")

    def test_blokken_opdracht_eigenschap(self):
        s, kop, blokken = self.vraag("GET", "/blokken")
        self.assertEqual(s, 200)
        self.assertEqual(kop["Access-Control-Allow-Origin"], HERKOMST)
        self.assertTrue(any(b.get("tekst") == "Kosten" and b["niveau"] == 4 for b in blokken))
        s, _, _ = self.vraag("POST", "/opdracht", {"soort": "niveau", "alinea": 2, "niveau": 3, "tekst": "Kosten"})
        self.assertEqual(s, 200)
        s, _, f = self.vraag("POST", "/opdracht", {"soort": "niveau", "alinea": 2, "niveau": 3, "tekst": "Anders"})
        self.assertEqual((s, f["fout"]), (409, "gewijzigd"))
        self.assertEqual(self.vraag("PUT", "/eigenschap", {"naam": "oa-afdruk", "waarde": "{\"versie\":1}"})[0], 200)
        self.assertEqual(self.vraag("GET", "/eigenschap?naam=oa-afdruk")[2], {"waarde": "{\"versie\":1}"})
        self.assertEqual(self.vraag("POST", "/toon", {"soort": "alinea", "alinea": 1})[0], 200)
        self.assertEqual(self.vraag("GET", "/onzin")[0], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
