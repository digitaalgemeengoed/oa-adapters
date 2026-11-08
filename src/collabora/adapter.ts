import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";

export type Formaat = "docx" | "ods" | "odp";

/**
 * Adapter voor Collabora Online. Collabora draait in een iframe en praat met
 * deze pagina via postMessage; het document zelf staat als werkbestand in de
 * integratielaag (WOPI). Collabora biedt alleen de drie basisvermogens plus
 * de afdruk: een deel van het document vervangen kan via postMessage niet.
 * Voor tekst valt de assistent dan terug op het hele document; dat is hier
 * te zien. Een rekenblad (ods) of presentatie (odp) leest en herstelt de
 * integratielaag zelf, op een plek (lib/odf.ts); daarna laadt Collabora het
 * bestand opnieuw.
 */
export interface CollaboraVenster {
  /** Laat Collabora opslaan en wacht tot dat klaar is. */
  slaOp(): Promise<void>;
  /** Opent het werkbestand opnieuw in Collabora (na een wijziging buiten Collabora om). */
  herlaad(): Promise<void>;
}

const AFDRUK = "oa-afdruk";

export class CollaboraAdapter implements Adapter {
  constructor(
    private readonly werkbestand: string,
    private readonly venster: CollaboraVenster,
    private readonly melden: (m: Melding) => void,
    private readonly formaat: Formaat = "docx",
  ) {
    if (formaat !== "docx") this.vervangSegment = (plek, html) => this.herstelOpPlek(plek, html);
  }

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "afdruk-schrijven", "bestand-opleveren"];
    if (this.formaat !== "docx") vermogens.push("segment-vervangen");
    const naam = this.formaat === "ods" ? "Collabora Online (rekenblad)" : this.formaat === "odp" ? "Collabora Online (presentatie)" : "Collabora Online";
    return { id: "collabora-online", naam, vermogens };
  }

  readonly vervangSegment?: (plek: Plek, html: string) => Promise<void>;

  private async herstelOpPlek(plek: Plek, html: string): Promise<void> {
    await this.venster.slaOp();
    await this.vraag("/segment", { method: "POST", body: JSON.stringify({ pad: plek.pad, html }) });
    await this.venster.herlaad();
    this.melden({ soort: "info", tekst: "Hersteld; Collabora heeft het bestand opnieuw geladen." });
  }

  private async vraag<T>(pad: string, init: RequestInit = {}): Promise<T> {
    const r = await fetch(`/api/collabora/bestanden/${this.werkbestand}${pad}`, {
      ...init,
      credentials: "same-origin",
      headers: { "x-oa-verzoek": "1", ...(init.body ? { "content-type": "application/json" } : {}) },
    });
    const j = (await r.json().catch(() => ({}))) as { melding?: string };
    if (!r.ok) throw new Error(j.melding ?? `Fout ${r.status}`);
    return j as T;
  }

  async leverInhoud(): Promise<Inhoud> {
    // Eerst laten opslaan: de assistent beoordeelt wat de medewerker ziet.
    await this.venster.slaOp();
    const { html } = await this.vraag<{ html: string }>("/html");
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: html };
  }

  async vervangInhoud(inhoud: Inhoud): Promise<void> {
    if (inhoud.formaat !== "html") throw new Error("Deze werkomgeving kan alleen html terugzetten.");
    await this.venster.slaOp();
    await this.vraag("/html", { method: "PUT", body: JSON.stringify({ html: inhoud.data }) });
    await this.venster.herlaad();
    this.melden({ soort: "waarschuwing", tekst: "Het hele document is vervangen en opnieuw geladen. Controleer de opmaak." });
  }

  /** Het werkbestand zelf (docx, ods of odp), na opslaan. */
  async leverBestand(): Promise<Inhoud> {
    await this.venster.slaOp();
    return this.vraag<Inhoud>("/bestand");
  }

  toon(melding: Melding): void {
    this.melden(melding);
  }

  schrijfAfdruk = async (afdruk: Afdruk): Promise<void> => {
    await this.vraag("/eigenschap", { method: "PUT", body: JSON.stringify({ naam: AFDRUK, waarde: JSON.stringify(afdruk) }) });
  };

  leesAfdruk = async (): Promise<Afdruk | null> => {
    const { waarde } = await this.vraag<{ waarde: string | null }>(`/eigenschap?naam=${AFDRUK}`);
    if (!waarde) return null;
    try {
      return JSON.parse(waarde) as Afdruk;
    } catch {
      return null;
    }
  };
}
