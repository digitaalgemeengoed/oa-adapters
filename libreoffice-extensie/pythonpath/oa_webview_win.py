# -*- coding: utf-8 -*-
"""Het webpaneel in de zijbalk op Windows: WebView2 (de motor van Edge).

WebView2 zit in Windows 10 en 11 (de "Evergreen Runtime"). We laden het met
WebView2Loader.dll uit de extensie (Microsoft, BSD-licentie; zie
webview2/LICENSE.txt) en praten er via COM mee, met ctypes: de Python van
LibreOffice heeft geen extra pakketten. De volgorde van de methoden in de
COM-tabellen komt uit de WebView2-SDK (zoals in go-webview2, MIT).

Alles gebeurt op de hoofdthread van LibreOffice (een STA met een
berichtenlus): de antwoorden van WebView2 komen daar binnen.
"""
import ctypes
import os
import platform
import sys
from ctypes import POINTER, Structure, byref, c_int, c_int64, c_long, c_ulong, c_void_p, c_wchar_p

from oa_webview_eigen import NietBeschikbaar, SysteemWebweergave, log

HRESULT = c_long
# Op 64-bits Windows is er één aanroepconventie; WINFUNCTYPE is er alleen op Windows.
FUNC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

# Plaatsen in de COM-tabellen (0, 1, 2 zijn IUnknown).
_WEBVIEW = [
    "GetSettings", "GetSource", "Navigate", "NavigateToString",
    "AddNavigationStarting", "RemoveNavigationStarting", "AddContentLoading", "RemoveContentLoading",
    "AddSourceChanged", "RemoveSourceChanged", "AddHistoryChanged", "RemoveHistoryChanged",
    "AddNavigationCompleted", "RemoveNavigationCompleted", "AddFrameNavigationStarting", "RemoveFrameNavigationStarting",
    "AddFrameNavigationCompleted", "RemoveFrameNavigationCompleted", "AddScriptDialogOpening", "RemoveScriptDialogOpening",
    "AddPermissionRequested", "RemovePermissionRequested", "AddProcessFailed", "RemoveProcessFailed",
    "AddScriptToExecuteOnDocumentCreated", "RemoveScriptToExecuteOnDocumentCreated", "ExecuteScript", "CapturePreview",
    "Reload", "PostWebMessageAsJSON", "PostWebMessageAsString", "AddWebMessageReceived", "RemoveWebMessageReceived",
    "CallDevToolsProtocolMethod", "GetBrowserProcessID", "GetCanGoBack", "GetCanGoForward", "GoBack", "GoForward",
    "GetDevToolsProtocolEventReceiver", "Stop", "AddNewWindowRequested", "RemoveNewWindowRequested",
]
_CONTROLLER = [
    "GetIsVisible", "PutIsVisible", "GetBounds", "PutBounds", "GetZoomFactor", "PutZoomFactor",
    "AddZoomFactorChanged", "RemoveZoomFactorChanged", "SetBoundsAndZoomFactor", "MoveFocus",
    "AddMoveFocusRequested", "RemoveMoveFocusRequested", "AddGotFocus", "RemoveGotFocus",
    "AddLostFocus", "RemoveLostFocus", "AddAcceleratorKeyPressed", "RemoveAcceleratorKeyPressed",
    "GetParentWindow", "PutParentWindow", "NotifyParentWindowPositionChanged", "Close", "GetCoreWebView2",
]
_SETTINGS = [
    "GetIsScriptEnabled", "PutIsScriptEnabled", "GetIsWebMessageEnabled", "PutIsWebMessageEnabled",
    "GetAreDefaultScriptDialogsEnabled", "PutAreDefaultScriptDialogsEnabled", "GetIsStatusBarEnabled", "PutIsStatusBarEnabled",
    "GetAreDevToolsEnabled", "PutAreDevToolsEnabled",
]
WEBVIEW = {n: i + 3 for i, n in enumerate(_WEBVIEW)}
CONTROLLER = {n: i + 3 for i, n in enumerate(_CONTROLLER)}
SETTINGS = {n: i + 3 for i, n in enumerate(_SETTINGS)}
ENVIRONMENT = {"CreateCoreWebView2Controller": 3}
BERICHT_ARGS = {"GetSource": 3, "GetWebMessageAsJSON": 4, "TryGetWebMessageAsString": 5}
NIEUW_VENSTER_ARGS = {"GetUri": 3, "PutNewWindow": 4, "GetNewWindow": 5, "PutHandled": 6}


class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]


def methode(obj, index, *argtypes, restype=HRESULT):
    """Methode `index` van een COM-object (een pointer naar een pointer naar de tabel)."""
    tabel = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = FUNC(restype, c_void_p, *argtypes)(tabel[index])
    return lambda *a: fn(obj, *a)


class Afhandeling:
    """
    Een COM-object dat WebView2 terugroept (…CompletedHandler, …EventHandler):
    IUnknown plus één methode Invoke. `soort` zijn de argumenttypen van Invoke
    na `this`. De Python-objecten moeten blijven bestaan zolang WebView2 ze
    kan aanroepen; de webweergave bewaart ze.
    """

    def __init__(self, invoke, *soort):
        self._qi = FUNC(HRESULT, c_void_p, c_void_p, POINTER(c_void_p))(self._query)
        self._ref = FUNC(c_ulong, c_void_p)(lambda _this: 1)
        self._inv = FUNC(HRESULT, c_void_p, *soort)(lambda _this, *a: self._roep(invoke, a))
        self._tabel = (c_void_p * 4)(
            ctypes.cast(self._qi, c_void_p), ctypes.cast(self._ref, c_void_p), ctypes.cast(self._ref, c_void_p), ctypes.cast(self._inv, c_void_p)
        )
        self._obj = c_void_p(ctypes.addressof(self._tabel))
        self.ptr = ctypes.addressof(self._obj)

    def _query(self, _this, _iid, uit):
        uit[0] = self.ptr
        return 0

    @staticmethod
    def _roep(invoke, a):
        try:
            invoke(*a)
        except Exception as e:  # nooit een uitzondering terug in WebView2
            log("fout in afhandeling", repr(e))
        return 0


def _laadlader(map_):
    machine = platform.machine().lower()
    soort = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("amd64", "x86_64") else "x86"
    pad = os.path.join(map_, soort, "WebView2Loader.dll")
    try:
        return ctypes.WinDLL(pad)
    except Exception as e:
        raise NietBeschikbaar("WebView2Loader.dll niet te laden (%s): %s" % (pad, e))


class Webweergave(SysteemWebweergave):
    SOORT = "SYSTEM_WIN32"
    LADER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webview2")

    def _start(self, hwnd, breedte, hoogte, adres, opslag):
        if not sys.platform.startswith("win"):
            raise NietBeschikbaar("WebView2 is er alleen op Windows")
        self.hwnd = hwnd
        self.adres = adres
        self.controller = None
        self.web = None
        self._bewaar = []  # afhandelingen die WebView2 nog kan aanroepen
        lader = _laadlader(self.LADER)
        maak = lader.CreateCoreWebView2EnvironmentWithOptions
        maak.restype = HRESULT
        maak.argtypes = [c_wchar_p, c_wchar_p, c_void_p, c_void_p]
        os.makedirs(opslag, exist_ok=True)
        klaar = self._afhandeling(self._omgeving_klaar, HRESULT, c_void_p)
        hr = maak(None, opslag, None, klaar.ptr)
        if hr < 0:
            raise NietBeschikbaar("WebView2 start niet (0x%08x); is de WebView2 Runtime geïnstalleerd?" % (hr & 0xFFFFFFFF))
        log("WebView2: omgeving aangevraagd", opslag)

    def _afhandeling(self, invoke, *soort):
        a = Afhandeling(invoke, *soort)
        self._bewaar.append(a)
        return a

    def _omgeving_klaar(self, hr, omgeving):
        if hr < 0 or not omgeving:
            log("WebView2: geen omgeving", hex(hr & 0xFFFFFFFF))
            return
        methode(omgeving, 1, restype=c_ulong)()  # AddRef
        self.omgeving = omgeving
        klaar = self._afhandeling(self._controller_klaar, HRESULT, c_void_p)
        methode(omgeving, ENVIRONMENT["CreateCoreWebView2Controller"], c_void_p, c_void_p)(self.hwnd, klaar.ptr)

    def _controller_klaar(self, hr, controller):
        if hr < 0 or not controller:
            log("WebView2: geen controller", hex(hr & 0xFFFFFFFF))
            return
        methode(controller, 1, restype=c_ulong)()  # AddRef
        self.controller = controller
        web = c_void_p()
        methode(controller, CONTROLLER["GetCoreWebView2"], POINTER(c_void_p))(byref(web))
        self.web = web.value
        token = c_int64()
        # Instellingen: geen statusbalk, ontwikkelhulp alleen met OA_LOG.
        inst = c_void_p()
        methode(self.web, WEBVIEW["GetSettings"], POINTER(c_void_p))(byref(inst))
        if inst.value:
            methode(inst.value, SETTINGS["PutIsStatusBarEnabled"], c_int)(0)
            methode(inst.value, SETTINGS["PutAreDevToolsEnabled"], c_int)(1 if os.environ.get("OA_LOG") else 0)
        # Het kanaal zoals WebKit het kent, bovenop chrome.webview.
        methode(self.web, WEBVIEW["AddScriptToExecuteOnDocumentCreated"], c_wchar_p, c_void_p)(
            "window.webkit=window.webkit||{};window.webkit.messageHandlers={oaBrug:{postMessage:function(m){window.chrome.webview.postMessage(JSON.stringify(m));}}};",
            None,
        )
        bericht = self._afhandeling(self._bericht, c_void_p, c_void_p)
        methode(self.web, WEBVIEW["AddWebMessageReceived"], c_void_p, POINTER(c_int64))(bericht.ptr, byref(token))
        geladen = self._afhandeling(lambda _s, _a: self.geladen(), c_void_p, c_void_p)
        methode(self.web, WEBVIEW["AddNavigationCompleted"], c_void_p, POINTER(c_int64))(geladen.ptr, byref(token))
        nieuw = self._afhandeling(self._nieuw_venster, c_void_p, c_void_p)
        methode(self.web, WEBVIEW["AddNewWindowRequested"], c_void_p, POINTER(c_int64))(nieuw.ptr, byref(token))
        self._maat(self.breedte, self.hoogte)
        methode(controller, CONTROLLER["PutIsVisible"], c_int)(1)
        methode(self.web, WEBVIEW["Navigate"], c_wchar_p)(self.adres)
        log("WebView2: ingebed", self.breedte, "x", self.hoogte, self.adres.split("#")[0])

    def _tekst(self, args, index):
        p = c_void_p()
        methode(args, index, POINTER(c_void_p))(byref(p))
        if not p.value:
            return ""
        try:
            return ctypes.wstring_at(p.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(p)

    def _bericht(self, _afzender, args):
        self.bericht(self._tekst(args, BERICHT_ARGS["TryGetWebMessageAsString"]), self._tekst(args, BERICHT_ARGS["GetSource"]))

    def _nieuw_venster(self, _afzender, args):
        # target=_blank of window.open: in de gewone browser.
        uri = self._tekst(args, NIEUW_VENSTER_ARGS["GetUri"])
        methode(args, NIEUW_VENSTER_ARGS["PutHandled"], c_int)(1)
        self.extern_openen(uri)

    def _voer_uit(self, script):
        if self.web:
            methode(self.web, WEBVIEW["ExecuteScript"], c_wchar_p, c_void_p)(script, None)

    def stuur(self, opdracht):
        self.wacht = opdracht
        if self.web:
            super().stuur(opdracht)

    def _maat(self, breedte, hoogte):
        if self.controller:
            methode(self.controller, CONTROLLER["PutBounds"], RECT)(RECT(0, 0, breedte, hoogte))

    def _herlaad(self):
        if self.web:
            methode(self.web, WEBVIEW["Reload"])()

    def _weg(self):
        if self.controller:
            try:
                methode(self.controller, CONTROLLER["Close"])()
                methode(self.controller, 2, restype=c_ulong)()  # Release
            except Exception as e:
                log("WebView2 sluiten", e)
            self.controller = None
            self.web = None
