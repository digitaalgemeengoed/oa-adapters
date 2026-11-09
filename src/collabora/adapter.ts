import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import { icuPatroon, icuVervanging, ordenParen, plaatshoudersIn, telInHtml, type Paar } from "../tekstvervangen.js";
import type { PiiMarkering, PiiPlek } from "@digitaalgemeengoed/oa-contract";

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
  /** Een UNO-opdracht in Collabora uitvoeren (postMessage Send_UNO_Command); geen antwoord. */
  unoOpdracht?(opdracht: string, args: Record<string, { type: string; value: unknown }>): void;
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
    if (venster.unoOpdracht) {
      this.vervangTekst = (paren) => this.zoekEnVervang(paren);
      this.markeerPii = (m) => this.markeer(m);
      this.leesPiiPlekken = () => this.plekken();
      this.herstelPii = (p) => this.herstel(p);
      this.zetPiiDefinitief = async () => undefined;
      this.toonPiiPlek = (p) => this.toonPlaatshouder(p);
    }
  }

  // --- Anonimiseren in het document -------------------------------------
  // Collabora geeft via postMessage niets terug uit het document. Vervangen
  // gaat met zoeken en vervangen van Collabora zelf; welke plaatshouders er
  // staan, lezen we na opslaan uit het bestand. Klikken en de selectie geeft
  // Collabora niet door; terugzetten geldt voor alle plekken van een
  // plaatshouder tegelijk.

  readonly markeerPii?: (m: PiiMarkering[]) => Promise<PiiPlek[]>;
  readonly leesPiiPlekken?: () => Promise<PiiPlek[]>;
  readonly herstelPii?: (p: { plek: string; waarde: string }[]) => Promise<void>;
  readonly zetPiiDefinitief?: () => Promise<void>;
  readonly toonPiiPlek?: (plek: string) => void;
  private laatsteScan: PiiPlek[] = [];

  private vervangAlles(van: string, naar: string, regex = true): void {
    this.venster.unoOpdracht!(".uno:ExecuteSearch", {
      "SearchItem.SearchString": { type: "string", value: regex ? icuPatroon(van) : van },
      "SearchItem.ReplaceString": { type: "string", value: icuVervanging(naar) },
      "SearchItem.Command": { type: "long", value: 3 }, // REPLACE_ALL
      "SearchItem.AlgorithmType": { type: "short", value: 1 }, // REGEXP
      "SearchItem.TransliterationFlags": { type: "long", value: 0 },
      "SearchItem.Backward": { type: "boolean", value: false },
    });
  }

  private async plekken(): Promise<PiiPlek[]> {
    await this.venster.slaOp();
    const { html } = await this.vraag<{ html: string }>("/html");
    const tekst = html.replace(/<[^>]*>/g, " ");
    this.laatsteScan = plaatshoudersIn(tekst).map((p, i) => ({ plek: `h${i}`, plaatshouder: p.plaatshouder, voorvertoning: false }));
    return this.laatsteScan;
  }

  private async markeer(markeringen: PiiMarkering[]): Promise<PiiPlek[]> {
    const voor = await this.plekken();
    for (const m of [...markeringen].filter((x) => x.van.trim()).sort((a, b) => b.van.length - a.van.length)) this.vervangAlles(m.van, m.plaatshouder);
    const na = await this.plekken();
    // Nieuw: wat er van deze plaatshouders meer staat dan voorheen.
    const tel = (l: PiiPlek[], ph: string) => l.filter((p) => p.plaatshouder === ph).length;
    const namen = new Set(markeringen.map((m) => m.plaatshouder));
    return [...namen].flatMap((ph) => na.filter((p) => p.plaatshouder === ph).slice(tel(voor, ph)));
  }

  private async herstel(plekken: { plek: string; waarde: string }[]): Promise<void> {
    const per = new Map<string, string>();
    for (const { plek, waarde } of plekken) {
      const ph = this.laatsteScan.find((p) => p.plek === plek)?.plaatshouder;
      if (ph) per.set(ph, waarde);
    }
    // Letterlijk zoeken: \Q…\E, zonder woordgrens (een plaatshouder staat tussen haken).
    for (const [ph, waarde] of per) this.vervangAlles(`\\Q${ph}\\E`, waarde, false);
    if (per.size) await this.venster.slaOp();
  }

  private toonPlaatshouder(plek: string): void {
    const ph = this.laatsteScan.find((p) => p.plek === plek)?.plaatshouder;
    if (!ph) return;
    this.venster.unoOpdracht!(".uno:ExecuteSearch", {
      "SearchItem.SearchString": { type: "string", value: `\\Q${ph}\\E` },
      "SearchItem.Command": { type: "long", value: 0 }, // FIND
      "SearchItem.AlgorithmType": { type: "short", value: 1 },
      "SearchItem.Backward": { type: "boolean", value: false },
    });
  }

  readonly vervangTekst?: (paren: Paar[]) => Promise<number>;

  /**
   * Zoeken en vervangen van Collabora zelf (.uno:ExecuteSearch, "alles
   * vervangen", reguliere expressie met woordgrens). postMessage geeft geen
   * aantal terug; daarom tellen we voor en na in het opgeslagen bestand, en
   * melden we wat is blijven staan.
   */
  private async zoekEnVervang(paren: Paar[]): Promise<number> {
    const geordend = ordenParen(paren);
    await this.venster.slaOp();
    const voor = telInHtml((await this.vraag<{ html: string }>("/html")).html, geordend);
    for (const p of geordend)
      this.venster.unoOpdracht!(".uno:ExecuteSearch", {
        "SearchItem.SearchString": { type: "string", value: icuPatroon(p.van) },
        "SearchItem.ReplaceString": { type: "string", value: icuVervanging(p.naar) },
        "SearchItem.Command": { type: "long", value: 3 }, // REPLACE_ALL
        "SearchItem.AlgorithmType": { type: "short", value: 1 }, // REGEXP
        "SearchItem.TransliterationFlags": { type: "long", value: 0 }, // hoofdlettergevoelig
        "SearchItem.Backward": { type: "boolean", value: false },
      });
    // Collabora voert de opdrachten op volgorde uit; opslaan komt er dus na.
    await this.venster.slaOp();
    const na = telInHtml((await this.vraag<{ html: string }>("/html")).html, geordend);
    if (na > 0) this.melden({ soort: "waarschuwing", tekst: `${na} keer is een persoonsgegeven in het document blijven staan. Vervang die met de hand door de plaatshouder.` });
    return Math.max(0, voor - na);
  }

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "afdruk-schrijven", "bestand-opleveren"];
    if (this.formaat !== "docx") vermogens.push("segment-vervangen");
    if (this.vervangTekst) vermogens.push("tekst-vervangen", "pii-markeren");
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
