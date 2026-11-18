import type { SVGProps } from "react";

/**
 * Barras: entrada "Dashboard" del menú. Decorativo, como los de `components/ui/icons`
 * (candidato a pasar a la librería; aquí mientras el front 1 la migra).
 */
export function DashboardIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M3 3h2v12h12v2H3V3Zm4 7h2v4H7v-4Zm4-4h2v8h-2V6Zm4 2h2v6h-2V8Z" />
    </svg>
  );
}
