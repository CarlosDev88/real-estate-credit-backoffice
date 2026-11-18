import { darkTheme, lightTheme } from "@design/antd-theme";
import { DocsContainer, type DocsContainerProps } from "@storybook/addon-docs/blocks";
import type { PropsWithChildren } from "react";
import { useSyncExternalStore } from "react";
import { create } from "storybook/theming";

import type { ThemeMode } from "@/lib/theme/theme";

import { getStorybookTheme, subscribeStorybookTheme } from "./theme";

/** Tema de las páginas de documentación, leído de los tokens generados (no se copian valores). */
function docsTheme(mode: ThemeMode) {
  const token = (mode === "dark" ? darkTheme : lightTheme).token ?? {};
  return create({
    base: mode,
    brandTitle: "Umbral · Design system",
    fontBase: token.fontFamily,
    fontCode: token.fontFamilyCode,
    colorPrimary: token.colorPrimary,
    colorSecondary: token.colorPrimary,
    appBg: token.colorBgLayout,
    appContentBg: token.colorBgContainer,
    appPreviewBg: token.colorBgLayout,
    appBorderColor: token.colorBorder,
    appBorderRadius: token.borderRadiusLG,
    textColor: token.colorText,
    textMutedColor: token.colorTextSecondary,
    barBg: token.colorBgContainer,
    inputBg: token.colorBgContainer,
    inputBorder: token.colorBorder,
  });
}

const THEMES = { light: docsTheme("light"), dark: docsTheme("dark") };

/** Los documentos siguen el selector de tema de la barra, igual que los stories. */
export function UmbralDocsContainer({ children, context }: PropsWithChildren<DocsContainerProps>) {
  const mode = useSyncExternalStore(subscribeStorybookTheme, getStorybookTheme, getStorybookTheme);
  return (
    <DocsContainer context={context} theme={THEMES[mode]}>
      {children}
    </DocsContainer>
  );
}
