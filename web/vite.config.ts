import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  // Relative asset URLs so the built site works from any path.
  base: "./",
  define: {
    // Footer link. Set VITE_REPO_URL at build time; "#" when it is not set.
    __REPO_URL__: JSON.stringify(process.env.VITE_REPO_URL ?? "#"),
  },
  server: {
    // Only used by the dev server; the built site never calls the API unless
    // it happens to be served next to a running one.
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  resolve: {
    alias: {
      // tests/fixtures lives one level above web/.
      "@@fixtures": fileURLToPath(new URL("../tests/fixtures", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/__tests__/setup.ts",
  },
});
