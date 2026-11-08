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

/** Is er een sessie (cookie)? Zo niet: naar het inloggen, met terugkeer naar deze pagina. */
export async function zorgVoorInlog(): Promise<boolean> {
  const r = await fetch("/api/lees/wie-ben-ik", { credentials: "same-origin" });
  if (r.status === 401) {
    location.href = `/api/auth/login?terug=${encodeURIComponent(location.pathname + location.search)}`;
    return false;
  }
  return r.ok;
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
