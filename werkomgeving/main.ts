import { plaatsPaneel } from "@digitaalgemeengoed/oa-paneel";
import { plaatsAssistentKnoppen } from "../src/host/assistentknoppen";
import "@digitaalgemeengoed/oa-paneel/style.css";
import type { Melding } from "@digitaalgemeengoed/oa-contract";
import { DemoEditorAdapter, type DocumentOpslag } from "../src/index";
import { VOORBEELD } from "./voorbeeld";
import "./werkomgeving.css";

/**
 * De demo-werkomgeving: een tekstverwerker die zijn document en de
 * eigenschappen ervan zelf bewaart (hier in de browser, zoals een
 * tekstverwerker een bestand op schijf bewaart). De assistent bewaart niets.
 */
const SLEUTEL = "oa-demo-document";
const editor = document.getElementById("document") as HTMLElement;
const status = document.getElementById("status") as HTMLElement;
const paneelplek = document.getElementById("paneel") as HTMLElement;
const soortKeuze = document.getElementById("soort") as HTMLSelectElement;

interface Bestand {
  html: string;
  eigenschappen: Record<string, string>;
}

function leesBestand(): Bestand {
  try {
    const w = localStorage.getItem(SLEUTEL);
    if (w) return JSON.parse(w) as Bestand;
  } catch {
    /* geen opslag beschikbaar */
  }
  return { html: VOORBEELD, eigenschappen: {} };
}

let bestand = leesBestand();
editor.innerHTML = bestand.html;

function bewaar() {
  bestand = { ...bestand, html: editor.innerHTML };
  try {
    localStorage.setItem(SLEUTEL, JSON.stringify(bestand));
  } catch {
    /* geen opslag beschikbaar */
  }
}

const eigenschappen: DocumentOpslag = {
  leesEigenschap: (naam) => bestand.eigenschappen[naam] ?? null,
  schrijfEigenschap: (naam, waarde) => {
    bestand.eigenschappen[naam] = waarde;
    bewaar();
  },
};

let statusTimer: number | undefined;
function meld(m: Melding) {
  status.textContent = m.tekst;
  status.dataset.soort = m.soort;
  clearTimeout(statusTimer);
  statusTimer = window.setTimeout(() => (status.textContent = "Gereed"), 4000);
}

// --- Paneel plaatsen, opnieuw bij wisselen van werkomgeving --------------

let adapter: DemoEditorAdapter;
let weghalen: (() => void) | null = null;
function start() {
  weghalen?.();
  adapter = new DemoEditorAdapter(editor, eigenschappen, meld, soortKeuze.value as "rijk" | "beperkt");
  weghalen = plaatsPaneel(paneelplek, adapter);
}
soortKeuze.addEventListener("change", start);
start();

// De knoppen van de assistent in de werkbalk, zoals in de demo (MIRA).
const werkvlak = document.querySelector<HTMLElement>(".werkvlak")!;
const balk = document.querySelector<HTMLElement>(".werkbalk")!;
balk.append(Object.assign(document.createElement("span"), { className: "scheiding" }));
plaatsAssistentKnoppen(balk, {
  toon: () => werkvlak.classList.remove("zonder-paneel"),
  wissel: () => werkvlak.classList.toggle("zonder-paneel"),
});

// --- Werkbalk --------------------------------------------------------------

document.querySelectorAll<HTMLButtonElement>("[data-opdracht]").forEach((k) =>
  k.addEventListener("click", () => {
    editor.focus();
    const [opdracht, waarde] = k.dataset.opdracht!.split(":");
    document.execCommand(opdracht, false, waarde);
  }),
);

document.getElementById("opslaan")!.addEventListener("click", () => {
  bewaar();
  meld({ soort: "succes", tekst: "Opgeslagen in de werkomgeving." });
  adapter.meldOpgeslagen();
});

document.getElementById("nieuw")!.addEventListener("click", () => {
  if (!confirm("Een nieuw voorbeelddocument openen? Het huidige document en zijn eigenschappen worden in deze werkomgeving vervangen.")) return;
  bestand = { html: VOORBEELD, eigenschappen: {} };
  editor.innerHTML = VOORBEELD;
  bewaar();
  start();
});

window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    document.getElementById("opslaan")!.click();
  }
});
