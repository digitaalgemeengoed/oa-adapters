import { plaatsPaneel } from "@digitaalgemeengoed/oa-paneel";
import "@digitaalgemeengoed/oa-paneel/style.css";
import { StructuurAdapter } from "../src/structuur-adapter";
import { LibreOfficeTekstverwerker } from "../src/libreoffice/tekstverwerker";
import { statusbalk, zorgVoorInlog } from "../src/host/statusbalk";
import "./libreoffice.css";

/**
 * Het paneel naast LibreOffice op de eigen computer. LibreOffice opent deze
 * pagina met #brug=<poort>&sleutel=<sleutel>. Die bewaren we alleen in dit
 * tabblad (sessionStorage), zodat inloggen of herladen ze niet kwijtraakt,
 * en halen ze uit de adresbalk.
 */
const OPSLAG = "oa-libreoffice-brug";
const meld = statusbalk(document.getElementById("status")!);

function leesBrug(): { poort: number; sleutel: string } | null {
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("brug") && h.get("sleutel")) {
    const b = { poort: Number(h.get("brug")), sleutel: h.get("sleutel")! };
    try {
      sessionStorage.setItem(OPSLAG, JSON.stringify(b));
    } catch {
      /* geen opslag: dan alleen voor nu */
    }
    history.replaceState(null, "", location.pathname);
    return b;
  }
  try {
    const w = sessionStorage.getItem(OPSLAG);
    return w ? (JSON.parse(w) as { poort: number; sleutel: string }) : null;
  } catch {
    return null;
  }
}

async function start() {
  const brug = leesBrug();
  if (!brug || !Number.isInteger(brug.poort)) {
    document.getElementById("uitleg")!.hidden = false;
    return;
  }
  if (!(await zorgVoorInlog())) return;
  const tv = new LibreOfficeTekstverwerker(brug.poort, brug.sleutel);
  try {
    const s = await tv.status();
    document.getElementById("document")!.textContent = `LibreOffice Writer — ${s.naam}`;
    document.title = `${s.naam} — Office Assistent`;
  } catch (e) {
    meld({ soort: "fout", tekst: (e as Error).message });
    document.getElementById("uitleg")!.hidden = false;
    return;
  }
  plaatsPaneel(document.getElementById("paneel")!, new StructuurAdapter(tv, meld));
}

start();
