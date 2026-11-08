"""Aanmelden via de lokale server, en de verbinding met een nepintegratielaag."""
import json
import os
import sys
import threading
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "pythonpath"))
from oa_verbinding import Aanmelder, Verbinding, VerbindingsFout  # noqa: E402

HERKOMST = "https://oa.test"
# Rechtstreeks naar 127.0.0.1, nooit via een proxy uit de omgeving.
ZONDER_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(poort, sleutel, lichaam, herkomst=HERKOMST):
    r = urllib.request.Request("http://127.0.0.1:%d/sessie" % poort, data=json.dumps(lichaam).encode(), method="POST",
                               headers={"Origin": herkomst, "Authorization": "Bearer " + sleutel, "Content-Type": "application/json"})
    try:
        with ZONDER_PROXY.open(r, timeout=5) as a:
            return a.status
    except urllib.error.HTTPError as e:
        return e.code


class AanmeldenTest(unittest.TestCase):
    def test_alleen_met_herkomst_en_sleutel_en_een_keer(self):
        ontvangen = []
        a = Aanmelder(HERKOMST, ontvangen.append)
        self.assertIn("/libreoffice#aanmelden=%d&sleutel=" % a.poort, a.adres())
        self.assertEqual(post(a.poort, a.sleutel, {"sessie": "s" * 40}, "https://kwaad.example"), 403)
        self.assertEqual(post(a.poort, "fout", {"sessie": "s" * 40}), 403)
        self.assertEqual(post(a.poort, a.sleutel, {"sessie": "kort"}), 400)
        self.assertEqual(post(a.poort, a.sleutel, {"sessie": "s" * 40}), 200)
        self.assertEqual(ontvangen, ["s" * 40])


class Nep(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer goed" or self.headers.get("x-oa-verzoek") != "1":
            data = b'{"fout":"niet-ingelogd","melding":"Log eerst in."}'
            self.send_response(401)
        else:
            data = json.dumps({"naam": "Femke", "pad": self.path}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class VerbindingTest(unittest.TestCase):
    def test_kop_fouten_en_onbereikbaar(self):
        s = ThreadingHTTPServer(("127.0.0.1", 0), Nep)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        basis = "http://127.0.0.1:%d" % s.server_address[1]
        aanroepen = []
        v = Verbinding(basis, "goed", open_url=lambda r, t: ZONDER_PROXY.open(r, timeout=t), bij_aanroep=lambda *a: aanroepen.append(a))
        self.assertEqual(v.object("a/b c")["pad"], "/api/lees/objecten/a%2Fb%20c")
        self.assertEqual(aanroepen[-1][2], 200)
        with self.assertRaises(VerbindingsFout) as f:
            Verbinding(basis, "fout", open_url=lambda r, t: ZONDER_PROXY.open(r, timeout=t)).wie_ben_ik()
        self.assertTrue(f.exception.niet_ingelogd)
        s.shutdown()
        s.server_close()
        with self.assertRaises(VerbindingsFout) as f:
            Verbinding(basis, "goed", tijd=2, open_url=lambda r, t: ZONDER_PROXY.open(r, timeout=t)).wie_ben_ik()
        self.assertTrue(f.exception.niet_bereikbaar)


if __name__ == "__main__":
    unittest.main()
