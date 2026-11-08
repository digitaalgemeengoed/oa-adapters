import { resolve } from "node:path";
import { defineConfig } from "vite";

// Bouwt de pagina's van de werkomgevingen. De integratielaag levert ze uit
// op haar eigen adres, zodat paneel en API hetzelfde adres delen:
//   /werkomgeving/     demo-tekstverwerker
//   /word/             takenvenster en aanmeldvenster van de Word-invoegtoepassing
//   /collabora/        Collabora Online met het paneel ernaast
//   /libreoffice/      het paneel naast LibreOffice op de eigen computer
const pagina = (p: string) => resolve(__dirname, p);

export default defineConfig({
  root: __dirname,
  base: "/",
  publicDir: "statisch",
  build: {
    outDir: "dist/web",
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        werkomgeving: pagina("werkomgeving/index.html"),
        taskpane: pagina("word/taskpane.html"),
        aanmelden: pagina("word/aanmelden.html"),
        collabora: pagina("collabora/index.html"),
        libreoffice: pagina("libreoffice/index.html"),
      },
    },
  },
  server: { proxy: { "/api": "http://localhost:3000" } },
});
