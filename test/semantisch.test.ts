// De omzetting tussen de structuur van een tekstverwerker en html, en de
// StructuurAdapter, met een nagebootste tekstverwerker. Zonder Word of
// LibreOffice; die doen alleen het lezen en uitvoeren.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseHTML } from "linkedom";
import { groepeer, naarHtml, segmentNaarOpdracht, plekNaarDoel, niveauUitStijl, type Blok, type Opdracht, type MaakFragment } from "../src/semantisch.ts";
import { StructuurAdapter, type Tekstverwerker } from "../src/structuur-adapter.ts";

const fragment: MaakFragment = (html) => {
  const { document } = parseHTML(`<!doctype html><html><body><template>${html}</template></body></html>`);
  return (document.querySelector("template") as unknown as HTMLTemplateElement).content ?? document.querySelector("template")!;
};

const voorbeeld = (): Blok[] =>
  groepeer([
    { bron: 0, niveau: 1, tekst: "Raadsvoorstel fietsenstalling" },
    { bron: 1, niveau: 0, tekst: "Aanleiding", vet: true },
    { bron: 2, niveau: 3, tekst: "Kosten" },
    { bron: 3, niveau: 0, tekst: "Zie de begroting, klik hier voor meer.", inline: [{ soort: "link", tekst: "klik hier", href: "https://example.org/b", index: 0 }, { soort: "afbeelding", alt: "", index: 0 }] },
    { bron: 4, niveau: 0, tekst: "Eerste punt", lijst: { genummerd: false } },
    { bron: 5, niveau: 0, tekst: "Tweede punt", lijst: { genummerd: false } },
    { soort: "tabel", bron: 0, rijen: [["Post", "Bedrag"], ["Bouw", "120.000"]], kopregels: 0 },
    { bron: 9, niveau: 0, tekst: "Twee keer hier: hier en hier.", inline: [{ soort: "link", tekst: "hier", href: "https://b", index: 1 }, { soort: "link", tekst: "hier", href: "https://a", index: 0 }] },
  ]);

test("blokken worden semantische html, lijstitems één lijst", () => {
  const html = naarHtml(voorbeeld());
  assert.equal(
    html,
    [
      "<h1>Raadsvoorstel fietsenstalling</h1>",
      "<p><strong>Aanleiding</strong></p>",
      "<h3>Kosten</h3>",
      '<p>Zie de begroting, <a href="https://example.org/b">klik hier</a> voor meer.<img></p>',
      "<ul><li>Eerste punt</li><li>Tweede punt</li></ul>",
      "<table><tbody><tr><td>Post</td><td>Bedrag</td></tr><tr><td>Bouw</td><td>120.000</td></tr></tbody></table>",
      '<p>Twee keer <a href="https://a">hier</a>: <a href="https://b">hier</a> en hier.</p>',
    ].join("\n"),
  );
});

test("tekst wordt ge-escaped", () => {
  assert.equal(naarHtml(groepeer([{ bron: 0, niveau: 0, tekst: "a < b & <script>" }])), "<p>a &lt; b &amp; &lt;script&gt;</p>");
});

test("kop, tabelkop, alt en linktekst worden opdrachten", () => {
  const b = voorbeeld();
  assert.deepEqual(segmentNaarOpdracht(b, "body/1", "<h2>Aanleiding</h2>", fragment), { soort: "niveau", alinea: 1, niveau: 2, tekst: "Aanleiding" });
  assert.deepEqual(segmentNaarOpdracht(b, "body/2", "<h2>Kosten</h2>", fragment), { soort: "niveau", alinea: 2, niveau: 2, tekst: "Kosten" });
  assert.deepEqual(segmentNaarOpdracht(b, "body/5", "<table><thead><tr><th>Post</th></tr></thead></table>", fragment), { soort: "tabelkop", tabel: 0 });
  assert.deepEqual(segmentNaarOpdracht(b, "body/3/1", '<img alt="Plattegrond">', fragment), { soort: "alt", alinea: 3, afbeelding: 0, alt: "Plattegrond", tekst: "Zie de begroting, klik hier voor meer." });
  assert.deepEqual(segmentNaarOpdracht(b, "body/3/0", '<a href="https://example.org/b">Begroting 2027</a>', fragment), {
    soort: "linktekst", alinea: 3, link: 0, tekst: "Begroting 2027", href: "https://example.org/b", alineatekst: "Zie de begroting, klik hier voor meer.",
  });
  // De tweede <a> in de html is de link met index 1 in Word.
  assert.equal((segmentNaarOpdracht(b, "body/6/1", '<a href="https://b">x</a>', fragment) as { link: number }).link, 1);
});

test("wat niet uit te voeren is, zegt dat", () => {
  assert.throws(() => segmentNaarOpdracht(voorbeeld(), "body/4", "<ol><li>x</li></ol>", fragment), /nog niet automatisch/);
  assert.throws(() => segmentNaarOpdracht(voorbeeld(), "body/40", "<p>x</p>", fragment), /niet meer gevonden/);
});

test("plekken worden doelen om te tonen", () => {
  const b = voorbeeld();
  assert.deepEqual(plekNaarDoel(b, "body/5"), { soort: "tabel", tabel: 0 });
  assert.deepEqual(plekNaarDoel(b, "body/3/1"), { soort: "afbeelding", alinea: 3, afbeelding: 0 });
  assert.deepEqual(plekNaarDoel(b, "body/4/1"), { soort: "alinea", alinea: 5 });
});

test("kopstijlen in Word en LibreOffice", () => {
  assert.equal(niveauUitStijl("Heading2"), 2);
  assert.equal(niveauUitStijl("Heading 3"), 3);
  assert.equal(niveauUitStijl("Kop 2"), 2);
  assert.equal(niveauUitStijl("Title"), 1);
  assert.equal(niveauUitStijl("Normal", 10), 0);
  assert.equal(niveauUitStijl("Eigen stijl", 2), 2);
});

class NepTekstverwerker implements Tekstverwerker {
  id = "nep";
  naam = "Nep";
  uitgevoerd: Opdracht[] = [];
  eigenschappen = new Map<string, string>();
  async leesBlokken() { return voorbeeld(); }
  async voerUit(o: Opdracht) { this.uitgevoerd.push(o); }
  async toon() {}
  async vervangAlles() {}
  async leesEigenschap(n: string) { return this.eigenschappen.get(n) ?? null; }
  async schrijfEigenschap(n: string, w: string) { this.eigenschappen.set(n, w); }
}

test("StructuurAdapter: html, segment als opdracht, afdruk in de eigenschappen", async () => {
  const tv = new NepTekstverwerker();
  const meldingen: string[] = [];
  const a = new StructuurAdapter(tv, (m) => meldingen.push(m.tekst), fragment);
  assert.deepEqual(a.werkomgeving().vermogens.sort(), ["afdruk-schrijven", "inhoud-opleveren", "inhoud-vervangen", "plek-tonen", "segment-vervangen", "tonen"].sort());
  const inhoud = await a.leverInhoud();
  assert.match(inhoud.data, /<h3>Kosten<\/h3>/);
  await a.vervangSegment({ pad: "body/2", beschrijving: "Kop" }, "<h2>Kosten</h2>");
  assert.deepEqual(tv.uitgevoerd, [{ soort: "niveau", alinea: 2, niveau: 2, tekst: "Kosten" }]);
  await a.schrijfAfdruk({ identificatie: "x", versie: 2, objecttype: "document" });
  assert.deepEqual(await a.leesAfdruk(), { identificatie: "x", versie: 2, objecttype: "document" });
  await assert.rejects(a.vervangSegment({ pad: "body/4", beschrijving: "Lijst" }, "<ol></ol>"), /nog niet automatisch/);
});
