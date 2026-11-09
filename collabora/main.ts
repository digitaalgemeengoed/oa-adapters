import { plaatsPaneel, stuurOpdracht } from "@digitaalgemeengoed/oa-paneel";
import { assistentKnoppen } from "../src/host/assistentknoppen";
import "@digitaalgemeengoed/oa-paneel/style.css";
import { CollaboraAdapter, type CollaboraVenster, type Formaat } from "../src/collabora/adapter";
import { statusbalk, zorgVoorInlog } from "../src/host/statusbalk";
import "./collabora.css";

/**
 * Collabora Online met het paneel ernaast. Collabora opent het werkbestand
 * via WOPI bij de integratielaag; deze pagina praat met Collabora via
 * postMessage (Host_PostmessageReady, Action_Save).
 */
const iframe = document.getElementById("editor") as HTMLIFrameElement;
const keuze = document.getElementById("bestanden") as HTMLSelectElement;
const leeg = document.getElementById("leeg")!;
const meld = statusbalk(document.getElementById("status")!);
const paneelplek = document.getElementById("paneel")!;

const kop = { "x-oa-verzoek": "1" };
let collaboraHerkomst = "";
let huidig: string | null = null;
let weghalen: (() => void) | null = null;
let geladen: (() => void) | null = null;
let opgeslagen: ((ok: boolean) => void) | null = null;

async function api<T>(pad: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(pad, { ...init, credentials: "same-origin", headers: { ...kop, ...(init.headers ?? {}) } });
  const j = (await r.json().catch(() => ({}))) as { melding?: string };
  if (!r.ok) throw new Error(j.melding ?? `Fout ${r.status}`);
  return j as T;
}

function stuur(bericht: object) {
  iframe.contentWindow?.postMessage(JSON.stringify({ ...bericht, SendTime: Date.now() }), collaboraHerkomst);
}

window.addEventListener("message", (e) => {
  if (e.origin !== collaboraHerkomst || e.source !== iframe.contentWindow) return;
  let b: { MessageId?: string; Values?: Record<string, unknown> };
  try {
    b = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
  } catch {
    return;
  }
  if (b.MessageId === "App_LoadingStatus") {
    if (b.Values?.Status === "Frame_Ready") stuur({ MessageId: "Host_PostmessageReady" });
    if (b.Values?.Status === "Document_Loaded") {
      voegKnoppenToe();
      geladen?.();
      geladen = null;
    }
  }
  if (b.MessageId === "Clicked_Button" && typeof b.Values?.id === "string" && b.Values.id.startsWith("oa-")) {
    const id = b.Values.id.slice(3);
    if (id === "paneel") werkvlak.classList.toggle("zonder-paneel");
    else {
      werkvlak.classList.remove("zonder-paneel");
      stuurOpdracht(id as Parameters<typeof stuurOpdracht>[0]);
    }
  }
  if (b.MessageId === "Action_Save_Resp") {
    opgeslagen?.(b.Values?.success !== false);
    opgeslagen = null;
  }
});

/**
 * De knoppen van de assistent in de werkbalk van Collabora zelf (postMessage
 * Insert_Button). Collabora stuurt bij een klik Clicked_Button terug. De
 * pictogrammen komen van ons eigen adres; Collabora staat dat toe in zijn
 * Content-Security-Policy omdat wij de WOPI-host zijn.
 */
const werkvlak = document.querySelector<HTMLElement>(".co-werkvlak")!;
function voegKnoppenToe() {
  for (const k of assistentKnoppen()) {
    stuur({ MessageId: "Insert_Button", Values: { id: `oa-${k.id}`, imgurl: `${location.origin}/iconen/${k.id}.svg`, hint: `Assistent: ${k.naam}`, label: `Assistent: ${k.naam}`, mobile: false } });
  }
}

/** Opent een werkbestand in het iframe: formulier met de toegangssleutel, zoals WOPI dat wil. */
async function openInEditor(id: string): Promise<void> {
  const o = await api<{ editor: string; wopiSrc: string; token: string; ttl: number }>(`/api/collabora/bestanden/${id}/open`, { method: "POST" });
  collaboraHerkomst = new URL(o.editor).origin;
  const doel = `${o.editor}${o.editor.includes("?") ? "&" : "?"}WOPISrc=${encodeURIComponent(o.wopiSrc)}&lang=nl`;
  const form = document.createElement("form");
  form.method = "post";
  form.action = doel;
  form.target = "collabora";
  for (const [naam, waarde] of [["access_token", o.token], ["access_token_ttl", String(o.ttl)]]) {
    const i = document.createElement("input");
    i.type = "hidden";
    i.name = naam;
    i.value = waarde;
    form.appendChild(i);
  }
  document.body.appendChild(form);
  const klaar = new Promise<void>((r) => {
    geladen = r;
    setTimeout(r, 30_000);
  });
  form.submit();
  // Niet meteen weghalen: dan breekt de browser de navigatie af.
  setTimeout(() => form.remove(), 5000);
  leeg.hidden = true;
  iframe.hidden = false;
  await klaar;
}

const venster: CollaboraVenster = {
  slaOp: () =>
    new Promise<void>((klaar) => {
      opgeslagen = () => klaar();
      stuur({ MessageId: "Action_Save", Values: { DontTerminateEdit: true, DontSaveIfUnmodified: true, Notify: true } });
      // Niets gewijzigd: dan antwoordt Collabora soms niet. Niet eeuwig wachten.
      setTimeout(() => {
        opgeslagen = null;
        klaar();
      }, 6000);
    }),
  herlaad: async () => {
    if (huidig) await openInEditor(huidig);
  },
  unoOpdracht: (opdracht, args) => stuur({ MessageId: "Send_UNO_Command", Values: { Command: opdracht, Args: args } }),
};

const formaten = new Map<string, Formaat>();

async function open(id: string) {
  huidig = id;
  keuze.value = id;
  weghalen?.();
  await openInEditor(id);
  weghalen = plaatsPaneel(paneelplek, new CollaboraAdapter(id, venster, meld, formaten.get(id) ?? "docx"));
}

async function vulLijst(kies?: string) {
  const lijst = await api<{ id: string; naam: string; gewijzigd: string; formaat?: Formaat }[]>("/api/collabora/bestanden");
  for (const w of lijst) formaten.set(w.id, w.formaat ?? "docx");
  keuze.innerHTML = "";
  const leegOptie = new Option(lijst.length ? "Kies een werkbestand…" : "Nog geen werkbestanden", "");
  keuze.add(leegOptie);
  for (const w of lijst) keuze.add(new Option(`${w.naam} (${new Date(w.gewijzigd).toLocaleString("nl-NL")})`, w.id));
  if (kies) keuze.value = kies;
}

async function start() {
  if (!(await zorgVoorInlog())) return;
  iframe.hidden = true;
  try {
    await vulLijst();
  } catch (e) {
    meld({ soort: "fout", tekst: (e as Error).message });
    return;
  }
  keuze.addEventListener("change", () => keuze.value && open(keuze.value).catch((e) => meld({ soort: "fout", tekst: (e as Error).message })));
  for (const knop of document.querySelectorAll<HTMLButtonElement>(".co-nieuw button")) {
    knop.addEventListener("click", async () => {
      try {
        meld({ soort: "info", tekst: "Nieuw voorbeeld maken…" });
        const { id } = await api<{ id: string }>("/api/collabora/bestanden", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ soort: knop.dataset.soort }),
        });
        await vulLijst(id);
        await open(id);
      } catch (e) {
        meld({ soort: "fout", tekst: (e as Error).message });
      }
    });
  }
}

start();
