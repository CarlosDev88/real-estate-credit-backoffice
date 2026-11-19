import type { SVGProps } from "react";

/**
 * Persona con un más: entrada "Mis prospectos" del menú del broker. Decorativo, como los
 * de `components/ui/icons` (candidato a pasar a la librería).
 */
export function BrokerIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M8 3a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Zm0 8.5c3.3 0 6 1.6 6 3.8V17H2v-1.7c0-2.2 2.7-3.8 6-3.8ZM15 6h1.5v2.5H19V10h-2.5v2.5H15V10h-2.5V8.5H15V6Z" />
    </svg>
  );
}
