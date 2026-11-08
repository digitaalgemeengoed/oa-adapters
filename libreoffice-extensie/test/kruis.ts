// Draait de TypeScript-kant op test/kruis.json; test_kern.py vergelijkt met Python.
import { readFileSync } from "node:fs";
import { parseHTML } from "linkedom";
import { groepeer, naarHtml, plekNaarDoel, segmentNaarOpdracht, NietUitvoerbaar } from "../../src/semantisch.ts";
import { metadateren, toegankelijkheid } from "@digitaalgemeengoed/oa-kern";

const f = JSON.parse(readFileSync(new URL("./kruis.json", import.meta.url), "utf8"));
const fragment = (html: string) => parseHTML(`<!doctype html><html><body><template>${html}</template></body></html>`).document.querySelector("template")!.content as unknown as { firstElementChild: Element | null };
const parser = (html: string) => parseHTML(`<!doctype html><html><body>${html}</body></html>`).document as unknown as Document;
const blokken = groepeer(f.reeks);
const probeer = (fn: () => unknown) => {
  try {
    return fn();
  } catch (e) {
    if (e instanceof NietUitvoerbaar) return { fout: e.message };
    throw e;
  }
};
const uit = {
  html: naarHtml(blokken),
  segmenten: f.segmenten.map(([p, h]: [string, string]) => probeer(() => segmentNaarOpdracht(blokken, p, h, fragment))),
  doelen: f.doelen.map((p: string) => plekNaarDoel(blokken, p)),
  herstel: f.bevindingen.map(([b, a]: [never, string | null]) =>
    probeer(() => {
      const w = toegankelijkheid.wijzigingVoor(b, a ?? undefined);
      const r = toegankelijkheid.pasToe(parser, naarHtml(blokken), (b as { plek: never }).plek, w!);
      return segmentNaarOpdracht(blokken, (b as { plek: { pad: string } }).plek.pad, r.element, fragment);
    }),
  ),
  velden: metadateren.velden(f.objecttype),
  ontbrekend: metadateren.bevindingen(f.objecttype, f.metadata),
  suggesties: metadateren.suggesties(f.inhoud, f.metadata),
  meerSuggesties: f.inhouden.map((i: never) => metadateren.suggesties(i, {})),
};
process.stdout.write(JSON.stringify(uit));
