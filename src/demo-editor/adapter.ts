import {
  BASISVERMOGENS,
  type Adapter,
  type Afdruk,
  type Inhoud,
  type Melding,
  type PiiMarkering,
  type PiiPlek,
  type Plek,
  type Vermogen,
  type Werkomgeving,
} from "@digitaalgemeengoed/oa-contract";
import { heelWoord, ordenParen, schoonSelectie, vervangInTekst, type Paar } from "../tekstvervangen.js";

/** Een plaatshouder in de demo: een span die je niet kunt bewerken, gekleurd naar het niveau. */
const PII = "data-oa-pii";

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
    if (this.soort === "rijk") vermogens.push("segment-vervangen", "plek-tonen", "opslaan-melden", "afdruk-schrijven", "tekst-vervangen", "selectie-lezen", "pii-markeren", "pii-klik", "eigenschap-schrijven");
    return { id: `demo-editor-${this.soort}`, naam: this.soort === "rijk" ? "Demo-tekstverwerker" : "Demo-tekstverwerker (beperkt)", vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    const kopie = this.editor.cloneNode(true) as HTMLElement;
    kopie.querySelectorAll("[data-oa-gemarkeerd]").forEach((e) => e.removeAttribute("data-oa-gemarkeerd"));
    kopie.querySelectorAll(`[${PII}].on`).forEach((e) => e.classList.remove("on"));
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

  // --- Anonimiseren in het document ------------------------------------

  get markeerPii(): Adapter["markeerPii"] {
    if (this.soort !== "rijk") return undefined;
    return async (markeringen: PiiMarkering[]) => {
      const doc = this.editor.ownerDocument;
      let volgnummer = Math.max(0, ...this.plekken().map((e) => Number(e.getAttribute(PII)!.slice(1)) || 0));
      const nieuw: PiiPlek[] = [];
      const per = new Map(markeringen.map((m) => [m.van, m]));
      for (const { van } of ordenParen(markeringen.map((m) => ({ van: m.van, naar: m.plaatshouder })))) {
        const m = per.get(van)!;
        // Tekstknopen eerst verzamelen: we splitsen ze tijdens het lopen.
        const loper = doc.createTreeWalker(this.editor, 4 /* SHOW_TEXT */);
        const knopen: Text[] = [];
        for (let n = loper.nextNode(); n; n = loper.nextNode()) if (!(n.parentElement?.closest(`[${PII}]`))) knopen.push(n as Text);
        for (const knoop of knopen) {
          const tekst = knoop.data;
          const vondsten = [...tekst.matchAll(heelWoord(van))];
          if (!vondsten.length) continue;
          const frag = doc.createDocumentFragment();
          let i = 0;
          for (const v of vondsten) {
            frag.append(doc.createTextNode(tekst.slice(i, v.index!)));
            const plek = `p${++volgnummer}`;
            frag.append(this.plaatshouder(plek, m));
            nieuw.push({ plek, plaatshouder: m.plaatshouder, voorvertoning: m.voorvertoning });
            i = v.index! + v[0].length;
          }
          frag.append(doc.createTextNode(tekst.slice(i)));
          knoop.replaceWith(frag);
        }
      }
      if (nieuw.length) this.editor.dispatchEvent(new Event("input", { bubbles: true }));
      return nieuw;
    };
  }

  private plaatshouder(plek: string, m: Pick<PiiMarkering, "plaatshouder" | "ppl" | "voorvertoning">): HTMLElement {
    const e = this.editor.ownerDocument.createElement("span");
    e.setAttribute(PII, plek);
    e.className = `oa-plh l${m.ppl}${m.voorvertoning ? " pv" : ""}`;
    e.setAttribute("contenteditable", "false");
    e.tabIndex = 0;
    e.setAttribute("role", "button");
    e.textContent = m.plaatshouder;
    return e;
  }

  private plekken(): HTMLElement[] {
    return [...this.editor.querySelectorAll<HTMLElement>(`[${PII}]`)];
  }

  get leesPiiPlekken(): Adapter["leesPiiPlekken"] {
    if (this.soort !== "rijk") return undefined;
    return async () => this.plekken().map((e) => ({ plek: e.getAttribute(PII)!, plaatshouder: e.textContent ?? "", voorvertoning: e.classList.contains("pv") }));
  }

  get herstelPii(): Adapter["herstelPii"] {
    if (this.soort !== "rijk") return undefined;
    return async (plekken: { plek: string; waarde: string }[]) => {
      for (const { plek, waarde } of plekken) {
        const e = this.editor.querySelector(`[${PII}="${CSS.escape(plek)}"]`);
        e?.replaceWith(this.editor.ownerDocument.createTextNode(waarde));
      }
      this.editor.normalize();
      this.editor.dispatchEvent(new Event("input", { bubbles: true }));
    };
  }

  get zetPiiDefinitief(): Adapter["zetPiiDefinitief"] {
    if (this.soort !== "rijk") return undefined;
    return async () => {
      this.plekken().forEach((e) => e.classList.remove("pv"));
      this.editor.dispatchEvent(new Event("input", { bubbles: true }));
    };
  }

  get toonPiiPlek(): Adapter["toonPiiPlek"] {
    if (this.soort !== "rijk") return undefined;
    return (plek: string) => {
      const e = this.editor.querySelector<HTMLElement>(`[${PII}="${CSS.escape(plek)}"]`);
      if (!e) return;
      e.scrollIntoView({ behavior: "smooth", block: "center" });
      this.plekken().forEach((x) => x.classList.toggle("on", x === e));
    };
  }

  get bijPiiKlik(): Adapter["bijPiiKlik"] {
    if (this.soort !== "rijk") return undefined;
    return (terugroep: (p: PiiPlek) => void) => {
      const luister = (ev: Event) => {
        if (ev.type === "keydown" && (ev as KeyboardEvent).key !== "Enter" && (ev as KeyboardEvent).key !== " ") return;
        const e = (ev.target as Element | null)?.closest?.(`[${PII}]`);
        if (!e || !this.editor.contains(e)) return;
        ev.preventDefault();
        this.plekken().forEach((x) => x.classList.toggle("on", x === e));
        terugroep({ plek: e.getAttribute(PII)!, plaatshouder: e.textContent ?? "", voorvertoning: e.classList.contains("pv") });
      };
      this.editor.addEventListener("click", luister);
      this.editor.addEventListener("keydown", luister);
      return () => {
        this.editor.removeEventListener("click", luister);
        this.editor.removeEventListener("keydown", luister);
      };
    };
  }

  get schrijfDocumenteigenschap(): Adapter["schrijfDocumenteigenschap"] {
    if (this.soort !== "rijk") return undefined;
    return async (naam: string, waarde: string) => this.bestand.schrijfEigenschap(naam, waarde);
  }

  /** De werkomgeving roept dit aan als de medewerker opslaat. */
  meldOpgeslagen(): void {
    this.opslaanTerugroepen.forEach((t) => t());
  }
}
