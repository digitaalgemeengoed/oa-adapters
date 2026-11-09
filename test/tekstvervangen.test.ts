import { test } from "node:test";
import assert from "node:assert/strict";
import { DOMParser, Event as DomEvent } from "linkedom";
import { icuPatroon, icuVervanging, ordenParen, telInHtml, vervangInTekst } from "../src/tekstvervangen.ts";
import { DemoEditorAdapter } from "../src/demo-editor/adapter.ts";

// Het Event van linkedom; dat van Node past niet op linkedom-elementen.
globalThis.Event = DomEvent as unknown as typeof Event;

const PAREN = [
  { van: "Jan", naar: "[PERSOON 2]" },
  { van: "Jan de Vries", naar: "[PERSOON 1]" },
  { van: "Ève", naar: "[PERSOON 3]" },
];

test("hele woorden, langste eerst, ook met letters met accent", () => {
  const r = vervangInTekst("Jan de Vries, Janssen, Jan_x, Jan. Ève en Èveline", PAREN);
  assert.equal(r.tekst, "[PERSOON 1], Janssen, Jan_x, [PERSOON 2]. [PERSOON 3] en Èveline");
  assert.equal(r.aantal, 3);
  assert.deepEqual(ordenParen([...PAREN, { van: "Jan", naar: "x" }, { van: " ", naar: "y" }]).map((p) => p.van), ["Jan de Vries", "Jan", "Ève"]);
  assert.equal(vervangInTekst("a.b a+b", [{ van: "a.b", naar: "X" }]).tekst, "X a+b");
});

test("ICU-patroon en vervangtekst voor LibreOffice en Collabora", () => {
  assert.equal(icuPatroon("a\\Eb"), "(?<![\\p{L}\\p{N}_])\\Qa\\E\\\\E\\Qb\\E(?![\\p{L}\\p{N}_])");
  assert.equal(icuVervanging("[X] & $1"), "[X] \\& \\$1");
  assert.throws(() => icuVervanging("a\\b"), /backslash/);
  assert.equal(telInHtml("<p>Jan de <b>Vries</b> en Jan &amp; Ève</p>", PAREN), 3);
});

test("demo-tekstverwerker: vervangt in de tekst en leest de selectie", async () => {
  const doc = new DOMParser().parseFromString("<html><body><div id=e><p>Gesprek met <b>Jan de Vries</b>.</p><p>Janssen belde Jan.</p></div></body></html>", "text/html");
  const editor = doc.getElementById("e") as unknown as HTMLElement;
  let invoer = 0;
  editor.addEventListener("input", () => invoer++);
  const sel = { isCollapsed: false, anchorNode: editor.firstChild, toString: () => "  Jan\n de Vries " };
  (doc as unknown as { getSelection: () => unknown }).getSelection = () => sel;
  const opslag = { leesEigenschap: () => null, schrijfEigenschap: () => undefined };
  const a = new DemoEditorAdapter(editor, opslag, () => undefined);
  assert.equal(await a.vervangTekst!(PAREN), 2);
  assert.equal(editor.innerHTML, "<p>Gesprek met <b>[PERSOON 1]</b>.</p><p>Janssen belde [PERSOON 2].</p>");
  assert.equal(invoer, 1);
  assert.equal(await a.leesSelectie!(), "Jan de Vries");
  assert.equal(new DemoEditorAdapter(editor, opslag, () => undefined, "beperkt").vervangTekst, undefined);
});
