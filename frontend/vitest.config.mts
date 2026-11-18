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
  // Las páginas de fundamentos leen ../design/generated como texto (`?raw`).
  server: { fs: { allow: [path.resolve(import.meta.dirname, "..")] } },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000/" } },
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
    restoreMocks: true,
    // Vitest vacía el CSS por defecto; los tokens se leen como texto en src/stories/.
    css: { include: [/design[\\/]generated[\\/](tokens|tailwind-theme)\.css/] },
    unstubGlobals: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}", "scripts/**/*.ts"],
      exclude: [
        "**/*.test.{ts,tsx}",
        // Stories: declarativos; corren aparte, en `pnpm test:storybook`.
        "**/*.stories.{ts,tsx}",
        "scripts/__fixtures__/**",
        "src/test/**",
        "src/lib/api/schema.d.ts",
      ],
      // Sin umbral aquí: el mínimo (70 % de líneas, REQ §10.5) lo aplica el paso "Cobertura"
      // del CI con `node scripts/ci-report.ts --check-coverage`.
      // Con tests fallidos también se escribe el informe, para que el reporte lo muestre.
      reportOnFailure: true,
    },
  },
});
