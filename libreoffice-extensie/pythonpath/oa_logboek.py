# -*- coding: utf-8 -*-
"""Een klein logboek voor testers (Office Assistent → Logboek openen).

Altijd aan, maar beperkt: hoogstens 512 kB, daarna begint het opnieuw (het
vorige blijft als logboek.vorig.txt). Er staan geen documentinhoud en geen
sleutels in, alleen wat de extensie doet en wat er misgaat. OA_LOG=<bestand>
schrijft (ook) naar dat bestand, zoals voorheen.
"""
import os
import sys
import threading
import time

_slot = threading.Lock()
MAX = 512 * 1024


def map_():
    if sys.platform.startswith("win"):
        basis = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(basis, "office-assistent")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "office-assistent")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "office-assistent")


def pad():
    return os.path.join(map_(), "logboek.txt")


def log(bron, *a):
    regel = "%s %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), bron, " ".join(str(x) for x in a))
    with _slot:
        for p in filter(None, (os.environ.get("OA_LOG"), pad())):
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                if p == pad() and os.path.exists(p) and os.path.getsize(p) > MAX:
                    os.replace(p, p[:-4] + ".vorig.txt")
                with open(p, "a", encoding="utf-8") as f:
                    f.write(regel)
            except OSError:
                pass


def kop():
    """Eén regel over de omgeving, bij het begin van een paneel."""
    import platform
    try:
        import uno  # noqa: F401
        lo = "uno"
    except Exception:
        lo = "?"
    return "systeem=%s %s machine=%s python=%s %s" % (sys.platform, platform.release(), platform.machine(), platform.python_version(), lo)
