import type { Melding } from "@digitaalgemeengoed/oa-contract";

/** Een statusregel van de werkomgeving, voor meldingen van de adapter. */
export function statusbalk(el: HTMLElement, rust = "Gereed"): (m: Melding) => void {
  let timer: number | undefined;
  el.textContent = rust;
  return (m) => {
    el.textContent = m.tekst;
    el.dataset.soort = m.soort;
    clearTimeout(timer);
    timer = window.setTimeout(() => {
      el.textContent = rust;
      delete el.dataset.soort;
    }, m.soort === "fout" || m.soort === "waarschuwing" ? 8000 : 4000);
  };
}

const LUS = "oa-inlog-gestuurd";

/**
 * Is er een sessie (cookie)? Zo niet: naar het inloggen, met terugkeer naar
 * deze pagina. Lukt dat niet, dan een melding met een knop in plaats van een
 * leeg paneel:
 * - de server is niet bereikbaar (geen netwerk, server wordt bijgewerkt);
 * - net ingelogd en toch geen sessie: het cookie wordt niet bewaard (anders
 *   zouden we eindeloos heen en weer gaan).
 */
export async function zorgVoorInlog(plek: HTMLElement = document.body): Promise<boolean> {
  let r: Response;
  try {
    r = await fetch("/api/lees/wie-ben-ik", { credentials: "same-origin" });
  } catch {
    toonProbleem(plek, "De server van de assistent is nu niet bereikbaar. Controleer je internetverbinding; wordt de server bijgewerkt, probeer het dan over een minuut opnieuw.");
    return false;
  }
  if (r.status === 401) {
    const vorige = Number(leesSessie(LUS) ?? 0);
    if (Date.now() - vorige < 60_000) {
      zetSessie(LUS, null);
      toonProbleem(
        plek,
        "Je bent ingelogd, maar deze omgeving onthoudt dat niet: het inlogcookie wordt niet bewaard. Sta cookies toe voor deze site (ook in een privévenster) en probeer opnieuw.",
      );
      return false;
    }
    zetSessie(LUS, String(Date.now()));
    location.href = inlogAdres();
    return false;
  }
  if (!r.ok) {
    toonProbleem(plek, `De server van de assistent gaf een fout (${r.status}). Probeer het zo opnieuw; blijft het zo, meld het dan bij de beheerder.`);
    return false;
  }
  zetSessie(LUS, null);
  return true;
}

/** Het adres om (opnieuw) in te loggen en daarna hier terug te komen. */
export function inlogAdres(): string {
  return `/api/auth/login?terug=${encodeURIComponent(location.pathname + location.search)}`;
}

/** Een blijvende melding met een knop om het opnieuw te proberen. */
export function toonProbleem(plek: HTMLElement, tekst: string): void {
  plek.querySelector(".oa-probleem")?.remove();
  const vak = document.createElement("div");
  vak.className = "oa-probleem";
  vak.setAttribute("role", "alert");
  Object.assign(vak.style, { margin: "16px", padding: "12px 16px", border: "1px solid #c8a200", borderRadius: "6px", background: "#fff8db", color: "#1d1d1b", font: "14px/1.5 system-ui, sans-serif" });
  const p = document.createElement("p");
  p.style.margin = "0 0 10px";
  p.textContent = tekst;
  const knop = document.createElement("button");
  knop.type = "button";
  knop.textContent = "Opnieuw proberen";
  knop.addEventListener("click", () => location.reload());
  vak.append(p, knop);
  plek.prepend(vak);
}

function leesSessie(k: string): string | null {
  try {
    return sessionStorage.getItem(k);
  } catch {
    return null;
  }
}

function zetSessie(k: string, v: string | null): void {
  try {
    if (v === null) sessionStorage.removeItem(k);
    else sessionStorage.setItem(k, v);
  } catch {
    /* geen opslag: dan zonder lusbeveiliging */
  }
}

/** Vraagt een sessiesleutel voor de kop, met het cookie van deze pagina. */
export async function koppelSessie(): Promise<string | null> {
  try {
    const r = await fetch("/api/auth/koppel", { method: "POST", credentials: "same-origin", headers: { "x-oa-verzoek": "1" } });
    if (!r.ok) return null;
    return ((await r.json()) as { sessie: string }).sessie;
  } catch {
    return null;
  }
}
