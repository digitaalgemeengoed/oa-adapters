# -*- coding: utf-8 -*-
"""Wat van het webpaneel voor Windows en macOS hier (Linux) te toetsen is:
de COM-objecten van oa_webview_win (indeling van de tabellen, terugroepen),
en het berichtkanaal van oa_webview_eigen (alleen eigen pagina, met sleutel).
De webweergaven zelf toetst alleen een echte Windows of Mac (zie TESTEN.md)."""
import ctypes
import json
import os
import sys
import threading
import unittest
from ctypes import POINTER, byref, c_int, c_long, c_void_p

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pythonpath"))
import uno  # noqa: F401,E402
import oa_webview_win as ww  # noqa: E402
from oa_webview_eigen import SysteemWebweergave  # noqa: E402


class TestCom(unittest.TestCase):
    def test_afhandeling_is_een_com_object(self):
        gezien = []
        a = ww.Afhandeling(lambda hr, obj: gezien.append((hr, obj)), c_long, c_void_p)
        tabel = ctypes.cast(a.ptr, POINTER(POINTER(c_void_p)))[0]
        invoke = ww.FUNC(c_long, c_void_p, c_long, c_void_p)(tabel[3])
        self.assertEqual(invoke(a.ptr, -5, 1234), 0)
        self.assertEqual(gezien, [(-5, 1234)])
        uit = c_void_p()
        qi = ww.FUNC(c_long, c_void_p, c_void_p, POINTER(c_void_p))(tabel[0])
        self.assertEqual(qi(a.ptr, None, byref(uit)), 0)
        self.assertEqual(uit.value, a.ptr)
        # Een fout in Python gaat niet terug naar WebView2.
        b = ww.Afhandeling(lambda: 1 / 0)
        self.assertEqual(ww.FUNC(c_long, c_void_p)(ctypes.cast(b.ptr, POINTER(POINTER(c_void_p)))[0][3])(b.ptr), 0)

    def test_methode_roept_de_juiste_plaats_aan(self):
        gezien = []
        fns = [ww.FUNC(c_long, c_void_p, c_int)(lambda this, x, i=i: gezien.append((i, x)) or 0) for i in range(6)]
        tabel = (c_void_p * 6)(*[ctypes.cast(f, c_void_p) for f in fns])
        obj = c_void_p(ctypes.addressof(tabel))
        ww.methode(ctypes.addressof(obj), 4, c_int)(42)
        self.assertEqual(gezien, [(4, 42)])

    def test_plaatsen(self):
        # Uit de WebView2-SDK: deze vaste plaatsen gebruikt de code.
        self.assertEqual(ww.WEBVIEW["Navigate"], 5)
        self.assertEqual(ww.WEBVIEW["AddNavigationCompleted"], 15)
        self.assertEqual(ww.WEBVIEW["AddScriptToExecuteOnDocumentCreated"], 27)
        self.assertEqual(ww.WEBVIEW["ExecuteScript"], 29)
        self.assertEqual(ww.WEBVIEW["Reload"], 31)
        self.assertEqual(ww.WEBVIEW["AddWebMessageReceived"], 34)
        self.assertEqual(ww.WEBVIEW["AddNewWindowRequested"], 44)
        self.assertEqual(ww.CONTROLLER["PutBounds"], 6)
        self.assertEqual(ww.CONTROLLER["Close"], 24)
        self.assertEqual(ww.CONTROLLER["GetCoreWebView2"], 25)
        self.assertEqual(ww.SETTINGS["PutAreDevToolsEnabled"], 12)


class NepBrug:
    sleutel = "geheim"

    def antwoord(self, methode, pad, lichaam):
        return 200, {"pad": pad}


class NepWeergave(SysteemWebweergave):
    def __init__(self):  # zonder systeemvenster
        self.brug, self.herkomst, self.wacht = NepBrug(), "https://oa.haarlem.dev", None
        self.uitgevoerd = []
        self.klaar = threading.Event()
        self.later = lambda f: f()

    def _voer_uit(self, script):
        self.uitgevoerd.append(script)
        self.klaar.set()


class TestKanaal(unittest.TestCase):
    def test_alleen_eigen_pagina_met_sleutel(self):
        w = NepWeergave()
        w.bericht(json.dumps({"id": 7, "sleutel": "geheim", "methode": "GET", "pad": "/status"}), "https://oa.haarlem.dev/libreoffice#brug=1")
        self.assertTrue(w.klaar.wait(5))
        self.assertIn("__oaBrugAntwoord(7, ", w.uitgevoerd[0])
        self.assertIn('"/status"', w.uitgevoerd[0])
        w2 = NepWeergave()
        w2.bericht(json.dumps({"id": 1, "sleutel": "geheim"}), "https://kwaad.example/")
        w2.bericht(json.dumps({"id": 2, "sleutel": "fout"}), "https://oa.haarlem.dev/libreoffice")
        self.assertFalse(w2.klaar.wait(0.5))

    def test_opdracht_na_laden(self):
        w = NepWeergave()
        w.stuur("anon-selectie")
        w.geladen()
        self.assertEqual(len(w.uitgevoerd), 2)
        self.assertIn('"anon-selectie"', w.uitgevoerd[1])


if __name__ == "__main__":
    unittest.main()
