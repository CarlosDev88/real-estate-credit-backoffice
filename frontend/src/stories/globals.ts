// Globals de Storybook para los stories "Oscuro" y "Móvil" de cada componente.

/** Tema oscuro: `data-theme="dark"` y `darkTheme` de Ant Design. */
export const DARK = { theme: "dark" } as const;

/** Viewport de 390 px (`movil` en .storybook/preview.tsx). */
export const MOBILE = { viewport: { value: "movil", isRotated: false } } as const;

/** Fecha ISO de hace `minutes` minutos (para `RelativeTime`). */
export function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}
