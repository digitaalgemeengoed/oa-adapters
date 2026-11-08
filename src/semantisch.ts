/**
 * Van de structuur van een tekstverwerker naar semantische html, en terug.
 *
 * Word en LibreOffice beschrijven een document als alinea's met een stijl,
 * lijsten, tabellen, afbeeldingen en links. De assistent werkt met html. De
 * adapter zet de structuur om naar "blokken" (een kale beschrijving, zonder
 * Office.js of UNO); deze module maakt daar html van, en vertaalt een
 * hersteld html-segment terug naar een opdracht die de adapter in de
 * tekstverwerker uitvoert. Zo delen de Word-adapter en de LibreOffice-
 * adapter dezelfde logica, en is die zonder tekstverwerker te testen.
 *
 * Het pad van een plek ("body/3/1") telt elementen: blok 3, daarbinnen het
 * tweede element (een link of afbeelding). Elk blok is precies één element
 * op het hoogste niveau.
 */

export interface Afbeelding {
  soort: "afbeelding";
  alt: string;
  /** Volgnummer van de afbeelding binnen de alinea. */
  index: number;
}

export interface Link {
  soort: "link";
  tekst: string;
  href: string;
  /** Volgnummer van de link binnen de alinea. */
  index: number;
}

export type Inline = Afbeelding | Link;

export interface Alinea {
  soort: "alinea";
  /** Index van de alinea in de tekstverwerker. */
  bron: number;
  /** 0 = gewone alinea, 1–6 = kop. */
  niveau: number;
  tekst: string;
  /** De hele alinea vet (en geen kop): vaak een kop die geen kop is. */
  vet?: boolean;
  /** De hele alinea onderstreept. */
  onderstreept?: boolean;
  inline?: Inline[];
}

export interface Lijst {
  soort: "lijst";
  genummerd: boolean;
  items: Alinea[];
}

export interface Tabel {
  soort: "tabel";
  /** Index van de tabel in de tekstverwerker. */
  bron: number;
  rijen: string[][];
  /** Aantal rijen dat als kopregel is gemarkeerd. */
  kopregels: number;
}

export type Blok = Alinea | Lijst | Tabel;

/** Losse alinea's uit de tekstverwerker; opeenvolgende lijstitems worden één lijst. */
export interface RuweAlinea extends Omit<Alinea, "soort"> {
  lijst?: { genummerd: boolean } | null;
}

export function groepeer(alineas: (RuweAlinea | Tabel)[]): Blok[] {
  const blokken: Blok[] = [];
  for (const a of alineas) {
    if ("soort" in a && a.soort === "tabel") {
      blokken.push(a);
      continue;
    }
    const r = a as RuweAlinea;
    const { lijst, ...rest } = r;
    const alinea: Alinea = { soort: "alinea", ...rest };
    if (lijst) {
      const vorige = blokken.at(-1);
      if (vorige?.soort === "lijst" && vorige.genummerd === lijst.genummerd) vorige.items.push(alinea);
      else blokken.push({ soort: "lijst", genummerd: lijst.genummerd, items: [alinea] });
    } else {
      blokken.push(alinea);
    }
  }
  return blokken;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const escAttr = (s: string) => esc(s).replace(/"/g, "&quot;");

/**
 * Waar de links in de tekst staan: van links naar rechts, zonder overlap.
 * Een link waarvan de tekst niet (meer) in de alinea staat, komt achteraan.
 */
function plaatsLinks(a: Alinea): { geplaatst: { link: Link; begin: number }[]; los: Link[] } {
  const links = (a.inline ?? []).filter((i): i is Link => i.soort === "link");
  const kandidaten = links
    .map((link) => ({ link, begin: link.tekst ? a.tekst.indexOf(link.tekst) : -1 }))
    .sort((x, y) => x.begin - y.begin || x.link.index - y.link.index);
  const geplaatst: { link: Link; begin: number }[] = [];
  const los: Link[] = [];
  let cursor = 0;
  for (const k of kandidaten) {
    const begin = k.link.tekst ? a.tekst.indexOf(k.link.tekst, cursor) : -1;
    if (begin >= 0) {
      geplaatst.push({ link: k.link, begin });
      cursor = begin + k.link.tekst.length;
    } else los.push(k.link);
  }
  return { geplaatst, los };
}

function inhoudVan(a: Alinea): string {
  const inline = a.inline ?? [];
  const { geplaatst, los } = plaatsLinks(a);
  let html = "";
  let cursor = 0;
  for (const { link, begin } of geplaatst) {
    html += esc(a.tekst.slice(cursor, begin)) + `<a href="${escAttr(link.href)}">${esc(link.tekst)}</a>`;
    cursor = begin + link.tekst.length;
  }
  html += esc(a.tekst.slice(cursor));
  html += los.map((l) => `<a href="${escAttr(l.href)}">${esc(l.tekst)}</a>`).join("");
  // Afbeeldingen hebben hier geen tekstpositie; ze komen achteraan, na de links.
  html += inline.filter((i): i is Afbeelding => i.soort === "afbeelding").map((i) => (i.alt ? `<img alt="${escAttr(i.alt)}">` : "<img>")).join("");
  if (inline.length === 0 && a.niveau === 0) {
    if (a.vet) return `<strong>${html}</strong>`;
    if (a.onderstreept) return `<u>${html}</u>`;
  }
  return html;
}

/**
 * Volgorde van de inline-elementen zoals ze in de html staan: links in
 * tekstvolgorde, losse links, daarna afbeeldingen. Nodig om "body/i/j" te vertalen.
 */
export function inlineVolgorde(a: Alinea): Inline[] {
  const { geplaatst, los } = plaatsLinks(a);
  return [...geplaatst.map((g) => g.link), ...los, ...(a.inline ?? []).filter((i) => i.soort === "afbeelding")];
}

function alineaHtml(a: Alinea, tag?: string): string {
  const t = tag ?? (a.niveau > 0 ? `h${Math.min(a.niveau, 6)}` : "p");
  return `<${t}>${inhoudVan(a)}</${t}>`;
}

function tabelHtml(t: Tabel): string {
  const rijen = t.rijen.map((rij, i) => {
    const cel = i < t.kopregels ? "th" : "td";
    return `<tr>${rij.map((c) => `<${cel}>${esc(c)}</${cel}>`).join("")}</tr>`;
  });
  const kop = rijen.slice(0, t.kopregels);
  const romp = rijen.slice(t.kopregels);
  return `<table>${kop.length ? `<thead>${kop.join("")}</thead>` : ""}<tbody>${romp.join("")}</tbody></table>`;
}

export function naarHtml(blokken: Blok[]): string {
  return blokken
    .map((b) => {
      if (b.soort === "alinea") return alineaHtml(b);
      if (b.soort === "tabel") return tabelHtml(b);
      const tag = b.genummerd ? "ol" : "ul";
      return `<${tag}>${b.items.map((i) => `<li>${inhoudVan(i)}</li>`).join("")}</${tag}>`;
    })
    .join("\n");
}

// ---------------------------------------------------------------------------
// Terug: een hersteld segment wordt een opdracht voor de tekstverwerker
// ---------------------------------------------------------------------------

export type Opdracht =
  | { soort: "niveau"; alinea: number; niveau: number; tekst: string }
  | { soort: "tabelkop"; tabel: number }
  | { soort: "alt"; alinea: number; afbeelding: number; alt: string; tekst: string }
  | { soort: "linktekst"; alinea: number; link: number; tekst: string; href: string; alineatekst: string };

export class NietUitvoerbaar extends Error {}

/** Minimale DOM, zodat dit ook in node te testen is (linkedom) en in de browser werkt. */
export type MaakFragment = (html: string) => { firstElementChild: Element | null };

export const browserFragment: MaakFragment = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html;
  return t.content;
};

export function plekNaarDelen(pad: string): number[] {
  const d = pad.split("/");
  if (d[0] !== "body") throw new NietUitvoerbaar(`Onbekend pad: ${pad}`);
  return d.slice(1).map(Number);
}

/**
 * Vertaalt het herstelde element op `pad` naar één opdracht. Wat de
 * assistent zo niet kan uitdrukken, levert NietUitvoerbaar op; de adapter
 * zegt dat dan tegen de medewerker.
 */
export function segmentNaarOpdracht(blokken: Blok[], pad: string, html: string, fragment: MaakFragment = browserFragment): Opdracht {
  const [i, j, k] = plekNaarDelen(pad);
  const blok = blokken[i];
  if (!blok) throw new NietUitvoerbaar("Dit deel van het document is niet meer gevonden. Beoordeel opnieuw.");
  const el = fragment(html).firstElementChild;
  if (!el) throw new NietUitvoerbaar("De wijziging is leeg.");
  const tag = el.tagName.toLowerCase();

  if (j === undefined) {
    if (blok.soort === "alinea" && /^(h[1-6]|p)$/.test(tag)) {
      return { soort: "niveau", alinea: blok.bron, niveau: tag === "p" ? 0 : Number(tag[1]), tekst: blok.tekst };
    }
    if (blok.soort === "tabel" && tag === "table" && el.querySelector("th")) return { soort: "tabelkop", tabel: blok.bron };
    throw new NietUitvoerbaar("Deze wijziging kan in deze tekstverwerker nog niet automatisch. Pas het met de hand aan.");
  }

  // Een element binnen een alinea (of binnen een lijstitem: body/i/j/k).
  let alinea: Alinea | undefined;
  let index = j;
  if (blok.soort === "alinea") alinea = blok;
  else if (blok.soort === "lijst" && k !== undefined) {
    alinea = blok.items[j];
    index = k;
  }
  if (!alinea) throw new NietUitvoerbaar("Deze wijziging kan in deze tekstverwerker nog niet automatisch. Pas het met de hand aan.");
  const doel = inlineVolgorde(alinea)[index];
  if (!doel) throw new NietUitvoerbaar("Dit deel van het document is niet meer gevonden. Beoordeel opnieuw.");
  if (doel.soort === "afbeelding" && tag === "img") {
    return { soort: "alt", alinea: alinea.bron, afbeelding: doel.index, alt: el.getAttribute("alt") ?? "", tekst: alinea.tekst };
  }
  if (doel.soort === "link" && tag === "a") {
    return { soort: "linktekst", alinea: alinea.bron, link: doel.index, tekst: el.textContent ?? "", href: doel.href, alineatekst: alinea.tekst };
  }
  throw new NietUitvoerbaar("Deze wijziging kan in deze tekstverwerker nog niet automatisch. Pas het met de hand aan.");
}

/** Waar een plek in de tekstverwerker staat, om hem te tonen. */
export type Doel = { soort: "alinea"; alinea: number } | { soort: "tabel"; tabel: number } | { soort: "afbeelding"; alinea: number; afbeelding: number } | { soort: "link"; alinea: number; link: number };

export function plekNaarDoel(blokken: Blok[], pad: string): Doel | null {
  const [i, j, k] = plekNaarDelen(pad);
  const blok = blokken[i];
  if (!blok) return null;
  if (blok.soort === "tabel") return { soort: "tabel", tabel: blok.bron };
  const alinea = blok.soort === "alinea" ? blok : blok.items[j ?? 0];
  if (!alinea) return null;
  const idx = blok.soort === "alinea" ? j : k;
  if (idx === undefined) return { soort: "alinea", alinea: alinea.bron };
  const doel = inlineVolgorde(alinea)[idx];
  if (!doel) return { soort: "alinea", alinea: alinea.bron };
  return doel.soort === "afbeelding" ? { soort: "afbeelding", alinea: alinea.bron, afbeelding: doel.index } : { soort: "link", alinea: alinea.bron, link: doel.index };
}

/** Herkent een kopstijl aan de naam, in Word ("Heading2", "Title") en LibreOffice ("Heading 2"). */
export function niveauUitStijl(stijl: string | undefined | null, overzichtsniveau?: number | null): number {
  const s = (stijl ?? "").replace(/\s+/g, "").toLowerCase();
  const m = /^(?:heading|kop)(\d)$/.exec(s);
  if (m) return Math.min(Number(m[1]), 6);
  if (s === "title" || s === "titel") return 1;
  if (overzichtsniveau && overzichtsniveau >= 1 && overzichtsniveau <= 6) return overzichtsniveau;
  return 0;
}
