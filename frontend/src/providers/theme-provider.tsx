"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  applyThemeAttribute,
  persistTheme,
  readStoredTheme,
  type ThemeMode,
} from "@/lib/theme/theme";

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

interface ThemeProviderProps {
  /** Tema que pintó el servidor (desde la cookie). */
  initialMode: ThemeMode;
  /** `true` si el servidor recibió la cookie; si no, manda `localStorage`. */
  hasCookie: boolean;
  children: ReactNode;
}

export function ThemeProvider({ initialMode, hasCookie, children }: ThemeProviderProps) {
  const [mode, setModeState] = useState<ThemeMode>(initialMode);

  // Sin cookie, el script de <head> ya aplicó el tema de localStorage; aquí se
  // alinea React (y Ant Design) con él y se repone la cookie para la próxima carga.
  useEffect(() => {
    if (hasCookie) return;
    const stored = readStoredTheme();
    if (!stored) return;
    persistTheme(stored);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sincroniza con un valor que solo existe en el cliente
    setModeState(stored);
  }, [hasCookie]);

  const setMode = useCallback((next: ThemeMode) => {
    applyThemeAttribute(next);
    persistTheme(next);
    setModeState(next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, setMode, toggle: () => setMode(mode === "dark" ? "light" : "dark") }),
    [mode, setMode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>.");
  return ctx;
}
