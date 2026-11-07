/**
 * Een verzonnen raadsvoorstel met bewuste toegankelijkheidsfouten: een
 * afbeelding zonder alternatieve tekst, een vette regel als kop, een
 * overgeslagen kopniveau, een tabel zonder kopregel en een vage linktekst.
 * Personen, bedragen en nummers bestaan niet.
 */
const KAART =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200" viewBox="0 0 480 200"><rect width="480" height="200" fill="#e8efe6"/><path d="M0 140 C120 120 200 160 480 110" stroke="#9bb59a" stroke-width="18" fill="none"/><rect x="250" y="70" width="70" height="44" rx="4" fill="#3b6ea5"/><text x="285" y="97" font-family="sans-serif" font-size="13" fill="#fff" text-anchor="middle">P</text><text x="20" y="30" font-family="sans-serif" font-size="14" fill="#333">Stationsplein (verzonnen)</text></svg>`,
  );

export const VOORBEELD = `<h1>Raadsvoorstel fietsenstalling Stationsplein</h1>
<p>Het college stelt de raad voor een krediet beschikbaar te stellen voor een overdekte fietsenstalling aan het Stationsplein.</p>
<p><strong>Aanleiding</strong></p>
<p>Rond het station staan dagelijks honderden fietsen buiten de rekken. Dat belemmert voetgangers en hulpdiensten.</p>
<p><img src="${KAART}" width="480" height="200"></p>
<h3>Financiën</h3>
<table><tr><td>Onderdeel</td><td>Bedrag</td></tr><tr><td>Bouw</td><td>€ 1.200.000</td></tr><tr><td>Beheer per jaar</td><td>€ 45.000</td></tr></table>
<p>De onderbouwing van de bedragen staat <a href="https://example.org/onderbouwing">hier</a>.</p>
<h2>Besluit</h2>
<p>De raad besluit een krediet van € 1.200.000 beschikbaar te stellen.</p>`;
