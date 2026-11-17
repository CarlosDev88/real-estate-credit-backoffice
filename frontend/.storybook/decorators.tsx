import { AntdRegistry } from "@ant-design/nextjs-registry";
import type { Decorator } from "@storybook/nextjs-vite";
import { useEffect } from "react";
import { useGlobals } from "storybook/preview-api";

import { parseTheme, type ThemeMode } from "@/lib/theme/theme";
import { AntdProvider } from "@/providers/antd-provider";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";

import { setStorybookTheme, THEME_GLOBAL } from "./theme";

type UpdateGlobals = ReturnType<typeof useGlobals>[1];

/**
 * Los mismos providers que `app/layout.tsx`: `AntdRegistry` con `layer`, el tema (que
 * aplica `data-theme` y el `ConfigProvider` de Ant Design juntos), los toasts y Query.
 */
export const withUmbral: Decorator = (Story, context) => {
  const mode = parseTheme(context.globals[THEME_GLOBAL] as string | undefined);
  // Hook de Storybook (no de React): solo se puede llamar aquí, en el decorador.
  // eslint-disable-next-line react-hooks/rules-of-hooks -- los decoradores admiten los hooks de storybook/preview-api
  const [, updateGlobals] = useGlobals();
  // Antes de pintar: los tokens CSS y Ant Design quedan en el mismo tema desde el inicio.
  setStorybookTheme(mode);
  return (
    <AntdRegistry layer>
      {/* `key`: el provider toma el tema inicial al montar; un cambio de la barra lo remonta. */}
      <ThemeProvider key={mode} initialMode={mode} hasCookie>
        <ThemeAttributeSync mode={mode} updateGlobals={updateGlobals} />
        <AntdProvider>
          <QueryProvider>
            <Story />
          </QueryProvider>
        </AntdProvider>
      </ThemeProvider>
    </AntdRegistry>
  );
};

/**
 * Si un story cambia el tema por su cuenta (el `ThemeToggle`, por ejemplo), la barra de
 * Storybook lo sigue: así el selector, `data-theme` y Ant Design nunca quedan distintos.
 */
function ThemeAttributeSync({
  mode,
  updateGlobals,
}: {
  mode: ThemeMode;
  updateGlobals: UpdateGlobals;
}) {
  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      const next = parseTheme(root.getAttribute("data-theme"));
      if (next !== mode) updateGlobals({ [THEME_GLOBAL]: next });
    });
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [mode, updateGlobals]);
  return null;
}
