/// <reference types="office-js" />
import { koppelSessie, toonProbleem, zorgVoorInlog } from "../src/host/statusbalk";

/**
 * Het aanmeldvenster van de Word-invoegtoepassing. Office opent het als
 * eigen venster, zodat Keycloak niet in een iframe hoeft. Na het inloggen
 * vraagt het een sessiesleutel en geeft die aan het takenvenster.
 */
Office.onReady(async () => {
  const status = document.getElementById("status")!;
  // Nog niet ingelogd: naar Keycloak en terug naar dit venster. Server weg of cookie niet bewaard: een melding met een knop.
  if (!(await zorgVoorInlog())) return;
  const sessie = await koppelSessie();
  if (!sessie) {
    status.textContent = "";
    toonProbleem(document.body, "Je bent ingelogd, maar de sessie voor Office kon niet worden gemaakt. Probeer het opnieuw; blijft het zo, meld het dan bij de beheerder.");
    return;
  }
  status.textContent = "Ingelogd. Dit venster sluit vanzelf.";
  Office.context.ui.messageParent(JSON.stringify({ sessie }));
});
