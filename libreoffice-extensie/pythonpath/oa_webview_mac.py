# -*- coding: utf-8 -*-
"""Het webpaneel in de zijbalk op macOS: WKWebView (de motor van Safari).

macOS kan een venster van een ander programma niet in de zijbalk hangen;
de webweergave moet in LibreOffice zelf ontstaan. De Python van LibreOffice
heeft geen PyObjC, dus praten we met ctypes rechtstreeks met de runtime van
Objective-C (objc_msgSend). Het berichtkanaal is dat van WebKit zelf
(window.webkit.messageHandlers.oaBrug), net als op Linux.

Alles gebeurt op de hoofdthread (de AppKit-thread, waar LibreOffice op
macOS zijn lus draait).
"""
import ctypes
import ctypes.util
import sys
from ctypes import Structure, c_bool, c_char_p, c_double, c_ulong, c_void_p

from oa_webview_eigen import NietBeschikbaar, SysteemWebweergave, log

_objc = None
_klasse = None
_afhandelaars = {}  # objectadres → Webweergave


class CGRect(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("w", c_double), ("h", c_double)]


def _laad():
    global _objc
    if _objc is not None:
        return _objc
    if sys.platform != "darwin":
        raise NietBeschikbaar("WKWebView is er alleen op macOS")
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/WebKit.framework/WebKit")
    except OSError as e:
        raise NietBeschikbaar("WebKit is niet te laden: %s" % e)
    for naam, res, args in (
        ("objc_getClass", c_void_p, [c_char_p]),
        ("objc_getProtocol", c_void_p, [c_char_p]),
        ("sel_registerName", c_void_p, [c_char_p]),
        ("objc_allocateClassPair", c_void_p, [c_void_p, c_char_p, ctypes.c_size_t]),
        ("objc_registerClassPair", None, [c_void_p]),
        ("class_addMethod", c_bool, [c_void_p, c_void_p, c_void_p, c_char_p]),
        ("class_addProtocol", c_bool, [c_void_p, c_void_p]),
    ):
        f = getattr(objc, naam)
        f.restype, f.argtypes = res, args
    _objc = objc
    return objc


def cls(naam):
    c = _laad().objc_getClass(naam.encode())
    if not c:
        raise NietBeschikbaar("klasse %s ontbreekt" % naam)
    return c


def sel(naam):
    return _laad().sel_registerName(naam.encode())


def stuur(obj, selector, *args, restype=c_void_p, argtypes=()):
    """[obj selector:args…] met de juiste typen (op arm64 verplicht: objc_msgSend is niet variadisch)."""
    adres = ctypes.cast(_laad().objc_msgSend, c_void_p).value
    fn = ctypes.CFUNCTYPE(restype, c_void_p, c_void_p, *argtypes)(adres)
    return fn(obj, sel(selector), *args)


def nsstring(tekst):
    return stuur(cls("NSString"), "stringWithUTF8String:", tekst.encode("utf-8"), argtypes=(c_char_p,))


def pytekst(nsstr):
    if not nsstr:
        return ""
    p = stuur(nsstr, "UTF8String", restype=c_char_p)
    return p.decode("utf-8", "replace") if p else ""


def _json_van(obj):
    """Een object uit JavaScript (NSDictionary …) als JSON-tekst."""
    data = stuur(cls("NSJSONSerialization"), "dataWithJSONObject:options:error:", obj, 0, None, argtypes=(c_void_p, c_ulong, c_void_p))
    if not data:
        return pytekst(stuur(obj, "description"))
    lengte = stuur(data, "length", restype=c_ulong)
    p = stuur(data, "bytes")
    return ctypes.string_at(p, lengte).decode("utf-8", "replace")


# Methoden van onze eigen klasse (afhandelaar voor berichten, navigatie en nieuwe vensters).
_IMP_BERICHT = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p, c_void_p)
_IMP_GELADEN = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p, c_void_p)
_IMP_NIEUW = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p)


def _bij_bericht(this, _sel, _ucc, bericht):
    w = _afhandelaars.get(this)
    if w is None:
        return
    try:
        lichaam = stuur(bericht, "body")
        uri = pytekst(stuur(stuur(w.web, "URL"), "absoluteString")) if w.web else ""
        w.bericht(_json_van(lichaam), uri)
    except Exception as e:
        log("WKWebView: bericht", repr(e))


def _bij_geladen(this, _sel, _web, _navigatie):
    w = _afhandelaars.get(this)
    if w is not None:
        w.geladen()


def _bij_nieuw(this, _sel, _web, _config, actie, _kenmerken):
    w = _afhandelaars.get(this)
    try:
        url = pytekst(stuur(stuur(stuur(actie, "request"), "URL"), "absoluteString"))
        if w is not None and url:
            w.extern_openen(url)
    except Exception as e:
        log("WKWebView: nieuw venster", repr(e))
    return None  # geen nieuwe webweergave: de gewone browser opent het


_imps = (_IMP_BERICHT(_bij_bericht), _IMP_GELADEN(_bij_geladen), _IMP_NIEUW(_bij_nieuw))


def _afhandelklasse():
    global _klasse
    if _klasse:
        return _klasse
    objc = _laad()
    k = objc.objc_getClass(b"OAWebweergaveAfhandeling")
    if not k:
        k = objc.objc_allocateClassPair(cls("NSObject"), b"OAWebweergaveAfhandeling", 0)
        objc.class_addMethod(k, sel("userContentController:didReceiveScriptMessage:"), ctypes.cast(_imps[0], c_void_p), b"v@:@@")
        objc.class_addMethod(k, sel("webView:didFinishNavigation:"), ctypes.cast(_imps[1], c_void_p), b"v@:@@")
        objc.class_addMethod(k, sel("webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:"), ctypes.cast(_imps[2], c_void_p), b"@@:@@@@")
        for p in (b"WKScriptMessageHandler", b"WKNavigationDelegate", b"WKUIDelegate"):
            proto = objc.objc_getProtocol(p)
            if proto:
                objc.class_addProtocol(k, proto)
        objc.objc_registerClassPair(k)
    _klasse = k
    return k


class Webweergave(SysteemWebweergave):
    SOORT = "SYSTEM_MAC"

    def _start(self, nsview, breedte, hoogte, adres, opslag):
        self.web = None
        k = _afhandelklasse()
        self.afhandeling = stuur(stuur(k, "alloc"), "init")
        _afhandelaars[self.afhandeling] = self
        config = stuur(stuur(cls("WKWebViewConfiguration"), "alloc"), "init")
        ucc = stuur(config, "userContentController")
        stuur(ucc, "addScriptMessageHandler:name:", self.afhandeling, nsstring("oaBrug"), restype=None, argtypes=(c_void_p, c_void_p))
        web = stuur(stuur(cls("WKWebView"), "alloc"), "initWithFrame:configuration:", CGRect(0, 0, breedte, hoogte), config, argtypes=(CGRect, c_void_p))
        if not web:
            raise NietBeschikbaar("WKWebView is niet te maken")
        self.web = web
        stuur(web, "setNavigationDelegate:", self.afhandeling, restype=None, argtypes=(c_void_p,))
        stuur(web, "setUIDelegate:", self.afhandeling, restype=None, argtypes=(c_void_p,))
        stuur(web, "setAutoresizingMask:", 18, restype=None, argtypes=(c_ulong,))  # breedte en hoogte volgen het paneel
        stuur(nsview, "addSubview:", web, restype=None, argtypes=(c_void_p,))
        url = stuur(cls("NSURL"), "URLWithString:", nsstring(adres), argtypes=(c_void_p,))
        verzoek = stuur(cls("NSURLRequest"), "requestWithURL:", url, argtypes=(c_void_p,))
        stuur(web, "loadRequest:", verzoek, argtypes=(c_void_p,))
        log("WKWebView: ingebed", breedte, "x", hoogte, adres.split("#")[0])

    def _voer_uit(self, script):
        if self.web:
            stuur(self.web, "evaluateJavaScript:completionHandler:", nsstring(script), None, restype=None, argtypes=(c_void_p, c_void_p))

    def _maat(self, breedte, hoogte):
        if self.web:
            stuur(self.web, "setFrame:", CGRect(0, 0, breedte, hoogte), restype=None, argtypes=(CGRect,))

    def _herlaad(self):
        if self.web:
            stuur(self.web, "reload")

    def _weg(self):
        if self.web:
            try:
                stuur(self.web, "removeFromSuperview", restype=None)
            except Exception as e:
                log("WKWebView weg", e)
        _afhandelaars.pop(getattr(self, "afhandeling", None), None)
        self.web = None


# Ongebruikt maar handig bij het zoeken naar fouten (logboek): de versie van macOS.
def systeemversie():
    try:
        info = stuur(cls("NSProcessInfo"), "processInfo")
        return pytekst(stuur(info, "operatingSystemVersionString"))
    except Exception:
        return "?"

