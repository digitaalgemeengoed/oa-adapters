import { plaatsPaneel, type Opdracht } from "@digitaalgemeengoed/oa-paneel";
import "@digitaalgemeengoed/oa-paneel/style.css";
import { StructuurAdapter } from "../src/structuur-adapter";
import { LibreOfficeTekstverwerker } from "../src/libreoffice/tekstverwerker";
import { LibreOfficeBladenAdapter } from "../src/libreoffice/bladen";
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
// In de zijbalk alleen een regel als er iets te melden is.
const meld = statusbalk(document.getElementById("status")!, /[#&]ingebed=1/.test(location.hash) ? "" : "Gereed");

interface Brug {
  soort: "brug" | "aanmelden";
  poort: number;
  sleutel: string;
  /** In de webweergave in de zijbalk van Writer: zonder kopbalk, over de volle breedte. */
  ingebed?: boolean;
}

function leesBrug(): Brug | null {
  const h = new URLSearchParams(location.hash.slice(1));
  const soort = h.get("aanmelden") ? "aanmelden" : h.get("brug") ? "brug" : null;
  if (soort && h.get("sleutel")) {
    const b: Brug = { soort, poort: Number(h.get(soort)), sleutel: h.get("sleutel")!, ingebed: h.get("ingebed") === "1" };
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
  if (brug?.ingebed) {
    document.documentElement.classList.add("ingebed");
    document.body.classList.add("ingebed");
  }
  if (!brug || !Number.isInteger(brug.poort)) {
    document.getElementById("uitleg")!.hidden = false;
    return;
  }
  if (!(await zorgVoorInlog())) return;
  if (brug.soort === "aanmelden") return aanmelden(brug);
  const tv = new LibreOfficeTekstverwerker(brug.poort, brug.sleutel);
  let soort: "tekst" | "rekenblad" | "presentatie" = "tekst";
  let extensieVersie = "0";
  try {
    const s = await tv.status();
    soort = s.soort ?? "tekst";
    extensieVersie = s.versie;
    const app = soort === "rekenblad" ? "LibreOffice Calc" : soort === "presentatie" ? "LibreOffice Impress" : "LibreOffice Writer";
    document.getElementById("document")!.textContent = `${app} — ${s.naam}`;
    document.title = `${s.naam} — Office Assistent`;
  } catch (e) {
    meld({ soort: "fout", tekst: (e as Error).message });
    document.getElementById("uitleg")!.hidden = false;
    return;
  }
  // Anonimiseren in het document vraagt extensie 0.10.0 of nieuwer; met een oudere werkt het zoals vroeger (voorbeeld in het paneel).
  const nodig = soort === "tekst" ? "0.10.0" : "0.11.0";
  if (!nieuwerOfGelijk(extensieVersie, nodig)) {
    const t = tv as unknown as Record<string, undefined>;
    for (const m of ["markeerPii", "leesPiiPlekken", "herstelPii", "zetPiiDefinitief", "toonPiiPlek", "bijPiiKlik"]) t[m] = undefined;
    meld({ soort: "info", tekst: `Je LibreOffice-extensie is versie ${extensieVersie}. Installeer de nieuwe (zie de startpagina) om in het document zelf te anonimiseren.` });
  }
  // Herkleuren (andere grondslag) vraagt 0.13.2; zonder zet de kern de plekken terug en markeert ze opnieuw.
  if (!nieuwerOfGelijk(extensieVersie, "0.13.2")) (tv as unknown as Record<string, undefined>).herkleurPii = undefined;
  const adapter = soort === "tekst" ? new StructuurAdapter(tv, meld) : new LibreOfficeBladenAdapter(tv, soort, meld);
  // In de zijbalk van LibreOffice staan rechts al de tabbladen van de zijbalk zelf: de knoppen van de modules dan bovenaan.
  // Een knop in de werkbalk Assistent van LibreOffice die al was ingedrukt voordat het paneel er stond.
  const wacht = (window as { __oaWacht?: Opdracht }).__oaWacht;
  plaatsPaneel(document.getElementById("paneel")!, adapter, { knoppen: brug.ingebed ? "boven" : "rechts", module: wacht });
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

/** Is versie a gelijk aan of nieuwer dan b (x.y.z)? */
function nieuwerOfGelijk(a: string, b: string): boolean {
  const x = a.split(".").map((d) => Number.parseInt(d, 10) || 0);
  const y = b.split(".").map((d) => Number.parseInt(d, 10) || 0);
  for (let i = 0; i < 3; i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0);
  return true;
}
