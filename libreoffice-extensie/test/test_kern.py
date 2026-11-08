"""De Python-kern tegen de TypeScript-kern, op dezelfde voorbeelden (kruis.json)."""
import json
import os
import subprocess
import sys
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "pythonpath"))
import oa_kern as k  # noqa: E402

ADAPTERS = os.path.normpath(os.path.join(HIER, "..", ".."))


def zonder_none(x):
    """TypeScript laat undefined weg in JSON; Python schrijft None."""
    if isinstance(x, dict):
        return {a: zonder_none(b) for a, b in x.items() if b is not None}
    if isinstance(x, list):
        return [zonder_none(b) for b in x]
    return x


class Kruistest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = json.load(open(os.path.join(HIER, "kruis.json"), encoding="utf-8"))
        uit = subprocess.run(["node", "--import", "tsx", os.path.join(HIER, "kruis.ts")], cwd=ADAPTERS, capture_output=True, text=True, check=True)
        cls.ts = json.loads(uit.stdout)
        cls.blokken = k.groepeer(cls.f["reeks"])

    def probeer(self, fn):
        try:
            return fn()
        except k.NietUitvoerbaar as e:
            return {"fout": str(e)}

    def test_html(self):
        self.assertEqual(k.naar_html(self.blokken), self.ts["html"])

    def test_segmenten(self):
        py = [self.probeer(lambda p=p, h=h: k.segment_naar_opdracht(self.blokken, p, h)) for p, h in self.f["segmenten"]]
        self.assertEqual(py, self.ts["segmenten"])

    def test_doelen(self):
        self.assertEqual([k.plek_naar_doel(self.blokken, p) for p in self.f["doelen"]], self.ts["doelen"])

    def test_herstel(self):
        py = [self.probeer(lambda b=b, a=a: k.herstel_opdracht(self.blokken, b, a)) for b, a in self.f["bevindingen"]]
        self.assertEqual(py, self.ts["herstel"])

    def test_metadateren(self):
        self.assertEqual(zonder_none(k.velden(self.f["objecttype"])), self.ts["velden"])
        self.assertEqual(k.ontbrekend(self.f["objecttype"], self.f["metadata"]), self.ts["ontbrekend"])
        self.assertEqual(k.suggesties(self.f["inhoud"], self.f["metadata"]), self.ts["suggesties"])
        self.assertEqual([k.suggesties(i, {}) for i in self.f["inhouden"]], self.ts["meerSuggesties"])
        self.assertEqual(self.ts["meerSuggesties"][0]["naam"], "Fietsenstalling Stationsplein")

    def test_omschrijving(self):
        self.assertEqual(k.bestandsomschrijving({"formaat": "odt", "grootte": 24 * 1024 + 512, "weergaven": [{"formaat": "html"}]}), "odt, 25 kB, met html-weergave")
        self.assertEqual(k.opgeschoond({"a": "", "b": None, "c": "x"}), {"c": "x"})


if __name__ == "__main__":
    unittest.main()
