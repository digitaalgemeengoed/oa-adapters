// De Excel- en PowerPoint-adapter met een nagebootst Office.js: geen echte
// Office, wel de echte regels van oa-services. Dit toetst de vorm van de html
// en de herstellingen; of Office.js zich zo gedraagt, toetst alleen een echte
// Excel of PowerPoint.
import { test } from "node:test";
import assert from "node:assert/strict";
import { DOMParser } from "linkedom";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { existsSync } from "node:fs";

type Vorm = { id: string; name: string; type: string; tekst?: string; plaats?: string; altTextDescription?: string; altTextTitle?: string };
const geselecteerd: string[] = [];

function verzameling<T>(items: T[], extra: Record<string, unknown> = {}) {
  return { items, load: () => undefined, ...extra };
}

function pptVorm(v: Vorm) {
  const range = { get text() { return v.tekst ?? ""; }, set text(t: string) { v.tekst = t; }, load() { return this; }, font: {} };
  return Object.assign(v, {
    load: () => undefined,
    placeholderFormat: { type: v.plaats, load() { return this; } },
    textFrame: { textRange: range },
  });
}

const dias: { id: string; vormen: Vorm[] }[] = [
  { id: "d1", vormen: [{ id: "a", name: "Title 1", type: "Placeholder", plaats: "Title", tekst: "Fietsenstalling" }, { id: "b", name: "Content 2", type: "Placeholder", plaats: "Body", tekst: "Waarom\rWat het kost" }] },
  { id: "d2", vormen: [{ id: "c", name: "Picture 1", type: "Image", altTextDescription: "" }] },
  { id: "d3", vormen: [{ id: "e", name: "Title 1", type: "Placeholder", plaats: "Title", tekst: "fietsenstalling" }] },
];

const pptCtx = () => ({
  sync: async () => undefined,
  presentation: {
    setSelectedSlides: (ids: string[]) => geselecteerd.push(...ids),
    slides: Object.assign(
      verzameling(dias.map((d) => ({ id: d.id, shapes: verzameling(d.vormen.map(pptVorm)) }))),
      {
        getItem: (id: string) => {
          const d = dias.find((x) => x.id === id)!;
          return {
            setSelectedShapes: (ids: string[]) => geselecteerd.push(...ids),
            shapes: {
              getItem: (vid: string) => pptVorm(d.vormen.find((v) => v.id === vid)!),
              addTextBox: (tekst: string) => {
                const v = pptVorm({ id: `n${d.vormen.length}`, name: "TextBox", type: "TextBox", tekst });
                d.vormen.unshift(v);
                return v;
              },
            },
          };
        },
      },
    ),
  },
});

const bladen: { id: string; name: string; waarden: unknown[][] | null; vormen: Vorm[]; grafieken: number }[] = [
  { id: "s1", name: "Blad1", waarden: [["Post", "Bedrag"], ["Bouw", 1250000]], vormen: [{ id: "p", name: "Picture 1", type: "Image" }], grafieken: 1 },
  { id: "s2", name: "Toelichting", waarden: null, vormen: [], grafieken: 0 },
];
const xlCtx = () => ({
  sync: async () => undefined,
  workbook: {
    worksheets: Object.assign(
      verzameling(
        bladen.map((b) => ({
          get id() { return b.id; },
          get name() { return b.name; },
          getUsedRangeOrNullObject: () => ({ isNullObject: !b.waarden, values: b.waarden ?? [], load: () => undefined }),
          charts: verzameling(Array.from({ length: b.grafieken }, () => ({}))),
          shapes: verzameling(b.vormen),
        })),
      ),
      {
        getItem: (id: string) => {
          const b = bladen.find((x) => x.id === id)!;
          return {
            set name(n: string) { b.name = n; },
            activate: () => geselecteerd.push(id),
            getRange: () => ({ select: () => undefined }),
            shapes: { getItem: (vid: string) => b.vormen.find((v) => v.id === vid)! },
          };
        },
      },
    ),
  },
});

const instellingen = new Map<string, unknown>();
Object.assign(globalThis, {
  DOMParser,
  Office: {
    context: {
      requirements: { isSetSupported: () => true },
      document: { settings: { set: (k: string, w: unknown) => instellingen.set(k, w), get: (k: string) => instellingen.get(k) ?? null, saveAsync: (cb: (r: unknown) => void) => cb({ status: "succeeded" }) } },
    },
    AsyncResultStatus: { Succeeded: "succeeded" },
  },
  PowerPoint: { run: (cb: (ctx: unknown) => Promise<unknown>) => cb(pptCtx()) },
  Excel: { run: (cb: (ctx: unknown) => Promise<unknown>) => cb(xlCtx()), ShapeType: { image: "Image" } },
});

// De regels uit een gebouwde oa-services ernaast (zoals in de werkplaats); anders overslaan.
const REGELS = resolve(import.meta.dirname, "../../oa-services/dist/toegankelijkheid.js");
const skip = existsSync(REGELS) ? false : "oa-services/dist ontbreekt";
const services = skip ? null : await import(pathToFileURL(REGELS).href);
const beoordeel = (html: string) => (services.beoordeelHtml(html) as { regel: string; ernst: string; plek: { pad: string; beschrijving: string } }[]).map((b) => [b.regel, b.plek.pad, b.ernst]).sort();
const { PowerPointAdapter } = await import("../src/office/powerpoint.ts");
const { ExcelAdapter } = await import("../src/office/excel.ts");

test("PowerPoint: dia's als secties, met de regels van oa-services", { skip }, async () => {
  const meldingen: string[] = [];
  const a = new PowerPointAdapter((m) => meldingen.push(m.tekst));
  const html = (await a.leverInhoud()).data;
  assert.ok(html.startsWith('<section data-oa="dia"><h2>Fietsenstalling</h2><ul><li>Waarom</li><li>Wat het kost</li></ul></section>'), html);
  assert.deepEqual(beoordeel(html), [
    ["WCAG 2.2 1.1.1", "body/1/0", "fout"],
    ["WCAG 2.2 2.4.2", "body/1", "fout"],
    ["WCAG 2.2 2.4.6", "body/2/0", "advies"],
  ]);
  // Zoals het paneel herstelt (oa-kern): titel als attribuut op de sectie, kop en alt als element.
  await a.vervangSegment({ pad: "body/1", beschrijving: "" }, '<section data-oa="dia" titel="Situatie ter plaatse"><img></section>');
  await a.leverInhoud();
  await a.vervangSegment({ pad: "body/2/0", beschrijving: "" }, "<h2>Fietsenstalling: planning</h2>");
  await a.leverInhoud();
  await a.vervangSegment({ pad: "body/1/1", beschrijving: "" }, '<img alt="Foto van de fietsen">');
  const na = (await a.leverInhoud()).data;
  assert.ok(na.includes('<section data-oa="dia"><h2>Situatie ter plaatse</h2><img alt="Foto van de fietsen"></section>'), na);
  assert.deepEqual(beoordeel(na), []);
  a.toonPlek!({ pad: "body/0/1", beschrijving: "" });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(geselecteerd.splice(0), ["d1", "b"]);
  await assert.rejects(a.vervangSegment!({ pad: "body/0/1", beschrijving: "" }, "<ul><li>x</li></ul>"), /met de hand/);
  assert.deepEqual(meldingen, []);
});

test("Excel: bladen als secties, hernoemen en alternatieve tekst", { skip }, async () => {
  const meldingen: string[] = [];
  const a = new ExcelAdapter((m) => meldingen.push(m.tekst));
  const html = (await a.leverInhoud()).data;
  assert.equal(html, '<section data-oa="blad"><h2>Blad1</h2><table><tbody><tr><td>Post</td><td>Bedrag</td></tr><tr><td>Bouw</td><td>1250000</td></tr></tbody></table><img></section>\n<section data-oa="blad"><h2>Toelichting</h2></section>');
  assert.match(meldingen[0], /1 grafiek/);
  assert.deepEqual(beoordeel(html), [["WCAG 2.2 1.1.1", "body/0/2", "fout"], ["WCAG 2.2 2.4.6", "body/0/0", "advies"]]);
  await assert.rejects(a.vervangSegment({ pad: "body/0/0", beschrijving: "" }, "<h2>Kosten: bouw</h2>"), /31 tekens/);
  await a.vervangSegment({ pad: "body/0/0", beschrijving: "" }, "<h2>Begroting 2027</h2>");
  await a.vervangSegment({ pad: "body/0/2", beschrijving: "" }, '<img alt="Kaart van het Stationsplein">');
  assert.deepEqual(beoordeel((await a.leverInhoud()).data), []);
  await a.schrijfAfdruk!({ id: "x" } as never);
  assert.deepEqual(await a.leesAfdruk!(), { id: "x" });
});
