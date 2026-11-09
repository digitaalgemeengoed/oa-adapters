/**
 * Gedeelde hulp voor het vermogen "tekst-vervangen": persoonsgegevens in
 * het document zelf vervangen door hun plaatshouder ([PERSOON 1]).
 *
 * Alleen hele woorden worden vervangen ("Jan" niet in "Janssen"), en de
 * langste waarden eerst, zodat "Jan de Vries" niet half vervangen wordt
 * omdat "Jan" eerder in de lijst stond.
 */
export interface Paar {
  van: string;
  naar: string;
}

export function ordenParen(paren: Paar[]): Paar[] {
  const gezien = new Set<string>();
  return paren
    .filter((p) => p.van.trim() !== "" && p.van !== p.naar && !gezien.has(p.van) && gezien.add(p.van))
    .sort((a, b) => b.van.length - a.van.length);
}

const ESCAPE = /[.*+?^${}()|[\]\\]/g;

/** Een patroon dat de waarde alleen als heel woord vindt (ook bij ä, é, ĳ …). */
export function heelWoord(van: string, vlaggen = "gu"): RegExp {
  return new RegExp(`(?<![\\p{L}\\p{N}_])${van.replace(ESCAPE, "\\$&")}(?![\\p{L}\\p{N}_])`, vlaggen);
}

/** Vervangt in een stuk platte tekst; geeft de nieuwe tekst en het aantal vervangingen. */
export function vervangInTekst(tekst: string, paren: Paar[]): { tekst: string; aantal: number } {
  let aantal = 0;
  for (const p of ordenParen(paren)) {
    tekst = tekst.replace(heelWoord(p.van), () => {
      aantal++;
      return p.naar;
    });
  }
  return { tekst, aantal };
}

/** Een selectie opschonen tot iets dat als persoonsgegeven kan dienen. */
export function schoonSelectie(s: string | null | undefined): string {
  return (s ?? "").replace(/\s+/g, " ").trim().slice(0, 500);
}

/**
 * Voor zoeken en vervangen in LibreOffice/Collabora zelf (ICU): de waarde
 * letterlijk (\\Q…\\E), met dezelfde woordgrens als hierboven.
 */
export function icuPatroon(van: string): string {
  return `(?<![\\p{L}\\p{N}_])\\Q${van.replaceAll("\\E", "\\E\\\\E\\Q")}\\E(?![\\p{L}\\p{N}_])`;
}

/** In de vervangtekst van LibreOffice zijn & en $ stuurtekens; een backslash is niet letterlijk in te voegen. */
export function icuVervanging(naar: string): string {
  if (naar.includes("\\")) throw new Error("Een vervangtekst met een backslash kan niet letterlijk worden ingevoegd.");
  return naar.replace(/[&$]/g, "\\$&");
}

/** Hoe vaak de waarden als heel woord voorkomen in de tekst van een stuk html. */
export function telInHtml(html: string, paren: Paar[]): number {
  const tekst = html
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
  return vervangInTekst(tekst, paren).aantal;
}

/** Een plaatshouder in de tekst, zoals [PERSOON 1] of [E-MAIL 2]. */
export const PLAATSHOUDER = /\[[A-Z][A-Z-]* \d+\]/g;

/** De plaatshouders in een stuk tekst, met hun positie. */
export function plaatshoudersIn(tekst: string): { plaatshouder: string; begin: number; eind: number }[] {
  return [...tekst.matchAll(PLAATSHOUDER)].map((m) => ({ plaatshouder: m[0], begin: m.index!, eind: m.index! + m[0].length }));
}

/**
 * Waar in de tekst de waarden (als heel woord, de langste eerst) staan, zonder
 * overlap en niet in een plaatshouder die er al staat. Van achter naar voren
 * gesorteerd, zodat vervangen de posities van de rest niet verschuift.
 */
export function vondstenVoorMarkeren<T extends { van: string }>(tekst: string, markeringen: T[]): { begin: number; eind: number; m: T }[] {
  const bezet = plaatshoudersIn(tekst).map((p) => [p.begin, p.eind] as const);
  const uit: { begin: number; eind: number; m: T }[] = [];
  for (const m of [...markeringen].filter((x) => x.van.trim()).sort((a, b) => b.van.length - a.van.length)) {
    for (const v of tekst.matchAll(heelWoord(m.van))) {
      const begin = v.index!;
      const eind = begin + v[0].length;
      if (bezet.some(([b, e]) => begin < e && eind > b)) continue;
      bezet.push([begin, eind]);
      uit.push({ begin, eind, m });
    }
  }
  return uit.sort((a, b) => b.begin - a.begin);
}

/** Kleur van een plaatshouder per niveau (zoals de demo). */
export const PII_KLEUR: Record<number, string> = { 1: "#1E6B33", 2: "#8A5300", 3: "#A4001D" };
