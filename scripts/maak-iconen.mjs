// Maakt de pictogrammen van de assistentknoppen voor werkbalken buiten het
// paneel, uit dezelfde tekeningen als het paneel (oa-paneel/src/modules.tsx):
//   statisch/iconen/<id>.svg           Collabora (Insert_Button, vanaf ons eigen adres)
//   statisch/iconen/<id>-<n>.png       Office-lint (16, 32, 80)
//   libreoffice-extensie/icons/oa-<id>-{16,26}.png   werkbalk van LibreOffice
// Alleen nodig als een tekening verandert; het resultaat staat in git.
// Gebruik (in de werkplaats, met oa-paneel ernaast en rsvg-convert):
//   node --import tsx scripts/maak-iconen.mjs
import { mkdir, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { icoonSvg, MODULES } from "../../oa-paneel/src/modules.tsx";

const EXTRA = {
  paneel: "M2.5 3h11v10h-11zM9.5 3v10",
  beoordelen: "M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM10.5 10.5l3 3",
  "anon-selectie": "M2 4.5h12M2 11.5h12M3.5 6.5h9v3h-9z",
};
const svg = (pad, kleur) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 16 16" fill="none" stroke="${kleur}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="${pad}"/></svg>`;

const KLEUR = "#2b4b6f";
const iconen = {
  ...Object.fromEntries(Object.entries(EXTRA).map(([id, pad]) => [id, svg(pad, KLEUR)])),
  ...Object.fromEntries(MODULES.filter((m) => m.id !== "help").map((m) => [m.id, icoonSvg(m.id, KLEUR, 24)])),
};

const web = resolve("statisch/iconen");
const lo = resolve("libreoffice-extensie/icons");
await mkdir(web, { recursive: true });
for (const [id, inhoud] of Object.entries(iconen)) {
  const bestand = resolve(web, `${id}.svg`);
  await writeFile(bestand, inhoud);
  for (const n of [16, 32, 80]) execFileSync("rsvg-convert", ["-w", String(n), "-h", String(n), "-o", resolve(web, `${id}-${n}.png`), bestand]);
  for (const n of [16, 26]) execFileSync("rsvg-convert", ["-w", String(n), "-h", String(n), "-o", resolve(lo, `oa-${id}-${n}.png`), bestand]);
}
console.log(`pictogrammen: ${Object.keys(iconen).join(", ")}`);
