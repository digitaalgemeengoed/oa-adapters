/// <reference types="office-js" />
import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import { heelWoord, ordenParen, PII_KLEUR, plaatshoudersIn, schoonSelectie, vondstenVoorMarkeren, type Paar } from "../tekstvervangen.js";
import type { PiiMarkering, PiiPlek } from "@digitaalgemeengoed/oa-contract";
import { eersteElement, esc, HANDMATIG, img, leesAfdrukUitBestand, leesOfficeBestand, NIET_GEVONDEN, padDelen, schrijfAfdrukInBestand } from "./gedeeld.js";

/** Plaatshouders die een titel zijn. */
const TITELS = new Set(["Title", "CenterTitle", "VerticalTitle"]);
/** Plaatshouders zonder tekst: daar vragen we de tekst niet op (dat zou de hele opdracht laten mislukken). */
const ZONDER_TEKST = new Set(["Picture", "Chart", "Table", "OnlinePicture", "SmartArt", "Media", "Cameo", "SlideNumber", "Date", "Footer", "Header"]);
const OPSOMMING = new Set(["Body", "Content", "VerticalBody", "VerticalContent"]);
const TITELNAAM = /^(title|titel)\b/i;

type Onderdeel = { soort: "titel"; vorm: string } | { soort: "tekst"; vorm: string } | { soort: "beeld"; vorm: string };

/** Dia's, hun vormen en de tekst van elke vorm die tekst kan hebben. */
async function laadTekstvormen(ctx: PowerPoint.RequestContext, plaatshouders: boolean, extra: (v: PowerPoint.Shape) => void = () => {}) {
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
  if (plaatshouders)
    for (const v of vormen.flatMap((c) => c.items))
      if (v.type === "Placeholder") plaats.set(v.id, v.placeholderFormat.load("type"));
  await ctx.sync();
  const tekst = new Map<string, PowerPoint.TextRange>();
  for (const v of vormen.flatMap((c) => c.items)) {
    const p = plaats.get(v.id)?.type;
    const heeftTekst = v.type === "TextBox" || v.type === "GeometricShape" || (v.type === "Placeholder" && !(p && ZONDER_TEKST.has(p)));
    if (heeftTekst) tekst.set(v.id, v.textFrame.textRange.load("text"));
    extra(v);
  }
  await ctx.sync();
  return { dias, vormen, plaats, tekst };
}

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
  /** TextRange.getSubstring: een deel van een tekstvak vervangen zonder de rest van de opmaak te verliezen. */
  private readonly deeltekst = Office.context.requirements.isSetSupported("PowerPointApi", "1.4");

  constructor(private readonly melden: (m: Melding) => void) {}

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "afdruk-schrijven", "bestand-opleveren"];
    if (this.selecteren) vermogens.push("plek-tonen", "selectie-lezen");
    if (this.deeltekst) vermogens.push("tekst-vervangen", "pii-markeren");
    if (this.deeltekst && this.selecteren) vermogens.push("pii-klik");
    return { id: "powerpoint", naam: "Microsoft PowerPoint", vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    let beeldenOverslagen = 0;
    const { html, kaart, ids } = await PowerPoint.run(async (ctx) => {
      const { dias, vormen, plaats, tekst } = await laadTekstvormen(ctx, this.plaatshouders, (v) => {
        if (v.type === "Image" && this.altTekst) v.load("altTextDescription");
      });

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

  /**
   * Per tekstvak de vondsten van achter naar voren vervangen, zodat de
   * posities kloppen en alleen het vervangen stuk zijn opmaak verliest.
   */
  get vervangTekst(): ((paren: Paar[]) => Promise<number>) | undefined {
    if (!this.deeltekst) return undefined;
    return async (paren) => {
      const geordend = ordenParen(paren);
      const aantal = await PowerPoint.run(async (ctx) => {
        const { tekst } = await laadTekstvormen(ctx, this.plaatshouders);
        let aantal = 0;
        for (const bereik of tekst.values()) {
          // Vondsten verzamelen op de oorspronkelijke tekst, zonder overlap; langste waarde wint.
          const bezet: { begin: number; eind: number; naar: string }[] = [];
          for (const p of geordend)
            for (const m of bereik.text.matchAll(heelWoord(p.van))) {
              const begin = m.index!;
              const eind = begin + m[0].length;
              if (!bezet.some((b) => begin < b.eind && eind > b.begin)) bezet.push({ begin, eind, naar: p.naar });
            }
          for (const b of bezet.sort((x, y) => y.begin - x.begin)) bereik.getSubstring(b.begin, b.eind - b.begin).text = b.naar;
          aantal += bezet.length;
        }
        await ctx.sync();
        return aantal;
      });
      this.kaart = [];
      return aantal;
    };
  }

  // --- Anonimiseren in het document -------------------------------------
  // De plaatshouder staat als tekst in het tekstvak, met de kleur van het
  // niveau en (zolang het een voorvertoning is) een gestreepte onderstreping.
  // De plek is dia, vorm en het hoeveelste voorkomen (d256/s3#0).

  private async vakken(ctx: PowerPoint.RequestContext) {
    const { dias, vormen, tekst } = await laadTekstvormen(ctx, this.plaatshouders);
    const uit: { dia: string; vorm: string; bereik: PowerPoint.TextRange; kenmerk: string }[] = [];
    vormen.forEach((c, i) =>
      c.items.forEach((v) => {
        const bereik = tekst.get(v.id);
        if (bereik) uit.push({ dia: dias.items[i]!.id, vorm: v.id, bereik, kenmerk: `${dias.items[i]!.id}/${v.id}` });
      }),
    );
    return uit;
  }

  get markeerPii(): ((m: PiiMarkering[]) => Promise<PiiPlek[]>) | undefined {
    if (!this.deeltekst) return undefined;
    return async (markeringen) => {
      const voor = new Set((await this.leesPiiPlekken!()).map((p) => p.plek));
      await PowerPoint.run(async (ctx) => {
        for (const v of await this.vakken(ctx)) {
          for (const x of vondstenVoorMarkeren(v.bereik.text, markeringen)) {
            const deel = v.bereik.getSubstring(x.begin, x.eind - x.begin);
            deel.text = x.m.plaatshouder;
            const nieuw = v.bereik.getSubstring(x.begin, x.m.plaatshouder.length);
            nieuw.font.color = PII_KLEUR[x.m.ppl] ?? PII_KLEUR[1]!;
            nieuw.font.underline = x.m.voorvertoning ? "Dash" : "None";
          }
        }
        await ctx.sync();
      });
      this.kaart = [];
      return (await this.leesPiiPlekken!()).filter((p) => !voor.has(p.plek));
    };
  }

  get leesPiiPlekken(): (() => Promise<PiiPlek[]>) | undefined {
    if (!this.deeltekst) return undefined;
    return async () =>
      PowerPoint.run(async (ctx) =>
        (await this.vakken(ctx)).flatMap((v) => plaatshoudersIn(v.bereik.text).map((p, i) => ({ plek: `${v.kenmerk}#${i}`, plaatshouder: p.plaatshouder, voorvertoning: false }))),
      );
  }

  get herstelPii(): ((p: { plek: string; waarde: string }[]) => Promise<void>) | undefined {
    if (!this.deeltekst) return undefined;
    return async (plekken) => {
      await PowerPoint.run(async (ctx) => {
        const vakken = await this.vakken(ctx);
        const per = new Map<string, { n: number; waarde: string }[]>();
        for (const { plek, waarde } of plekken) {
          const [kenmerk, n] = plek.split("#");
          per.set(kenmerk!, [...(per.get(kenmerk!) ?? []), { n: Number(n), waarde }]);
        }
        for (const [kenmerk, wat] of per) {
          const v = vakken.find((x) => x.kenmerk === kenmerk);
          if (!v) continue;
          const ph = plaatshoudersIn(v.bereik.text);
          for (const { n, waarde } of wat.sort((a, b) => b.n - a.n)) {
            const p = ph[n];
            if (!p) continue;
            const deel = v.bereik.getSubstring(p.begin, p.eind - p.begin);
            deel.text = waarde;
            v.bereik.getSubstring(p.begin, waarde.length).font.underline = "None";
          }
        }
        await ctx.sync();
      });
      this.kaart = [];
    };
  }

  get zetPiiDefinitief(): (() => Promise<void>) | undefined {
    if (!this.deeltekst) return undefined;
    return async () =>
      PowerPoint.run(async (ctx) => {
        for (const v of await this.vakken(ctx)) for (const p of plaatshoudersIn(v.bereik.text)) v.bereik.getSubstring(p.begin, p.eind - p.begin).font.underline = "None";
        await ctx.sync();
      });
  }

  get toonPiiPlek(): ((plek: string) => void) | undefined {
    if (!this.selecteren) return undefined;
    return (plek) => {
      const [dia, rest] = plek.split("/");
      const vorm = rest?.split("#")[0];
      PowerPoint.run(async (ctx) => {
        ctx.presentation.setSelectedSlides([dia!]);
        if (vorm) ctx.presentation.slides.getItem(dia!).setSelectedShapes([vorm]);
        await ctx.sync();
      }).catch(() => undefined);
    };
  }

  get bijPiiKlik(): ((t: (p: PiiPlek) => void) => () => void) | undefined {
    if (!this.selecteren || !this.deeltekst) return undefined;
    return (terugroep) => {
      let laatste = "";
      const bij = () => {
        PowerPoint.run(async (ctx) => {
          const dias = ctx.presentation.getSelectedSlides();
          dias.load("items/id");
          const vormen = ctx.presentation.getSelectedShapes();
          vormen.load("items/id");
          await ctx.sync();
          const dia = dias.items[0]?.id;
          const vorm = vormen.items[0];
          let plek = "";
          if (dia && vorm) {
            const t = vorm.textFrame.textRange;
            t.load("text");
            await ctx.sync().catch(() => undefined);
            const p = plaatshoudersIn(t.text ?? "")[0];
            if (p) {
              plek = `${dia}/${vorm.id}#0`;
              if (plek !== laatste) terugroep({ plek, plaatshouder: p.plaatshouder, voorvertoning: false });
            }
          }
          laatste = plek;
        }).catch(() => undefined);
      };
      Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, bij);
      return () => Office.context.document.removeHandlerAsync(Office.EventType.DocumentSelectionChanged, { handler: bij });
    };
  }

  get leesSelectie(): (() => Promise<string>) | undefined {
    if (!this.selecteren) return undefined;
    return async () =>
      PowerPoint.run(async (ctx) => {
        const r = ctx.presentation.getSelectedTextRangeOrNullObject();
        r.load("text");
        await ctx.sync();
        return schoonSelectie(r.isNullObject ? "" : r.text);
      });
  }

  leverBestand = (): Promise<Inhoud> => leesOfficeBestand("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "PowerPoint");
  schrijfAfdruk = (a: Afdruk) => schrijfAfdrukInBestand(a);
  leesAfdruk = () => leesAfdrukUitBestand();

  toon(melding: Melding): void {
    this.melden(melding);
  }
}
