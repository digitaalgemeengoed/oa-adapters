/// <reference types="office-js" />
import { plaatsPaneel } from "@digitaalgemeengoed/oa-paneel";
import "@digitaalgemeengoed/oa-paneel/style.css";
import { StructuurAdapter } from "../src/structuur-adapter";
import { WordTekstverwerker } from "../src/word/tekstverwerker";
import { koppelSessie, statusbalk } from "../src/host/statusbalk";
import "./word.css";

/**
 * Het takenvenster van de Word-invoegtoepassing. De sessie gaat als kop
 * mee: in Word voor het web staat dit venster in een iframe van office.com,
 * en daar komt het cookie van de integratielaag niet aan.
 */
const status = document.getElementById("status")!;
const aanmelden = document.getElementById("aanmelden")!;
const fout = document.getElementById("aanmeldfout")!;
const meld = statusbalk(status);

function start(sessie: string) {
  aanmelden.hidden = true;
  const adapter = new StructuurAdapter(new WordTekstverwerker(), meld);
  plaatsPaneel(document.getElementById("paneel")!, adapter, { sessie });
}

function inloggen() {
  fout.hidden = true;
  Office.context.ui.displayDialogAsync(`${location.origin}/word/aanmelden.html`, { height: 70, width: 35, promptBeforeOpen: false }, (r) => {
    if (r.status !== Office.AsyncResultStatus.Succeeded) {
      fout.textContent = `Het aanmeldvenster ging niet open (${r.error.message}). Sta pop-ups toe voor deze site en probeer opnieuw.`;
      fout.hidden = false;
      return;
    }
    const venster = r.value;
    venster.addEventHandler(Office.EventType.DialogMessageReceived, (arg) => {
      venster.close();
      try {
        const { sessie } = JSON.parse((arg as { message: string }).message) as { sessie: string };
        start(sessie);
      } catch {
        fout.textContent = "Inloggen is niet gelukt. Probeer opnieuw.";
        fout.hidden = false;
      }
    });
    venster.addEventHandler(Office.EventType.DialogEventReceived, () => {
      fout.textContent = "Het aanmeldvenster is gesloten voordat je was ingelogd.";
      fout.hidden = false;
    });
  });
}

Office.onReady(async (info) => {
  if (info.host !== Office.HostType.Word) {
    status.textContent = "Deze invoegtoepassing werkt alleen in Word.";
    return;
  }
  if (!Office.context.requirements.isSetSupported("WordApi", "1.3")) {
    status.textContent = "Deze versie van Word is te oud voor de assistent (WordApi 1.3 nodig).";
    return;
  }
  document.getElementById("inloggen")!.addEventListener("click", inloggen);
  // In Word op de desktop kan het cookie er al zijn; in Word voor het web niet.
  const sessie = await koppelSessie();
  if (sessie) start(sessie);
  else {
    meld({ soort: "info", tekst: "Log in om te beginnen." });
    aanmelden.hidden = false;
  }
});
