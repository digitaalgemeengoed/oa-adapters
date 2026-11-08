import { BASISVERMOGENS, type Adapter, type Afdruk, type Inhoud, type Melding, type Plek, type Werkomgeving } from "@digitaalgemeengoed/oa-contract";
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
    return { id, naam, vermogens: [...BASISVERMOGENS, "segment-vervangen", "plek-tonen", "afdruk-schrijven", "bestand-opleveren"] };
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

  leverBestand = (): Promise<Inhoud> => this.brug.leesBestand();

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
