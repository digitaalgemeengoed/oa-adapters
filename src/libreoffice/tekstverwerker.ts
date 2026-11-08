import type { Inhoud } from "@digitaalgemeengoed/oa-contract";
import type { Tekstverwerker } from "../structuur-adapter.js";
import { groepeer, type Blok, type Doel, type Opdracht, type RuweAlinea, type Tabel } from "../semantisch.js";

/**
 * LibreOffice Writer op de eigen computer, via de brug van de extensie
 * (127.0.0.1, alleen met de sleutel uit het adres van deze pagina). De
 * extensie leest en wijzigt het document met UNO; zie
 * libreoffice-extensie/pythonpath/oa_document.py.
 */
export class LibreOfficeTekstverwerker implements Tekstverwerker {
  readonly id = "libreoffice-writer";
  readonly naam = "LibreOffice Writer";

  constructor(
    private readonly poort: number,
    private readonly sleutel: string,
  ) {}

  private async vraag<T>(methode: string, pad: string, lichaam?: unknown): Promise<T> {
    const kanaal = webkitKanaal();
    if (kanaal) return viaKanaal<T>(kanaal, this.sleutel, methode, pad, lichaam);
    let r: Response;
    try {
      r = await fetch(`http://127.0.0.1:${this.poort}${pad}`, {
        method: methode,
        headers: { authorization: `Bearer ${this.sleutel}`, ...(lichaam !== undefined ? { "content-type": "application/json" } : {}) },
        body: lichaam !== undefined ? JSON.stringify(lichaam) : undefined,
      } as RequestInit);
    } catch {
      throw new Error("Geen verbinding met LibreOffice. Kies in LibreOffice opnieuw Office Assistent → Assistent openen bij dit document.");
    }
    const j = (await r.json().catch(() => ({}))) as { melding?: string };
    if (!r.ok) throw new Error(j.melding ?? `LibreOffice gaf fout ${r.status}`);
    return j as T;
  }

  status() {
    return this.vraag<{ naam: string; versie: string }>("GET", "/status");
  }

  async leesBlokken(): Promise<Blok[]> {
    return groepeer(await this.vraag<(RuweAlinea | Tabel)[]>("GET", "/blokken"));
  }

  async voerUit(o: Opdracht): Promise<void> {
    await this.vraag("POST", "/opdracht", o);
  }

  async toon(doel: Doel): Promise<void> {
    await this.vraag("POST", "/toon", doel);
  }

  async vervangAlles(html: string): Promise<void> {
    await this.vraag("POST", "/vervang", { html });
  }

  /** Het document als OpenDocument (.odt), het eigen formaat van Writer. */
  leesBestand(): Promise<Inhoud> {
    return this.vraag<Inhoud>("GET", "/bestand");
  }

  async leesEigenschap(naam: string): Promise<string | null> {
    return (await this.vraag<{ waarde: string | null }>("GET", `/eigenschap?naam=${encodeURIComponent(naam)}`)).waarde;
  }

  async schrijfEigenschap(naam: string, waarde: string): Promise<void> {
    await this.vraag("PUT", "/eigenschap", { naam, waarde });
  }
}

// ---------------------------------------------------------------------------
// In de zijbalk van Writer (webweergave van WebKitGTK) praat het paneel niet
// via http met de brug: een https-pagina mag geen http naar 127.0.0.1. De
// extensie biedt daar een berichtkanaal (window.webkit.messageHandlers.oaBrug)
// en antwoordt via window.__oaBrugAntwoord.
// ---------------------------------------------------------------------------

interface Kanaal {
  postMessage(bericht: unknown): void;
}

type Wachtend = { klaar: (w: unknown) => void; fout: (e: Error) => void };

const wachtend = new Map<number, Wachtend>();
let volgnummer = 0;

function webkitKanaal(): Kanaal | null {
  const w = globalThis as unknown as { webkit?: { messageHandlers?: { oaBrug?: Kanaal } } };
  return w.webkit?.messageHandlers?.oaBrug ?? null;
}

function viaKanaal<T>(kanaal: Kanaal, sleutel: string, methode: string, pad: string, lichaam?: unknown): Promise<T> {
  const g = globalThis as unknown as { __oaBrugAntwoord?: (id: number, a: { status: number; lichaam: { melding?: string } }) => void };
  g.__oaBrugAntwoord ??= (id, a) => {
    const w = wachtend.get(id);
    if (!w) return;
    wachtend.delete(id);
    if (a.status >= 200 && a.status < 300) w.klaar(a.lichaam);
    else w.fout(new Error(a.lichaam?.melding ?? `LibreOffice gaf fout ${a.status}`));
  };
  const id = ++volgnummer;
  return new Promise<T>((klaar, fout) => {
    const tijd = setTimeout(() => {
      wachtend.delete(id);
      fout(new Error("LibreOffice antwoordt niet. Sluit het zijpaneel en open het opnieuw."));
    }, 60_000);
    wachtend.set(id, {
      klaar: (w) => {
        clearTimeout(tijd);
        klaar(w as T);
      },
      fout: (e) => {
        clearTimeout(tijd);
        fout(e);
      },
    });
    kanaal.postMessage({ id, sleutel, methode, pad, lichaam: lichaam ?? null });
  });
}
