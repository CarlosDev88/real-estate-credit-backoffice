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
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}", "scripts/**/*.ts"],
      exclude: [
        "**/*.test.{ts,tsx}",
        "scripts/__fixtures__/**",
        "src/test/**",
        "src/lib/api/schema.d.ts",
        // Demos de desarrollo: en producción no existen.
        "src/app/(dev)/**",
      ],
      // Sin umbral aquí: el mínimo (70 % de líneas, REQ §10.5) lo aplica el paso "Cobertura"
      // del CI con `node scripts/ci-report.ts --check-coverage`.
      // Con tests fallidos también se escribe el informe, para que el reporte lo muestre.
      reportOnFailure: true,
    },
  },
});
