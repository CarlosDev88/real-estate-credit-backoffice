import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./globals.css";

import { AntdRegistry } from "@ant-design/nextjs-registry";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { parseTheme, THEME_COOKIE, THEME_FALLBACK_SCRIPT } from "@/lib/theme/theme";
import { AppProviders } from "@/providers/app-providers";

export const metadata: Metadata = {
  title: { default: "Umbral", template: "%s · Umbral" },
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const themeCookie = (await cookies()).get(THEME_COOKIE)?.value;
  const theme = parseTheme(themeCookie);

  return (
    // El script de respaldo puede cambiar `data-theme` antes de hidratar.
    <html lang="es" data-theme={theme} suppressHydrationWarning>
      <head>
        {themeCookie === undefined && (
          <script dangerouslySetInnerHTML={{ __html: THEME_FALLBACK_SCRIPT }} />
        )}
      </head>
      <body>
        {/* `layer` mete los estilos de Ant Design en la capa CSS `antd`. */}
        <AntdRegistry layer>
          <AppProviders initialTheme={theme} hasThemeCookie={themeCookie !== undefined}>
            {children}
          </AppProviders>
        </AntdRegistry>
      </body>
    </html>
  );
}
