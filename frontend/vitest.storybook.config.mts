import path from "node:path";

import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

// `pnpm test:storybook`: cada story corre como una prueba en Chromium (sin abrir ventana), con
// los decoradores de .storybook/preview.tsx y la revisión de accesibilidad del addon a11y
// (falla con violaciones serias o críticas). Va aparte de `pnpm test` (jsdom, con cobertura).
export default defineConfig({
  plugins: [storybookTest({ configDir: path.join(import.meta.dirname, ".storybook") })],
  // Optimizadas desde el inicio: si Vite las descubre a mitad de la corrida, recarga la
  // página y los stories de ese momento fallan al azar.
  optimizeDeps: {
    include: [
      "antd",
      "@ant-design/nextjs-registry",
      "@tanstack/react-query",
      "@tanstack/react-table",
      "react-hook-form",
      "@hookform/resolvers/zod",
      "zod",
    ],
  },
  test: {
    name: "storybook",
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [{ browser: "chromium" }],
    },
  },
});
