// De Collabora-adapter met een nagebootst Collabora: zoeken en vervangen via
// .uno:ExecuteSearch, de html van het opgeslagen bestand via de integratielaag.
import { test } from "node:test";
import assert from "node:assert/strict";
import { CollaboraAdapter } from "../src/collabora/adapter.ts";

test("Collabora: plaatshouders via zoeken en vervangen, plekken uit het opgeslagen bestand", async () => {
  let doc = "Jan de Vries belde Jan. Janssen niet.";
  const opdrachten: string[] = [];
  const venster = {
    slaOp: async () => undefined,
    herlaad: async () => undefined,
    unoOpdracht: (opdracht: string, args: Record<string, { type: string; value: unknown }>) => {
      opdrachten.push(`${opdracht}:${args["SearchItem.Command"]!.value}`);
      if (args["SearchItem.Command"]!.value !== 3) return;
      const zoek = String(args["SearchItem.SearchString"]!.value);
      const naar = String(args["SearchItem.ReplaceString"]!.value).replace(/\\([&$])/g, "$1");
      const letterlijk = /\\Q([\s\S]*?)\\E/.exec(zoek)![1]!;
      const heel = zoek.startsWith("(?<!");
      const re = new RegExp(`${heel ? "(?<![\\p{L}\\p{N}_])" : ""}${letterlijk.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${heel ? "(?![\\p{L}\\p{N}_])" : ""}`, "gu");
      doc = doc.replace(re, () => naar);
    },
  };
  (globalThis as { fetch: typeof fetch }).fetch = (async () => new Response(JSON.stringify({ html: `<p>${doc}</p>` }))) as typeof fetch;
  const a = new CollaboraAdapter("w1", venster, () => undefined, "docx");
  assert.ok(a.werkomgeving().vermogens.includes("pii-markeren"));
  const nieuw = await a.markeerPii!([
    { van: "Jan", plaatshouder: "[PERSOON 2]", ppl: 1, voorvertoning: true },
    { van: "Jan de Vries", plaatshouder: "[PERSOON 1]", ppl: 1, voorvertoning: true },
  ]);
  assert.equal(doc, "[PERSOON 1] belde [PERSOON 2]. Janssen niet.");
  assert.deepEqual(nieuw.map((p) => p.plaatshouder).sort(), ["[PERSOON 1]", "[PERSOON 2]"]);
  const plekken = await a.leesPiiPlekken!();
  await a.herstelPii!([{ plek: plekken[1]!.plek, waarde: "Jan" }]);
  assert.equal(doc, "[PERSOON 1] belde Jan. Janssen niet.");
  a.toonPiiPlek!(plekken[0]!.plek);
  assert.equal(opdrachten.at(-1), ".uno:ExecuteSearch:0");
});
