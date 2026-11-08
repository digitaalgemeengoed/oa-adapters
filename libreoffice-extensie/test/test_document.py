# -*- coding: utf-8 -*-
"""Test oa_document tegen een echte LibreOffice (headless).

    soffice --headless --invisible --accept="socket,host=127.0.0.1,port=2002;urp;" &
    python3 test/test_document.py
"""
import os, sys, time, json, unittest
import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK
from com.sun.star.text.TextContentAnchorType import AS_CHARACTER

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonpath"))
import oa_document as od

PAD_BEELD = os.path.join(os.path.dirname(__file__), "beeld.png")


def verbind():
    lokaal = uno.getComponentContext()
    resolver = lokaal.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", lokaal)
    for _ in range(40):
        try:
            return resolver.resolve("uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext")
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("LibreOffice niet bereikbaar")


def p(naam, waarde):
    x = PropertyValue(); x.Name = naam; x.Value = waarde; return x


def maak_document(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (p("Hidden", True),))
    t = doc.getText(); c = t.createTextCursor()

    def alinea(tekst, stijl="Standard", vet=False, onder=False, lijst=""):
        c.ParaStyleName = stijl
        c.NumberingStyleName = lijst
        c.CharWeight = 150 if vet else 100
        c.CharUnderline = 1 if onder else 0
        t.insertString(c, tekst, False)
        t.insertControlCharacter(c, PARAGRAPH_BREAK, False)
        c.CharWeight = 100; c.CharUnderline = 0

    alinea("Raadsvoorstel fietsenstalling", vet=True)               # 0
    alinea("Aanleiding", "Heading 2")                               # 1
    alinea("Kosten", "Heading 4")                                   # 2
    # 3: alinea met link en afbeelding
    c.ParaStyleName = "Standard"
    t.insertString(c, "Zie de begroting, ", False)
    t.insertString(c, "klik hier", False)
    c.goLeft(len("klik hier"), True)
    c.HyperLinkURL = "https://example.org/begroting"
    c.collapseToEnd()
    c.HyperLinkURL = ""
    t.insertString(c, " voor meer. ", False)
    beeld = doc.createInstance("com.sun.star.text.TextGraphicObject")
    beeld.GraphicURL = uno.systemPathToFileUrl(PAD_BEELD) if False else ""
    gp = ctx.ServiceManager.createInstanceWithContext("com.sun.star.graphic.GraphicProvider", ctx)
    beeld.Graphic = gp.queryGraphic((p("URL", uno.systemPathToFileUrl(PAD_BEELD)),))
    beeld.AnchorType = AS_CHARACTER
    t.insertTextContent(c, beeld, False)
    t.insertControlCharacter(c, PARAGRAPH_BREAK, False)
    alinea("Eerste punt", lijst="List 1")                            # 4
    alinea("Tweede punt", lijst="List 1")                            # 5
    alinea("Onderstreept stuk", onder=True)                         # 6
    tabel = doc.createInstance("com.sun.star.text.TextTable")
    tabel.initialize(2, 2)
    t.insertTextContent(c, tabel, False)
    tabel.HeaderRowCount = 0
    tabel.RepeatHeadline = False
    for naam, waarde in (("A1", "Post"), ("B1", "Bedrag"), ("A2", "Bouw"), ("B2", "120.000")):
        tabel.getCellByName(naam).setString(waarde)
    return doc


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = verbind()
        cls.doc = maak_document(cls.ctx)

    @classmethod
    def tearDownClass(cls):
        cls.doc.close(True)

    def test_1_lezen(self):
        r = od.lees_blokken(self.doc)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        tekst = {x.get("tekst"): x for x in r if "tekst" in x}
        self.assertEqual(tekst["Raadsvoorstel fietsenstalling"]["vet"], True)
        self.assertEqual(tekst["Aanleiding"]["niveau"], 2)
        self.assertEqual(tekst["Kosten"]["niveau"], 4)
        links = tekst["Zie de begroting, klik hier voor meer."]["inline"]
        self.assertEqual(links[0], {"soort": "link", "tekst": "klik hier", "href": "https://example.org/begroting", "index": 0})
        self.assertEqual(links[1]["soort"], "afbeelding")
        self.assertEqual(tekst["Onderstreept stuk"]["onderstreept"], True)
        tabel = [x for x in r if x.get("soort") == "tabel"][0]
        self.assertEqual(tabel["rijen"], [["Post", "Bedrag"], ["Bouw", "120.000"]])
        self.assertEqual(tabel["kopregels"], 0)

    def test_2_opdrachten(self):
        od.voer_uit(self.doc, {"soort": "niveau", "alinea": 0, "niveau": 1, "tekst": "Raadsvoorstel fietsenstalling"})
        od.voer_uit(self.doc, {"soort": "niveau", "alinea": 2, "niveau": 3, "tekst": "Kosten"})
        od.voer_uit(self.doc, {"soort": "tabelkop", "tabel": 0})
        od.voer_uit(self.doc, {"soort": "alt", "alinea": 3, "afbeelding": 0, "alt": "Plattegrond van de stalling", "tekst": "Zie de begroting, klik hier voor meer."})
        od.voer_uit(self.doc, {"soort": "linktekst", "alinea": 3, "link": 0, "tekst": "Begroting 2027", "href": "https://example.org/begroting", "alineatekst": "Zie de begroting, klik hier voor meer."})
        r = od.lees_blokken(self.doc)
        tekst = {x.get("tekst"): x for x in r if "tekst" in x}
        self.assertEqual(tekst["Raadsvoorstel fietsenstalling"]["niveau"], 1)
        self.assertEqual(tekst["Kosten"]["niveau"], 3)
        a = tekst["Zie de begroting, Begroting 2027 voor meer."]["inline"]
        self.assertEqual(a[0], {"soort": "link", "tekst": "Begroting 2027", "href": "https://example.org/begroting", "index": 0})
        self.assertEqual(a[1]["alt"], "Plattegrond van de stalling")
        self.assertEqual([x for x in r if x.get("soort") == "tabel"][0]["kopregels"], 1)

    def test_3_gewijzigd(self):
        with self.assertRaises(od.Gewijzigd):
            od.voer_uit(self.doc, {"soort": "niveau", "alinea": 1, "niveau": 1, "tekst": "Andere tekst"})

    def test_4_eigenschap(self):
        self.assertIsNone(od.lees_eigenschap(self.doc, "oa-afdruk"))
        od.schrijf_eigenschap(self.doc, "oa-afdruk", '{"identificatie":"x","versie":1}')
        od.schrijf_eigenschap(self.doc, "oa-afdruk", '{"identificatie":"x","versie":2}')
        self.assertEqual(od.lees_eigenschap(self.doc, "oa-afdruk"), '{"identificatie":"x","versie":2}')

    def test_5_vervang_alles(self):
        od.vervang_alles(self.doc, "<h1>Nieuw</h1><p>Tekst met <a href='https://x'>link</a></p>")
        r = od.lees_blokken(self.doc)
        self.assertEqual(r[0]["niveau"], 1)
        self.assertEqual(r[0]["tekst"], "Nieuw")
        self.assertTrue(r[1]["inline"][0]["href"].startswith("https://x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
