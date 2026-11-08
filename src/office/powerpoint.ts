/// <reference types="office-js" />
import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import { eersteElement, esc, HANDMATIG, img, leesAfdrukUitBestand, leesOfficeBestand, NIET_GEVONDEN, padDelen, schrijfAfdrukInBestand } from "./gedeeld.js";

/** Plaatshouders die een titel zijn. */
const TITELS = new Set(["Title", "CenterTitle", "VerticalTitle"]);
/** Plaatshouders zonder tekst: daar vragen we de tekst niet op (dat zou de hele opdracht laten mislukken). */
const ZONDER_TEKST = new Set(["Picture", "Chart", "Table", "OnlinePicture", "SmartArt", "Media", "Cameo", "SlideNumber", "Date", "Footer", "Header"]);
const OPSOMMING = new Set(["Body", "Content", "VerticalBody", "VerticalContent"]);
const TITELNAAM = /^(title|titel)\b/i;

type Onderdeel = { soort: "titel"; vorm: string } | { soort: "tekst"; vorm: string } | { soort: "beeld"; vorm: string };

const regels = (t: string) => t.split(/[\r\n\u000b]+/).map((r) => r.trim()).filter(Boolean);

/**
 * Microsoft PowerPoint via Office.js. Per dia een sectie: de titel als kop,
 * tekstvakken als opsomming of alinea, afbeeldingen met hun alternatieve
 * tekst. Herstellen: een titel invullen of wijzigen, alternatieve tekst bij
 * een afbeelding.
 *
 * Wat PowerPoint niet kan (oudere versies): titels herkennen zonder
 * PowerPointApi 1.8 (dan alleen op de naam "Title"/"Titel"), alternatieve
 * tekst lezen en schrijven zonder PowerPointApi 1.10. Afbeeldingen blijven
 * dan buiten de beoordeling en het paneel zegt dat.
 */
export class PowerPointAdapter implements Adapter {
  private kaart: Onderdeel[][] = [];
  private diaIds: string[] = [];
  private readonly plaatshouders = Office.context.requirements.isSetSupported("PowerPointApi", "1.8");
  private readonly altTekst = Office.context.requirements.isSetSupported("PowerPointApi", "1.10");
  private readonly selecteren = Office.context.requirements.isSetSupported("PowerPointApi", "1.5");

  constructor(private readonly melden: (m: Melding) => void) {}

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "afdruk-schrijven", "bestand-opleveren"];
    if (this.selecteren) vermogens.push("plek-tonen");
    return { id: "powerpoint", naam: "Microsoft PowerPoint", vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    let beeldenOverslagen = 0;
    const { html, kaart, ids } = await PowerPoint.run(async (ctx) => {
      const dias = ctx.presentation.slides;
      dias.load("items/id");
      await ctx.sync();
      const vormen = dias.items.map((d) => {
        d.shapes.load("items/id,items/name,items/type");
        return d.shapes;
      });
      await ctx.sync();
      // Tweede ronde: per vorm alleen laden wat bij dat soort vorm bestaat.
      const plaats = new Map<string, PowerPoint.PlaceholderFormat>();
      if (this.plaatshouders)
        for (const v of vormen.flatMap((c) => c.items))
          if (v.type === "Placeholder") plaats.set(v.id, v.placeholderFormat.load("type"));
      await ctx.sync();
      const tekst = new Map<string, PowerPoint.TextRange>();
      for (const v of vormen.flatMap((c) => c.items)) {
        const p = plaats.get(v.id)?.type;
        const heeftTekst = v.type === "TextBox" || v.type === "GeometricShape" || (v.type === "Placeholder" && !(p && ZONDER_TEKST.has(p)));
        if (heeftTekst) tekst.set(v.id, v.textFrame.textRange.load("text"));
        if (v.type === "Image" && this.altTekst) v.load("altTextDescription");
      }
      await ctx.sync();

      const kaart: Onderdeel[][] = [];
      const secties = vormen.map((c) => {
        const delen: string[] = [];
        const onderdelen: Onderdeel[] = [];
        const titel = c.items.find((v) => {
          const p = plaats.get(v.id)?.type;
          return (p ? TITELS.has(p) : TITELNAAM.test(v.name)) && tekst.get(v.id)?.text.trim();
        });
        if (titel) {
          delen.push(`<h2>${esc(regels(tekst.get(titel.id)!.text).join(" "))}</h2>`);
          onderdelen.push({ soort: "titel", vorm: titel.id });
        }
        for (const v of c.items) {
          if (v === titel) continue;
          const t = tekst.get(v.id)?.text;
          if (t !== undefined) {
            const r = regels(t);
            if (!r.length) continue;
            const p = plaats.get(v.id)?.type;
            delen.push(p && OPSOMMING.has(p) ? `<ul>${r.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : r.map((x) => `<p>${esc(x)}</p>`).join(""));
            onderdelen.push({ soort: "tekst", vorm: v.id });
          } else if (v.type === "Image") {
            if (!this.altTekst) {
              beeldenOverslagen++;
              continue;
            }
            delen.push(img(v.altTextDescription));
            onderdelen.push({ soort: "beeld", vorm: v.id });
          }
        }
        kaart.push(onderdelen);
        return `<section data-oa="dia">${delen.join("")}</section>`;
      });
      return { html: secties.join("\n"), kaart, ids: dias.items.map((d) => d.id) };
    });
    this.kaart = kaart;
    this.diaIds = ids;
    if (beeldenOverslagen)
      this.melden({ soort: "info", tekst: `${beeldenOverslagen} afbeelding(en) niet beoordeeld: deze versie van PowerPoint geeft de alternatieve tekst niet door. Controleer die met de hand.` });
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: html };
  }

  async vervangInhoud(): Promise<void> {
    throw new Error("Een presentatie kan de assistent niet in zijn geheel vervangen. Pas het met de hand aan.");
  }

  private plek(pad: string): { dia: string; onderdeel: Onderdeel | null } {
    const [i, j] = padDelen(pad);
    const dia = this.diaIds[i];
    if (!dia) throw new Error(NIET_GEVONDEN);
    if (j === undefined) return { dia, onderdeel: null };
    const onderdeel = this.kaart[i]?.[j];
    if (!onderdeel) throw new Error(NIET_GEVONDEN);
    return { dia, onderdeel };
  }

  vervangSegment = async (plek: Plek, html: string): Promise<void> => {
    if (!this.kaart.length) await this.leverInhoud();
    const { dia, onderdeel } = this.plek(plek.pad);
    const el = eersteElement(html);
    if (!el) throw new Error(HANDMATIG);
    await PowerPoint.run(async (ctx) => {
      const d = ctx.presentation.slides.getItem(dia);
      if (!onderdeel && el.tag === "section" && el.attrs.titel) {
        // Dia zonder titel (WCAG 2.4.2): een tekstvak "Titel" bovenaan.
        // Een plaatshouder toevoegen kan Office.js niet.
        const vak = d.shapes.addTextBox(el.attrs.titel, { left: 36, top: 18, width: 640, height: 50 });
        vak.name = "Titel";
        vak.textFrame.textRange.font.size = 32;
        vak.textFrame.textRange.font.bold = true;
      } else if (onderdeel?.soort === "titel" && /^h[1-6]$/.test(el.tag) && el.tekst) {
        d.shapes.getItem(onderdeel.vorm).textFrame.textRange.text = el.tekst;
      } else if (onderdeel?.soort === "beeld" && el.tag === "img" && this.altTekst) {
        d.shapes.getItem(onderdeel.vorm).altTextDescription = el.attrs.alt ?? "";
      } else throw new Error(HANDMATIG);
      await ctx.sync();
    });
    this.kaart = [];
  };

  toonPlek = (plek: Plek): void => {
    let doel: { dia: string; onderdeel: Onderdeel | null };
    try {
      doel = this.plek(plek.pad);
    } catch {
      this.melden({ soort: "info", tekst: `${plek.beschrijving}: beoordeel eerst opnieuw om de plek te kunnen tonen.` });
      return;
    }
    PowerPoint.run(async (ctx) => {
      ctx.presentation.setSelectedSlides([doel.dia]);
      if (doel.onderdeel) ctx.presentation.slides.getItem(doel.dia).setSelectedShapes([doel.onderdeel.vorm]);
      await ctx.sync();
    }).catch((e: Error) => this.melden({ soort: "fout", tekst: e.message }));
  };

  leverBestand = (): Promise<Inhoud> => leesOfficeBestand("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "PowerPoint");
  schrijfAfdruk = (a: Afdruk) => schrijfAfdrukInBestand(a);
  leesAfdruk = () => leesAfdrukUitBestand();

  toon(melding: Melding): void {
    this.melden(melding);
  }
}
