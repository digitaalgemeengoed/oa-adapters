/// <reference types="office-js" />
import { koppelSessie } from "../src/host/statusbalk";

/**
 * Het aanmeldvenster van de Word-invoegtoepassing. Office opent het als
 * eigen venster, zodat Keycloak niet in een iframe hoeft. Na het inloggen
 * vraagt het een sessiesleutel en geeft die aan het takenvenster.
 */
Office.onReady(async () => {
  const status = document.getElementById("status")!;
  const sessie = await koppelSessie();
  if (!sessie) {
    // Nog niet ingelogd: naar Keycloak, daarna terug naar dit venster.
    location.href = `/api/auth/login?terug=${encodeURIComponent("/word/aanmelden.html")}`;
    return;
  }
  status.textContent = "Ingelogd. Dit venster sluit vanzelf.";
  Office.context.ui.messageParent(JSON.stringify({ sessie }));
});
