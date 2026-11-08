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

  async leesEigenschap(naam: string): Promise<string | null> {
    return (await this.vraag<{ waarde: string | null }>("GET", `/eigenschap?naam=${encodeURIComponent(naam)}`)).waarde;
  }

  async schrijfEigenschap(naam: string, waarde: string): Promise<void> {
    await this.vraag("PUT", "/eigenschap", { naam, waarde });
  }
}
