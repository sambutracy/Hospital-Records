import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/comfort/",
  build: { manifest: true, rollupOptions: { input: "src/main.tsx" } },
  test: { environment: "jsdom", setupFiles: ["src/test/setup.ts"], css: false },
});
