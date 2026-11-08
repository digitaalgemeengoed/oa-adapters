// Pakt de LibreOffice-extensie in als dist/web/libreoffice/office-assistent-basis.oxt.
// De integratielaag voegt bij het downloaden instellingen.json toe met haar
// eigen adres (route /libreoffice/office-assistent.oxt).
import { readdirSync, readFileSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { zipSync } from "fflate";

const bron = new URL("../libreoffice-extensie/", import.meta.url).pathname;
const doel = new URL("../dist/web/libreoffice/", import.meta.url).pathname;
const overslaan = new Set(["test", "__pycache__", ".pytest_cache", "README.md"]);

const bestanden = {};
function voegToe(map) {
  for (const naam of readdirSync(map)) {
    if (overslaan.has(naam)) continue;
    const pad = join(map, naam);
    if (statSync(pad).isDirectory()) voegToe(pad);
    else bestanden[relative(bron, pad).split(sep).join("/")] = readFileSync(pad);
  }
}
voegToe(bron);
mkdirSync(doel, { recursive: true });
writeFileSync(join(doel, "office-assistent-basis.oxt"), zipSync(bestanden, { level: 9 }));
console.log(`office-assistent-basis.oxt: ${Object.keys(bestanden).sort().join(", ")}`);
