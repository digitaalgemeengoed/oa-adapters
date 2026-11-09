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
