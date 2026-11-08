import { plaatsPaneel } from "@digitaalgemeengoed/oa-paneel";
import "@digitaalgemeengoed/oa-paneel/style.css";
import { StructuurAdapter } from "../src/structuur-adapter";
import { LibreOfficeTekstverwerker } from "../src/libreoffice/tekstverwerker";
import { koppelSessie, statusbalk, zorgVoorInlog } from "../src/host/statusbalk";
import "./libreoffice.css";

/**
 * Deze pagina doet twee dingen voor LibreOffice op de eigen computer:
 *
 * - #aanmelden=<poort>&sleutel=<sleutel>: aanmelden voor het zijpaneel in
 *   Writer. Na het inloggen vraagt de pagina een sessiesleutel (zoals de
 *   Word-invoegtoepassing) en geeft die aan de extensie op 127.0.0.1.
 * - #brug=<poort>&sleutel=<sleutel>: het paneel in de browser, naast Writer.
 *
 * Poort en sleutel bewaren we alleen in dit tabblad (sessionStorage), zodat
 * inloggen of herladen ze niet kwijtraakt, en halen ze uit de adresbalk.
 */
const OPSLAG = "oa-libreoffice-brug";
const meld = statusbalk(document.getElementById("status")!);

interface Brug {
  soort: "brug" | "aanmelden";
  poort: number;
  sleutel: string;
}

function leesBrug(): Brug | null {
  const h = new URLSearchParams(location.hash.slice(1));
  const soort = h.get("aanmelden") ? "aanmelden" : h.get("brug") ? "brug" : null;
  if (soort && h.get("sleutel")) {
    const b: Brug = { soort, poort: Number(h.get(soort)), sleutel: h.get("sleutel")! };
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
    const b = w ? (JSON.parse(w) as Brug) : null;
    return b ? { ...b, soort: b.soort ?? "brug" } : null;
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
  if (brug.soort === "aanmelden") return aanmelden(brug);
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

/** De sessie voor het zijpaneel naar LibreOffice op deze computer. */
async function aanmelden(brug: Brug) {
  document.getElementById("document")!.textContent = "Aanmelden voor LibreOffice";
  const sessie = await koppelSessie();
  if (!sessie) {
    meld({ soort: "fout", tekst: "Er kon geen sessie worden gemaakt. Probeer opnieuw vanuit LibreOffice." });
    return;
  }
  try {
    const r = await fetch(`http://127.0.0.1:${brug.poort}/sessie`, {
      method: "POST",
      headers: { authorization: `Bearer ${brug.sleutel}`, "content-type": "application/json" },
      body: JSON.stringify({ sessie }),
    });
    const j = (await r.json().catch(() => ({}))) as { melding?: string };
    if (!r.ok) throw new Error(j.melding ?? `LibreOffice gaf fout ${r.status}`);
  } catch (e) {
    const tekst = e instanceof TypeError ? "LibreOffice wacht niet meer op deze aanmelding. Kies in het zijpaneel opnieuw Aanmelden." : (e as Error).message;
    meld({ soort: "fout", tekst });
    return;
  }
  try {
    sessionStorage.removeItem(OPSLAG);
  } catch {
    /* niets */
  }
  document.getElementById("aangemeld")!.hidden = false;
  meld({ soort: "succes", tekst: "Aangemeld" });
}

start();
