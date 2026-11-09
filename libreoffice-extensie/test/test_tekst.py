# -*- coding: utf-8 -*-
"""Test oa_tekst (vervangen door plaatshouders, selectie lezen) tegen een echte LibreOffice (headless).

    soffice --headless --invisible --accept="socket,host=127.0.0.1,port=2002;urp;" &
    python3 -m pytest test/test_tekst.py
"""
import os
import sys
import unittest

import uno  # noqa: F401  (maakt com.sun.star importeerbaar)
from com.sun.star.awt import Point, Size

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonpath"))
import oa_tekst as ot  # noqa: E402
from test_document import p, verbind  # noqa: E402

PAREN = [
    {"van": "Jan", "naar": "[PERSOON 2]"},
    {"van": "Jan de Vries", "naar": "[PERSOON 1]"},
    {"van": "06-12345678", "naar": "[TELEFOON 1]"},
    {"van": "A&B $1", "naar": "[OVERIG 1] & $0"},
]


class TestTekst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = verbind()
        cls.desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

    def nieuw(self, soort):
        return self.desktop.loadComponentFromURL("private:factory/" + soort, "_blank", 0, (p("Hidden", True),))

    def test_writer(self):
        doc = self.nieuw("swriter")
        try:
            tekst = doc.getText()
            tekst.setString("Jan de Vries belde. Janssen niet, maar Jan wel: 06-12345678. A&B $1.")
            n = ot.vervang_tekst(doc, PAREN)
            self.assertEqual(n, 4)
            self.assertEqual(tekst.getString(), "[PERSOON 1] belde. Janssen niet, maar [PERSOON 2] wel: [TELEFOON 1]. [OVERIG 1] & $0.")
            # selectie
            c = tekst.createTextCursor()
            c.gotoStart(False)
            c.goRight(11, True)
            doc.getCurrentController().select(c)
            self.assertEqual(ot.lees_selectie(doc), "[PERSOON 1]")
        finally:
            doc.close(True)

    def test_calc(self):
        doc = self.nieuw("scalc")
        try:
            bladen = doc.getSheets()
            b0 = bladen.getByIndex(0)
            b0.getCellByPosition(0, 0).setString("Jan de Vries")
            b0.getCellByPosition(1, 0).setString("Janssen")
            b0.getCellByPosition(0, 1).setFormula('="Jan"&" x"')
            bladen.insertNewByName("Tweede", 1)
            bladen.getByName("Tweede").getCellByPosition(2, 2).setString("Bel Jan op 06-12345678")
            n = ot.vervang_tekst(doc, PAREN)
            self.assertGreaterEqual(n, 3)
            self.assertEqual(b0.getCellByPosition(0, 0).getString(), "[PERSOON 1]")
            self.assertEqual(b0.getCellByPosition(1, 0).getString(), "Janssen")
            self.assertEqual(bladen.getByName("Tweede").getCellByPosition(2, 2).getString(), "Bel [PERSOON 2] op [TELEFOON 1]")
            doc.getCurrentController().select(b0.getCellRangeByName("A1:B1"))
            self.assertEqual(ot.lees_selectie(doc), "[PERSOON 1] Janssen")
        finally:
            doc.close(True)

    def test_impress(self):
        doc = self.nieuw("simpress")
        try:
            dia = doc.getDrawPages().getByIndex(0)
            vak = doc.createInstance("com.sun.star.drawing.TextShape")
            dia.add(vak)
            vak.setPosition(Point(1000, 1000))
            vak.setSize(Size(10000, 3000))
            vak.setString("Gesprek met Jan de Vries\nJan belt 06-12345678")
            n = ot.vervang_tekst(doc, PAREN)
            self.assertEqual(n, 3)
            self.assertEqual(vak.getString(), "Gesprek met [PERSOON 1]\n[PERSOON 2] belt [TELEFOON 1]")
        finally:
            doc.close(True)

    def test_backslash(self):
        with self.assertRaises(ot.NietUitvoerbaar):
            ot.icu_vervanging("a\\b")

    def test_orden(self):
        self.assertEqual([v for v, _ in ot.orden(PAREN)][:2], ["Jan de Vries", "06-12345678"])
        self.assertEqual(ot.orden([{"van": " ", "naar": "x"}, {"van": "a", "naar": "a"}]), [])


if __name__ == "__main__":
    unittest.main()
