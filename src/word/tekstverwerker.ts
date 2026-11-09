/// <reference types="office-js" />
import type { Inhoud } from "@digitaalgemeengoed/oa-contract";
import type { Tekstverwerker } from "../structuur-adapter.js";
import { groepeer, niveauUitStijl, type Blok, type Doel, type Inline, type Opdracht, type RuweAlinea, type Tabel } from "../semantisch.js";

/**
 * Microsoft Word via Office.js (WordApi 1.3): Word op Windows en Mac en
 * Word voor het web. Leest alinea's met hun stijl, lijsten, tabellen,
 * afbeeldingen en links, en voert herstellingen uit als stijl- of
 * eigenschapswijziging, zodat de opmaak blijft staan.
 */
export class WordTekstverwerker implements Tekstverwerker {
  readonly id = "word";
  readonly naam = "Microsoft Word";

  async leesBlokken(): Promise<Blok[]> {
    return Word.run(async (ctx) => {
      const ps = ctx.document.body.paragraphs;
      ps.load("items/text,items/styleBuiltIn,items/style,items/outlineLevel,items/tableNestingLevel,items/isListItem,items/font/bold,items/font/underline");
      const tabellen = ctx.document.body.tables;
      tabellen.load("items/values,items/headerRowCount,items/nestingLevel");
      await ctx.sync();

      const extra = ps.items.map((p) => {
        if (p.tableNestingLevel > 0) return null;
        const afbeeldingen = p.inlinePictures;
        afbeeldingen.load("items/altTextDescription");
        const links = p.getRange().getHyperlinkRanges();
        links.load("items/text,items/hyperlink");
        const lijst = p.listItemOrNullObject;
        lijst.load("listString");
        return { afbeeldingen, links, lijst };
      });
      await ctx.sync();

      const bovenste = tabellen.items.filter((t) => t.nestingLevel === 1);
      let volgendeTabel = 0;
      let inTabel = false;
      const reeks: (RuweAlinea | Tabel)[] = [];

      ps.items.forEach((p, i) => {
        if (p.tableNestingLevel > 0) {
          if (!inTabel) {
            const t = bovenste[volgendeTabel];
            if (t) reeks.push({ soort: "tabel", bron: volgendeTabel, rijen: t.values, kopregels: t.headerRowCount ?? 0 });
            volgendeTabel++;
            inTabel = true;
          }
          return;
        }
        inTabel = false;
        const x = extra[i]!;
        const inline: Inline[] = [
          ...x.links.items.map((l, index) => ({ soort: "link" as const, tekst: l.text, href: l.hyperlink ?? "", index })),
          ...x.afbeeldingen.items.map((a, index) => ({ soort: "afbeelding" as const, alt: a.altTextDescription ?? "", index })),
        ];
        const tekst = p.text.replace(/[\r\u000b]/g, " ").trim();
        if (!tekst && inline.length === 0) return;
        const lijsttekst = p.isListItem && !x.lijst.isNullObject ? x.lijst.listString : null;
        reeks.push({
          bron: i,
          niveau: niveauUitStijl(p.styleBuiltIn === "Other" ? p.style : p.styleBuiltIn, p.outlineLevel),
          tekst,
          vet: p.font.bold === true,
          onderstreept: !!p.font.underline && p.font.underline !== "None",
          inline,
          lijst: lijsttekst !== null ? { genummerd: /^(\d+|[a-zA-Z]{1,3}|[ivxlcIVXLC]+)[.)]$|^\d+$/.test(lijsttekst.trim()) } : null,
        });
      });
      return groepeer(reeks);
    });
  }

  async voerUit(o: Opdracht): Promise<void> {
    await Word.run(async (ctx) => {
      const ps = ctx.document.body.paragraphs;
      ps.load("items/text");
      const tabellen = ctx.document.body.tables;
      tabellen.load("items/nestingLevel");
      await ctx.sync();

      const alinea = (index: number, verwacht: string) => {
        const p = ps.items[index];
        if (!p || p.text.replace(/[\r\u000b]/g, " ").trim() !== verwacht) {
          throw new Error("Het document is intussen gewijzigd. Beoordeel opnieuw.");
        }
        return p;
      };

      switch (o.soort) {
        case "niveau": {
          const p = alinea(o.alinea, o.tekst);
          p.styleBuiltIn = (o.niveau ? `Heading${o.niveau}` : "Normal") as Word.BuiltInStyleName;
          break;
        }
        case "tabelkop": {
          const t = tabellen.items.filter((x) => x.nestingLevel === 1)[o.tabel];
          if (!t) throw new Error("De tabel is niet meer gevonden. Beoordeel opnieuw.");
          t.headerRowCount = 1;
          break;
        }
        case "alt": {
          const beelden = alinea(o.alinea, o.tekst).inlinePictures;
          beelden.load("items");
          await ctx.sync();
          const b = beelden.items[o.afbeelding];
          if (!b) throw new Error("De afbeelding is niet meer gevonden. Beoordeel opnieuw.");
          b.altTextDescription = o.alt;
          break;
        }
        case "linktekst": {
          const links = alinea(o.alinea, o.alineatekst).getRange().getHyperlinkRanges();
          links.load("items/hyperlink");
          await ctx.sync();
          const l = links.items[o.link];
          if (!l) throw new Error("De link is niet meer gevonden. Beoordeel opnieuw.");
          const adres = l.hyperlink || o.href;
          const nieuw = l.insertText(o.tekst, "Replace");
          nieuw.hyperlink = adres;
          break;
        }
      }
      await ctx.sync();
    });
  }

  async toon(doel: Doel): Promise<void> {
    await Word.run(async (ctx) => {
      const ps = ctx.document.body.paragraphs;
      ps.load("items");
      const tabellen = ctx.document.body.tables;
      tabellen.load("items/nestingLevel");
      await ctx.sync();
      if (doel.soort === "tabel") {
        tabellen.items.filter((t) => t.nestingLevel === 1)[doel.tabel]?.select();
      } else if (doel.soort === "alinea") {
        ps.items[doel.alinea]?.select();
      } else if (doel.soort === "afbeelding") {
        const b = ps.items[doel.alinea]?.inlinePictures;
        if (b) {
          b.load("items");
          await ctx.sync();
          b.items[doel.afbeelding]?.select();
        }
      } else {
        const l = ps.items[doel.alinea]?.getRange().getHyperlinkRanges();
        if (l) {
          l.load("items");
          await ctx.sync();
          l.items[doel.link]?.select();
        }
      }
      await ctx.sync();
    });
  }

  async vervangAlles(html: string): Promise<void> {
    await Word.run(async (ctx) => {
      ctx.document.body.insertHtml(html, "Replace");
      await ctx.sync();
    });
  }

  /** Het document als .docx (Office.FileType.Compressed), in stukken gelezen. */
  leesBestand(): Promise<Inhoud> {
    return new Promise((klaar, mis) => {
      Office.context.document.getFileAsync(Office.FileType.Compressed, { sliceSize: 4 * 1024 * 1024 }, (r) => {
        if (r.status !== Office.AsyncResultStatus.Succeeded) return mis(new Error(`Word kon het bestand niet opleveren: ${r.error.message}`));
        const bestand = r.value;
        const stukken: Uint8Array[] = [];
        const lees = (i: number) =>
          bestand.getSliceAsync(i, (s) => {
            if (s.status !== Office.AsyncResultStatus.Succeeded) {
              bestand.closeAsync();
              return mis(new Error(`Word kon het bestand niet opleveren: ${s.error.message}`));
            }
            stukken.push(new Uint8Array(s.value.data as number[]));
            if (i + 1 < bestand.sliceCount) return lees(i + 1);
            bestand.closeAsync();
            klaar({
              formaat: "docx",
              mediaType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              codering: "base64",
              data: naarBase64(stukken),
            });
          });
        lees(0);
      });
    });
  }

  /** Zoeken en vervangen als heel woord; de opmaak van de vervangen tekst blijft staan. */
  async vervangTekst(paren: { van: string; naar: string }[]): Promise<number> {
    return Word.run(async (ctx) => {
      const vondsten = paren
        .filter((p) => p.van.length <= 255) // grens van body.search
        .map((p) => {
          // ^ is in Word ook zonder jokertekens een stuurteken (^p, ^t).
          const r = ctx.document.body.search(p.van.replace(/\^/g, "^^"), { matchCase: true, matchWholeWord: true });
          r.load("items");
          return { p, r };
        });
      await ctx.sync();
      let aantal = 0;
      for (const { p, r } of vondsten)
        for (const bereik of r.items) {
          bereik.insertText(p.naar, "Replace");
          aantal++;
        }
      await ctx.sync();
      return aantal;
    });
  }

  async leesSelectie(): Promise<string> {
    return Word.run(async (ctx) => {
      const sel = ctx.document.getSelection();
      sel.load("text");
      await ctx.sync();
      return sel.text;
    });
  }

  async leesEigenschap(naam: string): Promise<string | null> {
    return Word.run(async (ctx) => {
      const p = ctx.document.properties.customProperties.getItemOrNullObject(naam);
      p.load("value");
      await ctx.sync();
      return p.isNullObject ? null : String(p.value);
    });
  }

  async schrijfEigenschap(naam: string, waarde: string): Promise<void> {
    await Word.run(async (ctx) => {
      // Een eigen eigenschap van Word mag hoogstens 255 tekens zijn.
      ctx.document.properties.customProperties.add(naam, waarde.slice(0, 255));
      await ctx.sync();
    });
  }
}

function naarBase64(stukken: Uint8Array[]): string {
  let binair = "";
  for (const s of stukken) for (let i = 0; i < s.length; i += 0x8000) binair += String.fromCharCode(...s.subarray(i, i + 0x8000));
  return btoa(binair);
}
