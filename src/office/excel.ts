/// <reference types="office-js" />
import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import { schoonSelectie, vervangInTekst, type Paar } from "../tekstvervangen.js";
import { eersteElement, esc, HANDMATIG, img, leesAfdrukUitBestand, leesOfficeBestand, NIET_GEVONDEN, padDelen, schrijfAfdrukInBestand } from "./gedeeld.js";

const MAX_RIJEN = 200;
const MAX_KOLOMMEN = 30;
const ONGELDIG = /[[\]*?:/\\]/;

type Onderdeel = { soort: "naam" } | { soort: "tabel" } | { soort: "beeld"; vorm: string };

/**
 * Microsoft Excel via Office.js (Excel op Windows en Mac, Excel voor het web).
 * Per blad een sectie met de naam als kop, het gebruikte bereik als tabel
 * en afbeeldingen (ExcelApi 1.9) met hun alternatieve tekst. Herstellen:
 * een blad hernoemen, alternatieve tekst bij een afbeelding.
 *
 * Grafieken: Office.js geeft van een grafiek geen alternatieve tekst; die
 * staan daarom niet in de html. De assistent zegt dat bij het beoordelen.
 */
export class ExcelAdapter implements Adapter {
  private kaart: Onderdeel[][] = [];
  private bladIds: string[] = [];
  private readonly vormen = Office.context.requirements.isSetSupported("ExcelApi", "1.9");

  constructor(private readonly melden: (m: Melding) => void) {}

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "plek-tonen", "afdruk-schrijven", "bestand-opleveren", "tekst-vervangen", "selectie-lezen"];
    return { id: "excel", naam: "Microsoft Excel", vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    const { html, kaart, ids, grafieken } = await Excel.run(async (ctx) => {
      const bladen = ctx.workbook.worksheets;
      bladen.load("items/name,items/id");
      await ctx.sync();
      const per = bladen.items.map((b) => {
        const bereik = b.getUsedRangeOrNullObject(true);
        bereik.load("values,rowCount,columnCount");
        const grafieken = b.charts;
        grafieken.load("items/name");
        const vormen = this.vormen ? b.shapes : null;
        vormen?.load("items/id,items/type,items/altTextDescription,items/altTextTitle");
        return { b, bereik, grafieken, vormen };
      });
      await ctx.sync();
      let grafieken = 0;
      const kaart: Onderdeel[][] = [];
      const secties = per.map(({ b, bereik, grafieken: g, vormen }) => {
        const delen = [`<h2>${esc(b.name)}</h2>`];
        const onderdelen: Onderdeel[] = [{ soort: "naam" }];
        if (!bereik.isNullObject && bereik.values.length) {
          const rijen = bereik.values.slice(0, MAX_RIJEN).map((r) => r.slice(0, MAX_KOLOMMEN));
          delen.push(`<table><tbody>${rijen.map((r) => `<tr>${r.map((c) => `<td>${esc(String(c ?? ""))}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
          onderdelen.push({ soort: "tabel" });
        }
        for (const v of vormen?.items ?? []) {
          if (v.type !== Excel.ShapeType.image) continue;
          delen.push(img(v.altTextDescription || v.altTextTitle));
          onderdelen.push({ soort: "beeld", vorm: v.id });
        }
        grafieken += g.items.length;
        kaart.push(onderdelen);
        return `<section data-oa="blad">${delen.join("")}</section>`;
      });
      return { html: secties.join("\n"), kaart, ids: bladen.items.map((b) => b.id), grafieken };
    });
    this.kaart = kaart;
    this.bladIds = ids;
    if (grafieken) this.melden({ soort: "info", tekst: `${grafieken} grafiek(en) niet beoordeeld: Excel geeft de alternatieve tekst van een grafiek niet door. Controleer die met de hand.` });
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: html };
  }

  async vervangInhoud(): Promise<void> {
    throw new Error("Een rekenblad kan de assistent niet in zijn geheel vervangen. Pas het met de hand aan.");
  }

  private plek(pad: string): { blad: string; onderdeel: Onderdeel | null } {
    const [i, j] = padDelen(pad);
    const blad = this.bladIds[i];
    if (!blad) throw new Error(NIET_GEVONDEN);
    if (j === undefined) return { blad, onderdeel: null };
    const onderdeel = this.kaart[i]?.[j];
    if (!onderdeel) throw new Error(NIET_GEVONDEN);
    return { blad, onderdeel };
  }

  vervangSegment = async (plek: Plek, html: string): Promise<void> => {
    if (!this.kaart.length) await this.leverInhoud();
    const { blad, onderdeel } = this.plek(plek.pad);
    const el = eersteElement(html);
    if (!el || !onderdeel) throw new Error(HANDMATIG);
    await Excel.run(async (ctx) => {
      const b = ctx.workbook.worksheets.getItem(blad);
      if (onderdeel.soort === "naam" && /^h[1-6]$/.test(el.tag)) {
        if (!el.tekst || el.tekst.length > 31 || ONGELDIG.test(el.tekst)) throw new Error("Een bladnaam is 1 tot 31 tekens, zonder [ ] * ? : / of \\.");
        b.name = el.tekst;
      } else if (onderdeel.soort === "beeld" && el.tag === "img") {
        const v = b.shapes.getItem(onderdeel.vorm);
        v.altTextDescription = el.attrs.alt ?? "";
        v.altTextTitle = el.attrs.alt ?? "";
      } else throw new Error(HANDMATIG);
      await ctx.sync();
    });
    this.kaart = [];
  };

  toonPlek = (plek: Plek): void => {
    let doel: { blad: string; onderdeel: Onderdeel | null };
    try {
      doel = this.plek(plek.pad);
    } catch {
      this.melden({ soort: "info", tekst: `${plek.beschrijving}: beoordeel eerst opnieuw om de plek te kunnen tonen.` });
      return;
    }
    Excel.run(async (ctx) => {
      const b = ctx.workbook.worksheets.getItem(doel.blad);
      b.activate();
      if (doel.onderdeel?.soort === "tabel") b.getRange("A1").select();
      await ctx.sync();
    }).catch((e: Error) => this.melden({ soort: "fout", tekst: e.message }));
  };

  /**
   * In elke cel met vaste tekst (geen formule) de waarden als heel woord
   * vervangen. Excel's eigen replaceAll kent geen "heel woord", vandaar
   * per cel.
   */
  vervangTekst = async (paren: Paar[]): Promise<number> => {
    const aantal = await Excel.run(async (ctx) => {
      const bladen = ctx.workbook.worksheets;
      bladen.load("items");
      await ctx.sync();
      const bereiken = bladen.items.map((b) => {
        const r = b.getUsedRangeOrNullObject(true);
        r.load("formulas,rowIndex,columnIndex");
        return { b, r };
      });
      await ctx.sync();
      let aantal = 0;
      for (const { b, r } of bereiken) {
        if (r.isNullObject) continue;
        r.formulas.forEach((rij, i) =>
          rij.forEach((cel, j) => {
            if (typeof cel !== "string" || cel.startsWith("=")) return;
            const v = vervangInTekst(cel, paren);
            if (!v.aantal) return;
            b.getCell(r.rowIndex + i, r.columnIndex + j).values = [[v.tekst]];
            aantal += v.aantal;
          }),
        );
      }
      await ctx.sync();
      return aantal;
    });
    this.kaart = [];
    return aantal;
  };

  /** Excel geeft geen deel van een cel als selectie; de geselecteerde cellen met tekst. */
  leesSelectie = async (): Promise<string> =>
    Excel.run(async (ctx) => {
      const r = ctx.workbook.getSelectedRange();
      r.load("values");
      await ctx.sync();
      return schoonSelectie(r.values.flat().filter((c) => typeof c === "string" && c.trim()).join(" "));
    });

  leverBestand = (): Promise<Inhoud> => leesOfficeBestand("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel");
  schrijfAfdruk = (a: Afdruk) => schrijfAfdrukInBestand(a);
  leesAfdruk = () => leesAfdrukUitBestand();

  toon(melding: Melding): void {
    this.melden(melding);
  }
}
