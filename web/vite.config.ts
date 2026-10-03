import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built output is shipped inside the Python package; relative base so it
// serves from wherever the review server mounts it.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../src/photoflow/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/img": "http://127.0.0.1:8765" } },
});
