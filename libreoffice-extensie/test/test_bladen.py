# -*- coding: utf-8 -*-
"""Test oa_bladen (Calc en Impress) tegen een echte LibreOffice (headless), met de regels van oa-services.

    soffice --headless --invisible --accept="socket,host=127.0.0.1,port=2002;urp;" &
    python3 -m pytest test/test_bladen.py
"""
import json
import os
import subprocess
import sys
import unittest

import uno
from com.sun.star.awt import Point, Size

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonpath"))
import oa_bladen as ob  # noqa: E402
from oa_kern import NietUitvoerbaar, herstel_opdracht  # noqa: E402,F401
from test_document import PAD_BEELD, p, verbind  # noqa: E402

SERVICES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "oa-services"))


def beoordeel(html):
    """De echte regels uit oa-services (gebouwd in dist/)."""
    code = "import('%s/dist/toegankelijkheid.js').then(m => process.stdout.write(JSON.stringify(m.beoordeelHtml(require('fs').readFileSync(0, 'utf8')))))" % SERVICES
    uit = subprocess.run(["node", "-e", code], input=html, capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


def beeld(doc, pagina):
    ctx = verbind()
    gp = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
    pagina.add(gp)
    provider = ctx.ServiceManager.createInstanceWithContext("com.sun.star.graphic.GraphicProvider", ctx)
    gp.Graphic = provider.queryGraphic((p("URL", uno.systemPathToFileUrl(PAD_BEELD)),))
    gp.setPosition(Point(1000, 6000))
    gp.setSize(Size(4000, 3000))
    return gp


class Rekenblad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = verbind()
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        cls.doc = desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, (p("Hidden", True),))
        bladen = cls.doc.getSheets()
        blad = bladen.getByIndex(0)
        blad.setName("Blad1")
        for r, rij in enumerate([("Post", "Bedrag"), ("Bouw", 1250000), ("Beheer", 45000)]):
            for k, w in enumerate(rij):
                cel = blad.getCellByPosition(k, r)
                cel.setValue(w) if isinstance(w, (int, float)) else cel.setString(w)
        bladen.insertNewByName("Toelichting", 1)
        beeld(cls.doc, blad.getDrawPage())

    @classmethod
    def tearDownClass(cls):
        cls.doc.close(True)

    def test_1_lezen_en_regels(self):
        self.assertEqual(ob.soort_van(self.doc), "rekenblad")
        html = ob.html(self.doc)
        self.assertIn('<section data-oa="blad"><h2>Blad1</h2><table><tbody><tr><td>Post</td><td>Bedrag</td></tr><tr><td>Bouw</td><td>1250000</td></tr>', html)
        self.assertIn("<img>", html)
        self.assertIn('<section data-oa="blad"><h2>Toelichting</h2></section>', html)
        regels = sorted((b["regel"], b["plek"]["pad"]) for b in beoordeel(html))
        self.assertEqual(regels, [("WCAG 2.2 1.1.1", "body/0/2"), ("WCAG 2.2 2.4.6", "body/0/0")])

    def test_2_herstellen(self):
        bevindingen = {b["plek"]["pad"]: b for b in beoordeel(ob.html(self.doc))}
        kaart = ob.lees(self.doc)[1]
        # Naam van het blad: vraag "tekst" op de kop.
        ob.vervang_segment(self.doc, "body/0/0", "<h2>Begroting 2027</h2>")
        self.assertEqual(self.doc.getSheets().getByIndex(0).getName(), "Begroting 2027")
        with self.assertRaises(NietUitvoerbaar):
            ob.vervang_segment(self.doc, "body/0/0", "<h2>Toelichting</h2>")
        with self.assertRaises(NietUitvoerbaar):
            ob.vervang_segment(self.doc, "body/0/0", "<h2>Kosten: bouw</h2>")
        # Alternatieve tekst bij de afbeelding.
        self.assertIn("body/0/2", bevindingen)
        ob.vervang_segment(self.doc, "body/0/2", '<img alt="Kaart van het Stationsplein">')
        self.assertEqual(self.doc.getSheets().getByIndex(0).getDrawPage().getByIndex(0).Title, "Kaart van het Stationsplein")
        self.assertEqual(beoordeel(ob.html(self.doc)), [])
        self.assertEqual(len(kaart), 2)

    def test_3_tonen_en_bestand(self):
        ob.toon(self.doc, "body/1")
        import oa_document as od
        b = od.bestand(self.doc)
        self.assertEqual((b["formaat"], b["mediaType"]), ("ods", "application/vnd.oasis.opendocument.spreadsheet"))


class Presentatie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = verbind()
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        cls.doc = desktop.loadComponentFromURL("private:factory/simpress", "_blank", 0, (p("Hidden", True),))
        dias = cls.doc.getDrawPages()
        d1 = dias.getByIndex(0)
        d1.Layout = 1  # titel en inhoud
        cls.vul(d1, "Fietsenstalling", "Waarom\nWat het kost")
        d2 = dias.insertNewByIndex(0)
        d2.Layout = 20  # leeg: geen titelvak
        beeld(cls.doc, d2)
        d3 = dias.insertNewByIndex(1)
        d3.Layout = 1
        cls.vul(d3, "fietsenstalling", "Planning")

    @staticmethod
    def vul(dia, titel, tekst):
        for i in range(dia.getCount()):
            v = dia.getByIndex(i)
            if v.getShapeType() == "com.sun.star.presentation.TitleTextShape":
                v.setString(titel)
            elif v.getShapeType() == "com.sun.star.presentation.OutlinerShape":
                v.setString(tekst)

    @classmethod
    def tearDownClass(cls):
        cls.doc.close(True)

    def test_1_lezen_en_regels(self):
        self.assertEqual(ob.soort_van(self.doc), "presentatie")
        html = ob.html(self.doc)
        self.assertTrue(html.startswith('<section data-oa="dia"><h2>Fietsenstalling</h2><ul><li>Waarom</li><li>Wat het kost</li></ul></section>'), html)
        regels = sorted((b["regel"], b["plek"]["pad"], b["ernst"]) for b in beoordeel(html))
        self.assertEqual(regels, [("WCAG 2.2 1.1.1", "body/1/0", "fout"), ("WCAG 2.2 2.4.2", "body/1", "fout"), ("WCAG 2.2 2.4.6", "body/2/0", "advies")])

    def test_2_herstellen(self):
        bevindingen = beoordeel(ob.html(self.doc))
        zonder = next(b for b in bevindingen if b["regel"] == "WCAG 2.2 2.4.2")
        # Zoals in het paneel: de vraag "titel" wordt een attribuut op de sectie (oa-kern, pasToe).
        ob.vervang_segment(self.doc, zonder["plek"]["pad"], '<section data-oa="dia" titel="Situatie ter plaatse"><img></section>')
        ob.vervang_segment(self.doc, "body/2/0", "<h2>Fietsenstalling: planning</h2>")
        html = ob.html(self.doc)
        self.assertIn('<section data-oa="dia"><h2>Situatie ter plaatse</h2><img></section>', html)
        alt = next(b for b in beoordeel(html) if b["regel"] == "WCAG 2.2 1.1.1")
        ob.vervang_segment(self.doc, alt["plek"]["pad"], '<img alt="Foto van de fietsen">')
        self.assertEqual(beoordeel(ob.html(self.doc)), [])

    def test_3_tonen_en_bestand(self):
        ob.toon(self.doc, "body/1/0")
        import oa_document as od
        self.assertEqual(od.bestand(self.doc)["formaat"], "odp")


if __name__ == "__main__":
    unittest.main()
