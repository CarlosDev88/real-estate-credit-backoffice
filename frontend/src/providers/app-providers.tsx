"use client";

import type { ReactNode } from "react";

import type { ThemeMode } from "@/lib/theme/theme";
import { AntdProvider } from "@/providers/antd-provider";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";

interface AppProvidersProps {
  initialTheme: ThemeMode;
  hasThemeCookie: boolean;
  children: ReactNode;
}

export function AppProviders({ initialTheme, hasThemeCookie, children }: AppProvidersProps) {
  return (
    <ThemeProvider initialMode={initialTheme} hasCookie={hasThemeCookie}>
      <AntdProvider>
        <QueryProvider>{children}</QueryProvider>
      </AntdProvider>
    </ThemeProvider>
  );
}
