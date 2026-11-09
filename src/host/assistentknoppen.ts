import { icoonSvg, MODULES, stuurOpdracht, type Opdracht } from "@digitaalgemeengoed/oa-paneel";

/**
 * De knoppen van de assistent in de werkbalk van een werkomgeving, zoals in
 * de demo (MIRA): Paneel, dan de modules, dan Beoordelen. Elke knop toont het
 * paneel en stuurt het een opdracht (zie stuurOpdracht in oa-paneel).
 */
const PANEEL = "M2.5 3h11v10h-11zM9.5 3v10";
const ZOEK = "M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM10.5 10.5l3 3";
/** Een geselecteerd woord met een balk eroverheen: de selectie anonimiseren. */
const SELECTIE = "M2 4.5h12M2 11.5h12M3.5 6.5h9v3h-9z";

const svg = (pad: string) =>
  `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${pad}"/></svg>`;

export interface KnopInfo {
  id: "paneel" | Opdracht;
  naam: string;
  /** svg met stroke="currentColor" (16×16). */
  svg: string;
}

/**
 * De knoppen in volgorde; ook voor werkbalken die de host zelf tekent
 * (Collabora). `selectie`: of de werkomgeving de selectie kan doorgeven (dan
 * de knop Anonimiseer selectie).
 */
export function assistentKnoppen(selectie = false): KnopInfo[] {
  return [
    { id: "paneel", naam: "Paneel", svg: svg(PANEEL) },
    ...MODULES.filter((m) => m.id !== "help").map((m) => ({ id: m.id, naam: m.volgt ? `${m.naam} (volgt)` : m.naam, svg: icoonSvg(m.id, "currentColor", 16).replace("<svg ", '<svg aria-hidden="true" ') })),
    { id: "beoordelen", naam: "Beoordelen", svg: svg(ZOEK) },
    ...(selectie ? [{ id: "anon-selectie" as const, naam: "Anonimiseer selectie", svg: svg(SELECTIE) }] : []),
  ];
}

/**
 * Zet de knoppen als groep in een werkbalk. `paneel` laat het paneel zien of
 * verbergt het; zonder die functie is er geen knop Paneel.
 */
export function plaatsAssistentKnoppen(werkbalk: HTMLElement, paneel?: { toon(): void; wissel(): void }, selectie = false): void {
  const groep = document.createElement("div");
  groep.className = "oa-knoppen";
  groep.setAttribute("role", "group");
  groep.setAttribute("aria-label", "Assistent");
  for (const k of assistentKnoppen(selectie)) {
    if (k.id === "paneel" && !paneel) continue;
    const b = document.createElement("button");
    b.type = "button";
    b.title = k.naam;
    b.setAttribute("aria-label", k.naam);
    b.innerHTML = k.svg;
    b.addEventListener("click", () => {
      if (k.id === "paneel") return paneel!.wissel();
      paneel?.toon();
      stuurOpdracht(k.id);
    });
    groep.append(b);
  }
  werkbalk.append(groep);
}
