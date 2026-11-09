# -*- coding: utf-8 -*-
"""Test oa_pii (plaatshouders met bladwijzers in Writer) tegen een echte LibreOffice (headless)."""
import os
import sys
import unittest

import uno  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonpath"))
import oa_pii as op  # noqa: E402
from test_document import p, verbind  # noqa: E402


class TestPii(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = verbind()
        cls.desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

    def test_markeren_herstellen_definitief(self):
        doc = self.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (p("Hidden", True),))
        try:
            t = doc.getText()
            t.setString("Jan de Vries belde Jan. Janssen niet. Mantelzorg voor Jan.")
            nieuw = op.markeer(doc, [
                {"van": "Jan", "plaatshouder": "[PERSOON 2]", "ppl": 1, "voorvertoning": True},
                {"van": "Jan de Vries", "plaatshouder": "[PERSOON 1]", "ppl": 1, "voorvertoning": True},
                {"van": "Mantelzorg", "plaatshouder": "[GEZONDHEID 1]", "ppl": 2, "voorvertoning": True},
            ])
            self.assertEqual([x["plaatshouder"] for x in nieuw], ["[PERSOON 1]", "[GEZONDHEID 1]", "[PERSOON 2]", "[PERSOON 2]"])
            self.assertEqual(t.getString(), "[PERSOON 1] belde [PERSOON 2]. Janssen niet. [GEZONDHEID 1] voor [PERSOON 2].")
            plekken = op.lees_plekken(doc)
            self.assertEqual([x["plaatshouder"] for x in plekken], ["[PERSOON 1]", "[PERSOON 2]", "[GEZONDHEID 1]", "[PERSOON 2]"])
            self.assertTrue(all(x["voorvertoning"] for x in plekken))
            # kleur van art. 9
            bw = doc.getBookmarks().getByName("oa-pii %s [GEZONDHEID 1] v" % plekken[2]["plek"])
            self.assertEqual(bw.getAnchor().CharBackColor, op.ACHTERGROND[2])
            # één plek terug
            op.herstel(doc, [{"plek": plekken[3]["plek"], "waarde": "Jan"}])
            self.assertEqual(t.getString(), "[PERSOON 1] belde [PERSOON 2]. Janssen niet. [GEZONDHEID 1] voor Jan.")
            self.assertEqual(len(op.lees_plekken(doc)), 3)
            # klik: cursor in een plaatshouder
            c = doc.getCurrentController()
            klik = op.Klikken(doc)
            c.select(doc.getBookmarks().getByName("oa-pii %s [PERSOON 2] v" % plekken[1]["plek"]).getAnchor())
            self.assertEqual(op.plek_bij_cursor(doc)["plek"], plekken[1]["plek"])
            self.assertEqual(klik.stand()["plek"], plekken[1]["plek"])
            # een cursor direct na een plaatshouder is geen klik; binnenin wel
            vc = c.getViewCursor()
            vc.gotoRange(doc.getBookmarks().getByName("oa-pii %s [PERSOON 1] v" % plekken[0]["plek"]).getAnchor().getEnd(), False)
            self.assertIsNone(op.plek_bij_cursor(doc))
            vc.goLeft(2, False)
            self.assertEqual(op.plek_bij_cursor(doc)["plaatshouder"], "[PERSOON 1]")
            op.zet_definitief(doc)
            self.assertFalse(any(x["voorvertoning"] for x in op.lees_plekken(doc)))
            # opnieuw markeren raakt bestaande plaatshouders niet
            op.markeer(doc, [{"van": "Janssen", "plaatshouder": "[PERSOON 3]", "ppl": 1, "voorvertoning": True}])
            self.assertEqual(t.getString(), "[PERSOON 1] belde [PERSOON 2]. [PERSOON 3] niet. [GEZONDHEID 1] voor Jan.")
        finally:
            doc.close(True)


if __name__ == "__main__":
    unittest.main()
