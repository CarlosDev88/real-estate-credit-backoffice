import type { SVGProps } from "react";

/**
 * Hoja con una tabla: entrada "Reportes" del menú. Decorativo, como los de
 * `components/ui/icons` (candidato a pasar a la librería).
 */
export function ReportsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      width={16}
      height={16}
      {...props}
    >
      <path d="M4 2h9l3 3v13H4V2Zm2 6v2h3V8H6Zm5 0v2h3V8h-3Zm-5 4v2h3v-2H6Zm5 0v2h3v-2h-3Z" />
    </svg>
  );
}
