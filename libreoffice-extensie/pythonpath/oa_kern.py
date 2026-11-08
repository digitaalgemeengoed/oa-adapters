# -*- coding: utf-8 -*-
"""De assistentkern voor het zijpaneel in LibreOffice, in Python.

Dezelfde regels als in TypeScript, zodat het zijpaneel precies doet wat het
paneel in de browser doet:

- oa-kern/src/metadateren.ts: velden uit het schema, voorstellen uit de
  inhoud, ontbrekende verplichte velden;
- oa-kern/src/toegankelijkheid.ts: welke wijziging een voorstel inhoudt;
- oa-adapters/src/semantisch.ts: blokken naar html, en een hersteld deel
  terug naar een opdracht voor Writer.

test/test_kern.py vergelijkt de uitkomsten met de TypeScript-versie op
dezelfde voorbeelden. Wijzig je hier iets, wijzig het daar ook.

Geen UNO: deze module is zonder LibreOffice te testen.
"""

import re
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Metadateren (oa-kern/src/metadateren.ts)
# ---------------------------------------------------------------------------


def velden(objecttype):
    """De invoervelden van een objecttype: verplichte eerst, in de volgorde van het schema."""
    schema = objecttype.get("schema") or {}
    verplicht = set(schema.get("required") or [])
    lijst = []
    for naam, e in (schema.get("properties") or {}).items():
        if e.get("enum"):
            soort = "keuze"
        elif (e.get("maxLength") or 0) > 400:
            soort = "lange-tekst"
        else:
            soort = "tekst"
        lijst.append({
            "naam": naam,
            "label": e.get("title") or naam,
            "beschrijving": e.get("description"),
            "soort": soort,
            "verplicht": naam in verplicht,
            "opties": e.get("enum"),
            "maxLengte": e.get("maxLength"),
            "standaard": e.get("default"),
        })
    return [v for v in lijst if v["verplicht"]] + [v for v in lijst if not v["verplicht"]]


_H1 = re.compile(r"<h1[^>]*>([\s\S]*?)</h1>", re.I)
_DIATITEL = re.compile(r'^\s*<section data-oa="dia"><h2[^>]*>([\s\S]*?)</h2>', re.I)


def suggesties(inhoud, huidig):
    """Voorstellen uit de inhoud. De medewerker beslist; een voorstel wordt nooit vanzelf vastgelegd."""
    s = {}
    if inhoud.get("formaat") == "html" and not huidig.get("naam"):
        # De eerste kop 1; in een presentatie de titel van de eerste dia.
        m = _H1.search(inhoud.get("data") or "") or _DIATITEL.search(inhoud.get("data") or "")
        if m:
            titel = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
            if len(titel) >= 3:
                s["naam"] = titel[:200]
    if not huidig.get("taal"):
        s["taal"] = "nl"
    return s


def ontbrekend(objecttype, metadata):
    """Ontbrekende verplichte velden, als bevindingen."""
    return [
        {
            "id": "md-" + v["naam"],
            "module": "metadateren",
            "ernst": "fout",
            "regel": "MDTO " + v["naam"],
            "melding": "%s is nog niet ingevuld." % v["label"],
        }
        for v in velden(objecttype)
        if v["verplicht"] and metadata.get(v["naam"]) in (None, "")
    ]


def opgeschoond(metadata):
    """Alleen ingevulde waarden; lege velden gaan niet als lege tekst naar het platform."""
    return {k: w for k, w in metadata.items() if w not in (None, "")}


# ---------------------------------------------------------------------------
# Blokken naar html (oa-adapters/src/semantisch.ts)
# ---------------------------------------------------------------------------


def groepeer(reeks):
    """Losse alinea's uit Writer; opeenvolgende lijstitems worden één lijst."""
    blokken = []
    for a in reeks:
        if a.get("soort") == "tabel":
            blokken.append(a)
            continue
        alinea = {k: w for k, w in a.items() if k != "lijst"}
        alinea["soort"] = "alinea"
        lijst = a.get("lijst")
        if lijst:
            vorige = blokken[-1] if blokken else None
            if vorige and vorige["soort"] == "lijst" and vorige["genummerd"] == lijst["genummerd"]:
                vorige["items"].append(alinea)
            else:
                blokken.append({"soort": "lijst", "genummerd": lijst["genummerd"], "items": [alinea]})
        else:
            blokken.append(alinea)
    return blokken


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s):
    return _esc(s).replace('"', "&quot;")


def _plaats_links(a):
    links = [i for i in (a.get("inline") or []) if i["soort"] == "link"]
    tekst = a["tekst"]
    kandidaten = sorted(
        ((link, tekst.find(link["tekst"]) if link["tekst"] else -1) for link in links),
        key=lambda k: (k[1], k[0]["index"]),
    )
    geplaatst, los, cursor = [], [], 0
    for link, _ in kandidaten:
        begin = tekst.find(link["tekst"], cursor) if link["tekst"] else -1
        if begin >= 0:
            geplaatst.append((link, begin))
            cursor = begin + len(link["tekst"])
        else:
            los.append(link)
    return geplaatst, los


def _inhoud(a):
    inline = a.get("inline") or []
    geplaatst, los = _plaats_links(a)
    html, cursor, tekst = "", 0, a["tekst"]
    for link, begin in geplaatst:
        html += _esc(tekst[cursor:begin]) + '<a href="%s">%s</a>' % (_esc_attr(link["href"]), _esc(link["tekst"]))
        cursor = begin + len(link["tekst"])
    html += _esc(tekst[cursor:])
    html += "".join('<a href="%s">%s</a>' % (_esc_attr(l["href"]), _esc(l["tekst"])) for l in los)
    html += "".join(('<img alt="%s">' % _esc_attr(i["alt"])) if i["alt"] else "<img>" for i in inline if i["soort"] == "afbeelding")
    if not inline and a["niveau"] == 0:
        if a.get("vet"):
            return "<strong>%s</strong>" % html
        if a.get("onderstreept"):
            return "<u>%s</u>" % html
    return html


def inline_volgorde(a):
    geplaatst, los = _plaats_links(a)
    return [l for l, _ in geplaatst] + los + [i for i in (a.get("inline") or []) if i["soort"] == "afbeelding"]


def _alinea_html(a):
    tag = "h%d" % min(a["niveau"], 6) if a["niveau"] > 0 else "p"
    return "<%s>%s</%s>" % (tag, _inhoud(a), tag)


def _tabel_html(t):
    rijen = []
    for i, rij in enumerate(t["rijen"]):
        cel = "th" if i < t["kopregels"] else "td"
        rijen.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (cel, _esc(c), cel) for c in rij))
    kop, romp = rijen[: t["kopregels"]], rijen[t["kopregels"]:]
    return "<table>%s<tbody>%s</tbody></table>" % ("<thead>%s</thead>" % "".join(kop) if kop else "", "".join(romp))


def naar_html(blokken):
    delen = []
    for b in blokken:
        if b["soort"] == "alinea":
            delen.append(_alinea_html(b))
        elif b["soort"] == "tabel":
            delen.append(_tabel_html(b))
        else:
            tag = "ol" if b["genummerd"] else "ul"
            delen.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _inhoud(i) for i in b["items"]), tag))
    return "\n".join(delen)


def als_inhoud(blokken):
    return {"formaat": "html", "mediaType": "text/html", "codering": "tekst", "data": naar_html(blokken)}


# ---------------------------------------------------------------------------
# Terug: een herstelling wordt een opdracht voor Writer
# ---------------------------------------------------------------------------


class NietUitvoerbaar(Exception):
    """Deze wijziging kan de assistent in Writer niet zelf doen."""


HANDMATIG = "Deze wijziging kan in deze tekstverwerker nog niet automatisch. Pas het met de hand aan."
NIET_GEVONDEN = "Dit deel van het document is niet meer gevonden. Beoordeel opnieuw."


class _Element(HTMLParser):
    """Het eerste element van een stuk html: tag, attributen, tekst en of er een th in staat."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag, self.attrs, self.tekst, self.diepte, self.th = None, {}, "", 0, False

    def handle_starttag(self, tag, attrs):
        if self.tag is None:
            self.tag, self.attrs = tag, dict(attrs)
            if tag not in ("img", "br", "hr", "input"):
                self.diepte = 1
            return
        if self.diepte > 0:
            if tag == "th":
                self.th = True
            if tag not in ("img", "br", "hr", "input"):
                self.diepte += 1

    def handle_endtag(self, tag):
        if self.diepte > 0:
            self.diepte -= 1

    def handle_data(self, data):
        if self.diepte > 0:
            self.tekst += data


def eerste_element(html):
    p = _Element()
    p.feed(html)
    p.close()
    return p


def pad_delen(pad):
    d = pad.split("/")
    if d[0] != "body":
        raise NietUitvoerbaar("Onbekend pad: %s" % pad)
    return [int(x) for x in d[1:]]


def _alinea_en_index(blok, j, k):
    if blok["soort"] == "alinea":
        return blok, j
    if blok["soort"] == "lijst" and k is not None and j < len(blok["items"]):
        return blok["items"][j], k
    return None, None


def segment_naar_opdracht(blokken, pad, html):
    """Het herstelde element op `pad` als één opdracht voor Writer."""
    delen = pad_delen(pad) + [None, None]
    i, j, k = delen[0], delen[1], delen[2]
    if i >= len(blokken):
        raise NietUitvoerbaar(NIET_GEVONDEN)
    blok = blokken[i]
    el = eerste_element(html)
    if el.tag is None:
        raise NietUitvoerbaar("De wijziging is leeg.")
    tag = el.tag
    if j is None:
        if blok["soort"] == "alinea" and re.match(r"^(h[1-6]|p)$", tag):
            return {"soort": "niveau", "alinea": blok["bron"], "niveau": 0 if tag == "p" else int(tag[1]), "tekst": blok["tekst"]}
        if blok["soort"] == "tabel" and tag == "table" and el.th:
            return {"soort": "tabelkop", "tabel": blok["bron"]}
        raise NietUitvoerbaar(HANDMATIG)
    alinea, index = _alinea_en_index(blok, j, k)
    if alinea is None:
        raise NietUitvoerbaar(HANDMATIG)
    volgorde = inline_volgorde(alinea)
    if index >= len(volgorde):
        raise NietUitvoerbaar(NIET_GEVONDEN)
    doel = volgorde[index]
    if doel["soort"] == "afbeelding" and tag == "img":
        return {"soort": "alt", "alinea": alinea["bron"], "afbeelding": doel["index"], "alt": el.attrs.get("alt") or "", "tekst": alinea["tekst"]}
    if doel["soort"] == "link" and tag == "a":
        return {"soort": "linktekst", "alinea": alinea["bron"], "link": doel["index"], "tekst": el.tekst, "href": doel["href"], "alineatekst": alinea["tekst"]}
    raise NietUitvoerbaar(HANDMATIG)


def plek_naar_doel(blokken, pad):
    """Waar een plek in Writer staat, om hem te tonen."""
    delen = pad_delen(pad) + [None, None]
    i, j, k = delen[0], delen[1], delen[2]
    if i >= len(blokken):
        return None
    blok = blokken[i]
    if blok["soort"] == "tabel":
        return {"soort": "tabel", "tabel": blok["bron"]}
    if blok["soort"] == "alinea":
        alinea, idx = blok, j
    else:
        n = j or 0
        alinea = blok["items"][n] if n < len(blok["items"]) else None
        idx = k
    if alinea is None:
        return None
    if idx is None:
        return {"soort": "alinea", "alinea": alinea["bron"]}
    volgorde = inline_volgorde(alinea)
    if idx >= len(volgorde):
        return {"soort": "alinea", "alinea": alinea["bron"]}
    doel = volgorde[idx]
    if doel["soort"] == "afbeelding":
        return {"soort": "afbeelding", "alinea": alinea["bron"], "afbeelding": doel["index"]}
    return {"soort": "link", "alinea": alinea["bron"], "link": doel["index"]}


# ---------------------------------------------------------------------------
# Herstellen (oa-kern/src/toegankelijkheid.ts)
# ---------------------------------------------------------------------------


def wijziging_voor(bevinding, antwoord=None):
    """Wat een voorstel concreet wijzigt, met het antwoord van de medewerker als het een vraag stelt."""
    v = bevinding.get("voorstel")
    if not v:
        return None
    if v.get("vervanging"):
        return {"soort": "vervang", "html": v["vervanging"]}
    vraag = v.get("vraag")
    if vraag and antwoord is not None:
        if vraag["veld"] == "tekst":
            return {"soort": "tekst", "waarde": antwoord}
        return {"soort": "attribuut", "naam": vraag["veld"], "waarde": antwoord}
    return None


def _tag_op_pad(blokken, pad):
    """De tag van het element op een pad, zoals naar_html het maakt."""
    delen = pad_delen(pad) + [None, None]
    i, j, k = delen[0], delen[1], delen[2]
    if i >= len(blokken):
        raise NietUitvoerbaar(NIET_GEVONDEN)
    blok = blokken[i]
    if j is None:
        if blok["soort"] == "alinea":
            return "h%d" % min(blok["niveau"], 6) if blok["niveau"] > 0 else "p"
        return "table" if blok["soort"] == "tabel" else ("ol" if blok["genummerd"] else "ul")
    alinea, index = _alinea_en_index(blok, j, k)
    if alinea is None:
        raise NietUitvoerbaar(HANDMATIG)
    volgorde = inline_volgorde(alinea)
    if index >= len(volgorde):
        raise NietUitvoerbaar(NIET_GEVONDEN)
    return "img" if volgorde[index]["soort"] == "afbeelding" else "a"


def herstel_opdracht(blokken, bevinding, antwoord=None):
    """
    De opdracht voor Writer die één bevinding herstelt. Zelfde uitkomst als
    pasToe + segmentNaarOpdracht in TypeScript, zonder html-boom: voor een
    vraag (alt, linktekst) is alleen de tag van het element en het antwoord nodig.
    """
    w = wijziging_voor(bevinding, antwoord)
    plek = bevinding.get("plek")
    if not w or not plek:
        raise NietUitvoerbaar("Deze bevinding kan de assistent niet zelf herstellen.")
    pad = plek["pad"]
    if w["soort"] == "vervang":
        return segment_naar_opdracht(blokken, pad, w["html"])
    tag = _tag_op_pad(blokken, pad)
    if w["soort"] == "attribuut":
        html = "<%s %s=\"%s\">" % (tag, w["naam"], _esc_attr(w["waarde"])) if tag == "img" else "<%s %s=\"%s\"></%s>" % (tag, w["naam"], _esc_attr(w["waarde"]), tag)
    else:
        html = "<%s></%s>" % (tag, tag) if tag == "img" else "<%s>%s</%s>" % (tag, _esc(w["waarde"]), tag)
    return segment_naar_opdracht(blokken, pad, html)


# ---------------------------------------------------------------------------
# Weergave
# ---------------------------------------------------------------------------


def bestandsomschrijving(versie):
    """"odt, 24 kB, met html-weergave": wat er van een versie is bewaard."""
    kb = max(1, int((versie.get("grootte") or 0) / 1024 + 0.5))  # zoals Math.round
    weergaven = [w["formaat"] for w in (versie.get("weergaven") or [])]
    return "%s, %d kB%s" % (versie.get("formaat"), kb, (", met %s-weergave" % " en ".join(weergaven)) if weergaven else "")
