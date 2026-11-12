import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@design": path.resolve(import.meta.dirname, "../design/generated"),
      "@": path.resolve(import.meta.dirname, "src"),
    },
    // `../design/generated/antd-theme.ts` importa "antd": se resuelve desde aquí.
    dedupe: ["antd", "react", "react-dom"],
  },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000/" } },
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/lib/api/schema.d.ts"],
    },
  },
});
