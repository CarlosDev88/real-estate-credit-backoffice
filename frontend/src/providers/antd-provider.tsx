"use client";

import { darkTheme, lightTheme } from "@design/antd-theme";
import { App, ConfigProvider } from "antd";
import esES from "antd/locale/es_ES";
import type { ReactNode } from "react";

import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useTheme } from "@/providers/theme-provider";

// Mismo corte que los toasts del mockup: abajo en pantallas angostas.
const MOBILE_QUERY = "(max-width: 720px)";

export function AntdProvider({ children }: { children: ReactNode }) {
  const { mode } = useTheme();
  const isMobile = useMediaQuery(MOBILE_QUERY);

  return (
    // Los dos temas van siempre juntos: `data-theme` en <html> y este ConfigProvider.
    <ConfigProvider theme={mode === "dark" ? darkTheme : lightTheme} locale={esES}>
      <App
        notification={{
          maxCount: 3,
          stack: false,
          placement: isMobile ? "bottom" : "topRight",
          top: 72,
          bottom: 84,
        }}
      >
        {children}
      </App>
    </ConfigProvider>
  );
}
