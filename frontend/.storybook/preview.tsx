// Mismas fuentes y estilos globales que app/layout.tsx (tokens, Tailwind y capas CSS).
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "../src/app/globals.css";
import "./docs.css";

import type { Preview } from "@storybook/nextjs-vite";

import { withUmbral } from "./decorators";
import { UmbralDocsContainer } from "./docs-container";
import { listenToThemeGlobal, THEME_GLOBAL } from "./theme";

listenToThemeGlobal();

const preview: Preview = {
  tags: ["autodocs"],
  globalTypes: {
    [THEME_GLOBAL]: {
      description: "Tema de Umbral: aplica data-theme y el tema de Ant Design juntos",
      toolbar: {
        title: "Tema",
        icon: "mirror",
        items: [
          { value: "light", title: "Claro", icon: "sun" },
          { value: "dark", title: "Oscuro", icon: "moon" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { [THEME_GLOBAL]: "light" },
  decorators: [withUmbral],
  parameters: {
    layout: "padded",
    // La app usa el App Router: `next/navigation` (usePathname, useRouter) va simulado.
    nextjs: { appDirectory: true },
    // El fondo lo pone el tema (`bg.canvas`), no el addon de fondos.
    backgrounds: { disable: true },
    viewport: {
      options: {
        movil: {
          name: "Móvil · 390",
          styles: { width: "390px", height: "844px" },
          type: "mobile",
        },
        portatil: {
          name: "Portátil · 1280",
          styles: { width: "1280px", height: "800px" },
          type: "desktop",
        },
        escritorio: {
          name: "Escritorio · 1440",
          styles: { width: "1440px", height: "900px" },
          type: "desktop",
        },
      },
    },
    a11y: {
      // Falla el story (en `pnpm test:storybook`) con violaciones serias o críticas; las
      // leves y moderadas se ven en el panel de accesibilidad, pero no lo hacen fallar.
      test: "error",
      options: { impactLevels: ["serious", "critical"] },
    },
    controls: {
      expanded: true,
      matchers: { color: /(background|color)$/i, date: /Date$/i },
    },
    // El índice lista las secciones de cada página (los `##` del MDX).
    docs: { container: UmbralDocsContainer, toc: { headingSelector: "h2" } },
    options: {
      storySort: {
        order: [
          "Introducción",
          "Guía de uso",
          "Fundamentos",
          [
            "Colores",
            "Tipografía",
            "Espaciado",
            "Radios",
            "Sombras y elevación",
            "Tonos de estado",
            "Redacción",
          ],
          "Componentes",
          "Patrones",
          [
            "Formulario con validación",
            "Lista con filtros en la URL",
            "Tabla con orden y paginación",
            "Panel lateral de revisión",
            "Modal de confirmación",
            "Carga de archivo",
            "Estados vacío, cargando y error",
            "Encabezado de página",
          ],
        ],
      },
    },
  },
};

export default preview;
