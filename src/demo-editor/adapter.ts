import {
  BASISVERMOGENS,
  type Adapter,
  type Afdruk,
  type Inhoud,
  type Melding,
  type Plek,
  type Vermogen,
  type Werkomgeving,
} from "@digitaalgemeengoed/oa-contract";
import { schoonSelectie, vervangInTekst, type Paar } from "../tekstvervangen.js";

/**
 * Adapter voor de demo-tekstverwerker: een bewerkbaar html-element.
 *
 * "rijk" levert alle optionele vermogens, "beperkt" alleen de drie
 * basisvermogens. Zo is in één werkomgeving te zien hoe de assistent
 * terugvalt als een vermogen ontbreekt.
 */
export interface DocumentOpslag {
  /** De eigenschappen van het bestand, zoals een tekstverwerker die bij het document bewaart. */
  leesEigenschap(naam: string): string | null;
  schrijfEigenschap(naam: string, waarde: string): void;
}

export class DemoEditorAdapter implements Adapter {
  private opslaanTerugroepen = new Set<() => void>();
  /** De laatste selectie in de editor; een klik in het paneel kan de selectie anders wegnemen. */
  private laatsteSelectie = "";

  constructor(
    private readonly editor: HTMLElement,
    private readonly bestand: DocumentOpslag,
    private readonly melden: (m: Melding) => void,
    private readonly soort: "rijk" | "beperkt" = "rijk",
  ) {
    const doc = editor.ownerDocument;
    doc.addEventListener("selectionchange", () => {
      const sel = doc.getSelection();
      if (sel && !sel.isCollapsed && sel.anchorNode && editor.contains(sel.anchorNode)) this.laatsteSelectie = sel.toString();
    });
  }

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS];
    if (this.soort === "rijk") vermogens.push("segment-vervangen", "plek-tonen", "opslaan-melden", "afdruk-schrijven", "tekst-vervangen", "selectie-lezen");
    return { id: `demo-editor-${this.soort}`, naam: this.soort === "rijk" ? "Demo-tekstverwerker" : "Demo-tekstverwerker (beperkt)", vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    const kopie = this.editor.cloneNode(true) as HTMLElement;
    kopie.querySelectorAll("[data-oa-gemarkeerd]").forEach((e) => e.removeAttribute("data-oa-gemarkeerd"));
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: kopie.innerHTML.trim() };
  }

  async vervangInhoud(inhoud: Inhoud): Promise<void> {
    if (inhoud.formaat !== "html") throw new Error("Deze werkomgeving opent alleen html.");
    this.editor.innerHTML = inhoud.data;
    this.editor.dispatchEvent(new Event("input", { bubbles: true }));
    this.melden({ soort: "info", tekst: "Het document is opnieuw geladen." });
  }

  toon(melding: Melding): void {
    this.melden(melding);
  }

  private zoek(plek: Plek): Element {
    let e: Element | null = this.editor;
    for (const d of plek.pad.split("/").slice(1)) e = e?.children.item(Number(d)) ?? null;
    if (!e || e === this.editor) throw new Error(`${plek.beschrijving} is niet meer gevonden. Beoordeel opnieuw.`);
    return e;
  }

  // --- Optionele vermogens; alleen in de rijke variant aangeboden ---------

  get vervangSegment(): Adapter["vervangSegment"] {
    if (this.soort !== "rijk") return undefined;
    return async (plek: Plek, html: string) => {
      this.zoek(plek).outerHTML = html;
      this.editor.dispatchEvent(new Event("input", { bubbles: true }));
    };
  }

  get toonPlek(): Adapter["toonPlek"] {
    if (this.soort !== "rijk") return undefined;
    return (plek: Plek) => {
      const e = this.zoek(plek);
      e.scrollIntoView({ behavior: "smooth", block: "center" });
      e.setAttribute("data-oa-gemarkeerd", "");
      setTimeout(() => e.removeAttribute("data-oa-gemarkeerd"), 2500);
    };
  }

  get bijOpslaan(): Adapter["bijOpslaan"] {
    if (this.soort !== "rijk") return undefined;
    return (terugroep: () => void) => {
      this.opslaanTerugroepen.add(terugroep);
      return () => this.opslaanTerugroepen.delete(terugroep);
    };
  }

  get schrijfAfdruk(): Adapter["schrijfAfdruk"] {
    if (this.soort !== "rijk") return undefined;
    return async (afdruk: Afdruk) => this.bestand.schrijfEigenschap("oa-afdruk", JSON.stringify(afdruk));
  }

  get leesAfdruk(): Adapter["leesAfdruk"] {
    if (this.soort !== "rijk") return undefined;
    return async () => {
      const w = this.bestand.leesEigenschap("oa-afdruk");
      return w ? (JSON.parse(w) as Afdruk) : null;
    };
  }

  get vervangTekst(): Adapter["vervangTekst"] {
    if (this.soort !== "rijk") return undefined;
    return async (paren: Paar[]) => {
      const doc = this.editor.ownerDocument;
      const loper = doc.createTreeWalker(this.editor, 4 /* NodeFilter.SHOW_TEXT */);
      let aantal = 0;
      for (let n = loper.nextNode(); n; n = loper.nextNode()) {
        const r = vervangInTekst(n.nodeValue ?? "", paren);
        if (r.aantal) {
          n.nodeValue = r.tekst;
          aantal += r.aantal;
        }
      }
      if (aantal) this.editor.dispatchEvent(new Event("input", { bubbles: true }));
      return aantal;
    };
  }

  get leesSelectie(): Adapter["leesSelectie"] {
    if (this.soort !== "rijk") return undefined;
    return async () => {
      const sel = this.editor.ownerDocument.getSelection();
      const nu = sel && !sel.isCollapsed && sel.anchorNode && this.editor.contains(sel.anchorNode) ? sel.toString() : "";
      return schoonSelectie(nu || this.laatsteSelectie);
    };
  }

  /** De werkomgeving roept dit aan als de medewerker opslaat. */
  meldOpgeslagen(): void {
    this.opslaanTerugroepen.forEach((t) => t());
  }
}
