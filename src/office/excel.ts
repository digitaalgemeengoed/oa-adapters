/// <reference types="office-js" />
import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import { plaatshoudersIn, schoonSelectie, vervangInTekst, vondstenVoorMarkeren, type Paar } from "../tekstvervangen.js";
import type { PiiMarkering, PiiPlek } from "@digitaalgemeengoed/oa-contract";
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
  /** Eigen documenteigenschappen (ExcelApi 1.7). */
  private readonly eigenschappen = Office.context.requirements.isSetSupported("ExcelApi", "1.7");

  constructor(private readonly melden: (m: Melding) => void) {}

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "plek-tonen", "afdruk-schrijven", "bestand-opleveren", "tekst-vervangen", "selectie-lezen", "pii-markeren", "pii-klik"];
    if (this.eigenschappen) vermogens.push("eigenschap-schrijven");
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

  // --- Anonimiseren in het document -------------------------------------
  // De plaatshouder staat als tekst in de cel ([PERSOON 1]); de plek is
  // blad, rij, kolom en het hoeveelste voorkomen (s1!r4c2#0). Een deel van
  // een cel kan Office.js niet opmaken; of het een voorvertoning is, weet
  // het register.

  /** Alle cellen met vaste tekst, per blad. */
  private async cellen(ctx: Excel.RequestContext) {
    const bladen = ctx.workbook.worksheets;
    bladen.load("items/id");
    await ctx.sync();
    const per = bladen.items.map((b) => {
      const r = b.getUsedRangeOrNullObject(true);
      r.load("formulas,rowIndex,columnIndex");
      return { b, r };
    });
    await ctx.sync();
    const uit: { b: Excel.Worksheet; rij: number; kolom: number; tekst: string; kenmerk: string }[] = [];
    for (const { b, r } of per) {
      if (r.isNullObject) continue;
      r.formulas.forEach((rij, i) =>
        rij.forEach((cel, j) => {
          if (typeof cel !== "string" || cel.startsWith("=") || !cel) return;
          const rr = r.rowIndex + i;
          const kk = r.columnIndex + j;
          uit.push({ b, rij: rr, kolom: kk, tekst: cel, kenmerk: `${b.id}!r${rr}c${kk}` });
        }),
      );
    }
    return uit;
  }

  markeerPii = async (markeringen: PiiMarkering[]): Promise<PiiPlek[]> => {
    const voor = new Set((await this.leesPiiPlekken()).map((p) => p.plek));
    await Excel.run(async (ctx) => {
      for (const c of await this.cellen(ctx)) {
        const v = vondstenVoorMarkeren(c.tekst, markeringen);
        if (!v.length) continue;
        let t = c.tekst;
        for (const x of v) t = t.slice(0, x.begin) + x.m.plaatshouder + t.slice(x.eind);
        c.b.getCell(c.rij, c.kolom).values = [[t]];
      }
      await ctx.sync();
    });
    this.kaart = [];
    return (await this.leesPiiPlekken()).filter((p) => !voor.has(p.plek));
  };

  leesPiiPlekken = async (): Promise<PiiPlek[]> =>
    Excel.run(async (ctx) =>
      (await this.cellen(ctx)).flatMap((c) => plaatshoudersIn(c.tekst).map((p, i) => ({ plek: `${c.kenmerk}#${i}`, plaatshouder: p.plaatshouder, voorvertoning: false }))),
    );

  herstelPii = async (plekken: { plek: string; waarde: string }[]): Promise<void> => {
    await Excel.run(async (ctx) => {
      const cellen = await this.cellen(ctx);
      const per = new Map<string, { n: number; waarde: string }[]>();
      for (const { plek, waarde } of plekken) {
        const [kenmerk, n] = plek.split("#");
        per.set(kenmerk!, [...(per.get(kenmerk!) ?? []), { n: Number(n), waarde }]);
      }
      for (const [kenmerk, wat] of per) {
        const c = cellen.find((x) => x.kenmerk === kenmerk);
        if (!c) continue;
        const ph = plaatshoudersIn(c.tekst);
        let t = c.tekst;
        for (const { n, waarde } of wat.sort((a, b) => b.n - a.n)) {
          const p = ph[n];
          if (p) t = t.slice(0, p.begin) + waarde + t.slice(p.eind);
        }
        c.b.getCell(c.rij, c.kolom).values = [[t]];
      }
      await ctx.sync();
    });
    this.kaart = [];
  };

  toonPiiPlek = (plek: string): void => {
    const m = /^(.+)!r(\d+)c(\d+)#/.exec(plek);
    if (!m) return;
    Excel.run(async (ctx) => {
      const b = ctx.workbook.worksheets.getItem(m[1]!);
      b.activate();
      b.getCell(Number(m[2]), Number(m[3])).select();
      await ctx.sync();
    }).catch(() => undefined);
  };

  bijPiiKlik = (terugroep: (p: PiiPlek) => void): (() => void) => {
    let laatste = "";
    const bij = () => {
      Excel.run(async (ctx) => {
        const r = ctx.workbook.getSelectedRange();
        r.load("values,rowIndex,columnIndex,cellCount");
        const b = r.worksheet;
        b.load("id");
        await ctx.sync();
        const tekst = r.cellCount === 1 && typeof r.values[0]?.[0] === "string" ? (r.values[0]![0] as string) : "";
        const p = plaatshoudersIn(tekst)[0];
        const plek = p ? `${b.id}!r${r.rowIndex}c${r.columnIndex}#0` : "";
        if (p && plek !== laatste) terugroep({ plek, plaatshouder: p.plaatshouder, voorvertoning: false });
        laatste = plek;
      }).catch(() => undefined);
    };
    Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, bij);
    return () => Office.context.document.removeHandlerAsync(Office.EventType.DocumentSelectionChanged, { handler: bij });
  };

  get schrijfDocumenteigenschap(): ((naam: string, waarde: string) => Promise<void>) | undefined {
    if (!this.eigenschappen) return undefined;
    return async (naam, waarde) =>
      Excel.run(async (ctx) => {
        ctx.workbook.properties.custom.add(naam, waarde.slice(0, 255));
        await ctx.sync();
      });
  }

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
