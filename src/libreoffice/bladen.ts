import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Vermogen, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
import type { LibreOfficeTekstverwerker } from "./tekstverwerker.js";

const AFDRUK = "oa-afdruk";
const NAMEN = { rekenblad: ["libreoffice-calc", "LibreOffice Calc"], presentatie: ["libreoffice-impress", "LibreOffice Impress"] } as const;

/**
 * LibreOffice Calc en Impress via de brug. De extensie levert het document
 * als secties (een blad of een dia per sectie, zie oa_bladen.py) en voert
 * een herstelling uit op een plek: een blad hernoemen, de titel van een dia,
 * alternatieve tekst. Het hele document vervangen kan hier niet; dat is
 * voor een rekenblad of presentatie ook geen zinnige terugval.
 */
export class LibreOfficeBladenAdapter implements Adapter {
  constructor(
    private readonly brug: LibreOfficeTekstverwerker,
    private readonly soort: "rekenblad" | "presentatie",
    private readonly melden: (m: Melding) => void,
  ) {}

  werkomgeving(): Werkomgeving {
    const [id, naam] = NAMEN[this.soort];
    const vermogens: Vermogen[] = [...BASISVERMOGENS, "segment-vervangen", "plek-tonen", "afdruk-schrijven", "bestand-opleveren", "tekst-vervangen", "selectie-lezen", "eigenschap-schrijven"];
    if (this.markeerPii) vermogens.push("pii-markeren", "pii-klik");
    return { id, naam, vermogens };
  }

  async leverInhoud(): Promise<Inhoud> {
    return { formaat: "html", mediaType: "text/html", codering: "tekst", data: await this.brug.html() };
  }

  async vervangInhoud(): Promise<void> {
    throw new Error("Een rekenblad of presentatie kan de assistent niet in zijn geheel vervangen. Pas het met de hand aan.");
  }

  vervangSegment = async (plek: Plek, html: string): Promise<void> => {
    await this.brug.segment(plek.pad, html);
  };

  toonPlek = (plek: Plek): void => {
    this.brug.plek(plek.pad).catch((e: Error) => this.melden({ soort: "fout", tekst: e.message }));
  };

  leverBestand = (voorkeur?: "ooxml"): Promise<Inhoud> => this.brug.leesBestand(voorkeur);
  vervangTekst = (paren: { van: string; naar: string }[]): Promise<number> => this.brug.vervangTekst(paren);
  leesSelectie = (): Promise<string> => this.brug.leesSelectie();
  schrijfDocumenteigenschap = (naam: string, waarde: string): Promise<void> => this.brug.schrijfDocumenteigenschap(naam, waarde);

  // Anonimiseren in het document: de plaatshouder staat in de cel of het tekstvak (oa_pii.py).
  // Ontbreekt als de extensie te oud is (zie libreoffice/main.ts).
  get markeerPii(): Adapter["markeerPii"] {
    return this.brug.markeerPii ? (m) => this.brug.markeerPii(m) : undefined;
  }
  get leesPiiPlekken(): Adapter["leesPiiPlekken"] {
    return this.brug.leesPiiPlekken ? () => this.brug.leesPiiPlekken() : undefined;
  }
  get herstelPii(): Adapter["herstelPii"] {
    return this.brug.herstelPii ? (p) => this.brug.herstelPii(p) : undefined;
  }
  get zetPiiDefinitief(): Adapter["zetPiiDefinitief"] {
    return this.brug.zetPiiDefinitief ? () => this.brug.zetPiiDefinitief() : undefined;
  }
  get toonPiiPlek(): Adapter["toonPiiPlek"] {
    return this.brug.toonPiiPlek ? (p) => this.brug.toonPiiPlek(p) : undefined;
  }
  get bijPiiKlik(): Adapter["bijPiiKlik"] {
    return this.brug.bijPiiKlik ? (t) => this.brug.bijPiiKlik(t) : undefined;
  }

  toon(melding: Melding): void {
    this.melden(melding);
  }

  schrijfAfdruk = async (afdruk: Afdruk): Promise<void> => {
    await this.brug.schrijfEigenschap(AFDRUK, JSON.stringify(afdruk));
  };

  leesAfdruk = async (): Promise<Afdruk | null> => {
    const w = await this.brug.leesEigenschap(AFDRUK);
    if (!w) return null;
    try {
      return JSON.parse(w) as Afdruk;
    } catch {
      return null;
    }
  };
}
