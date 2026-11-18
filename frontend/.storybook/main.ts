import path from "node:path";

import type { StorybookConfig } from "@storybook/nextjs-vite";
import { mergeConfig } from "vite";

const frontendDir = path.resolve(import.meta.dirname, "..");
// Raíz del monorepo: los tokens se importan desde ../design/generated.
const repoRoot = path.resolve(frontendDir, "..");

const config: StorybookConfig = {
  // Documentos en src/stories/ y stories junto a cada componente.
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y", "@storybook/addon-vitest"],
  // Archivos de muestra (sin datos reales) para el visor y la carga de documentos.
  staticDirs: ["./public"],
  framework: {
    name: "@storybook/nextjs-vite",
    options: { nextConfigPath: path.join(frontendDir, "next.config.ts") },
  },
  // Sin telemetría ni avisos de Storybook: la barra lateral queda solo para Umbral.
  core: { disableTelemetry: true, disableWhatsNewNotifications: true },
  features: { sidebarOnboardingChecklist: false, menuOnboardingChecklist: false },
  viteFinal: (viteConfig) =>
    mergeConfig(viteConfig, {
      resolve: {
        alias: {
          "@design": path.join(repoRoot, "design/generated"),
          "@": path.join(frontendDir, "src"),
        },
        // `../design/generated/antd-theme.ts` importa "antd": se resuelve desde el frontend,
        // igual que en vitest.config.mts.
        dedupe: ["antd", "react", "react-dom"],
      },
      server: { fs: { allow: [repoRoot] } },
    }),
};

export default config;
