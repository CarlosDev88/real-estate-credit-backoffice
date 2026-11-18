// Tema de Storybook: el selector de la barra (global `theme`) manda, igual que el botón de
// la app. Aplica `data-theme` en <html> y avisa a quien pinta con Ant Design o con el tema
// de los documentos, para que los dos cambien juntos.

import { GLOBALS_UPDATED, SET_GLOBALS } from "storybook/internal/core-events";
import { addons } from "storybook/preview-api";

import { applyThemeAttribute, parseTheme, type ThemeMode } from "@/lib/theme/theme";

export const THEME_GLOBAL = "theme";

let current: ThemeMode = "light";
const listeners = new Set<() => void>();

export function getStorybookTheme(): ThemeMode {
  return current;
}

export function setStorybookTheme(mode: ThemeMode): void {
  applyThemeAttribute(mode);
  if (mode === current) return;
  current = mode;
  listeners.forEach((listener) => listener());
}

export function subscribeStorybookTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Sigue los globals del canal: cubre también las páginas MDX que no tienen stories. */
export function listenToThemeGlobal(): void {
  const onGlobals = ({ globals }: { globals?: Record<string, unknown> }) =>
    setStorybookTheme(parseTheme(globals?.[THEME_GLOBAL] as string | undefined));
  try {
    const channel = addons.getChannel();
    channel.on(SET_GLOBALS, onGlobals);
    channel.on(GLOBALS_UPDATED, onGlobals);
  } catch {
    // Sin canal (stories en Vitest): el decorador aplica el tema de cada story.
  }
}
