import {
  BASISVERMOGENS,
  type Adapter,
  type Afdruk,
  type Inhoud,
  type Melding,
  type Plek,
  type Vermogen,
  type Werkomgeving,
} from "@digitaalgemeengoed/oa-contract";
import { browserFragment, naarHtml, NietUitvoerbaar, plekNaarDoel, segmentNaarOpdracht, type Blok, type Doel, type MaakFragment, type Opdracht } from "./semantisch.js";

/**
 * Wat een echte tekstverwerker (Word, LibreOffice) moet kunnen, zonder html:
 * zijn structuur beschrijven, een opdracht uitvoeren, iets aanwijzen en
 * eigenschappen in het bestand bewaren. De Word-adapter doet dat met
 * Office.js, de LibreOffice-adapter via de extensie op de eigen computer.
 */
export interface Tekstverwerker {
  readonly id: string;
  readonly naam: string;
  leesBlokken(): Promise<Blok[]>;
  voerUit(opdracht: Opdracht): Promise<void>;
  toon(doel: Doel): Promise<void>;
  /** Het hele document vervangen door html (terugval; kan opmaak en afbeeldingen kosten). */
  vervangAlles(html: string): Promise<void>;
  leesEigenschap(naam: string): Promise<string | null>;
  schrijfEigenschap(naam: string, waarde: string): Promise<void>;
  /** Het bestand zelf (docx, odt …), base64; voor het vastleggen van het origineel. */
  leesBestand?(): Promise<Inhoud>;
}

const AFDRUK = "oa-afdruk";

/**
 * Adapter voor tekstverwerkers met structuur. Levert semantische html, en
 * schrijft herstellingen terug als opdracht (kopniveau, alternatieve tekst,
 * linktekst, kopregel), zodat de opmaak van het document blijft staan.
 */
export class StructuurAdapter implements Adapter {
  private blokken: Blok[] = [];

  constructor(
    private readonly tv: Tekstverwerker,
    private readonly melden: (m: Melding) => void,
    private readonly fragment: MaakFragment = browserFragment,
  ) {
    if (tv.leesBestand) this.leverBestand = () => tv.leesBestand!();
  }

  /** Het origineel; alleen als de tekstverwerker het bestand kan opleveren. */
  readonly leverBestand?: () => Promise<Inhoud>;

  werkomgeving(): Werkomgeving {
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "plek-tonen", "afdruk-schrijven"];
    if (this.leverBestand) vermogens.push("bestand-opleveren");
    return { id: this.tv.id, naam: this.tv.naam, vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    this.blokken = await this.tv.leesBlokken();
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: naarHtml(this.blokken) };
  }

  async vervangInhoud(inhoud: Inhoud): Promise<void> {
    if (inhoud.formaat !== "html") throw new Error("Deze werkomgeving kan alleen html terugzetten.");
    await this.tv.vervangAlles(inhoud.data);
    this.blokken = [];
    this.melden({ soort: "waarschuwing", tekst: "Het hele document is vervangen. Controleer opmaak en afbeeldingen." });
  }

  toon(melding: Melding): void {
    this.melden(melding);
  }

  vervangSegment = async (plek: Plek, html: string): Promise<void> => {
    if (this.blokken.length === 0) await this.leverInhoud();
    let opdracht: Opdracht;
    try {
      opdracht = segmentNaarOpdracht(this.blokken, plek.pad, html, this.fragment);
    } catch (e) {
      if (e instanceof NietUitvoerbaar) throw new Error(e.message);
      throw e;
    }
    await this.tv.voerUit(opdracht);
    // De structuur is veranderd; bij de volgende vraag opnieuw lezen.
    this.blokken = [];
  };

  toonPlek = (plek: Plek): void => {
    const doel = this.blokken.length ? plekNaarDoel(this.blokken, plek.pad) : null;
    if (!doel) {
      this.melden({ soort: "info", tekst: `${plek.beschrijving}: beoordeel eerst opnieuw om de plek te kunnen tonen.` });
      return;
    }
    this.tv.toon(doel).catch((e: Error) => this.melden({ soort: "fout", tekst: e.message }));
  };

  schrijfAfdruk = async (afdruk: Afdruk): Promise<void> => {
    await this.tv.schrijfEigenschap(AFDRUK, JSON.stringify(afdruk));
  };

  leesAfdruk = async (): Promise<Afdruk | null> => {
    const w = await this.tv.leesEigenschap(AFDRUK);
    if (!w) return null;
    try {
      return JSON.parse(w) as Afdruk;
    } catch {
      return null;
    }
  };
}
