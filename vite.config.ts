import { defineConfig } from "vite";

// Bouwt de demo-werkomgeving. Wordt uitgeleverd door de integratielaag onder
// /werkomgeving/, zodat paneel en integratielaag hetzelfde adres delen.
export default defineConfig({
  root: "werkomgeving",
  base: "/werkomgeving/",
  build: { outDir: "../dist/werkomgeving", emptyOutDir: true, sourcemap: true },
  server: { proxy: { "/api": "http://localhost:3000" } },
});
