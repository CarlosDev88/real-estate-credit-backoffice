import type { SVGProps } from "react";

const BASE = {
  viewBox: "0 0 20 20",
  "aria-hidden": true,
  focusable: false,
  fill: "currentColor",
  width: 16,
  height: 16,
} as const;

/**
 * Billete: entrada "Comisiones" del menú. Decorativo, como los de `components/ui/icons`
 * (candidato a pasar a la librería).
 */
export function CommissionsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...BASE} {...props}>
      <path d="M2 5h16v10H2V5Zm2 2v6h12V7H4Zm6 1a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM5 9h1v2H5V9Zm9 0h1v2h-1V9Z" />
    </svg>
  );
}

/** Monedas apiladas: entrada "Mis comisiones" del menú. Decorativo. */
export function MyCommissionsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...BASE} {...props}>
      <path d="M10 2c3.9 0 7 1.3 7 3v10c0 1.7-3.1 3-7 3s-7-1.3-7-3V5c0-1.7 3.1-3 7-3Zm0 2C6.9 4 5 4.9 5 5s1.9 1 5 1 5-.9 5-1-1.9-1-5-1ZM5 7.6V10c0 .1 1.9 1 5 1s5-.9 5-1V7.6C13.7 8.2 12 8.5 10 8.5s-3.7-.3-5-.9Zm0 5V15c0 .1 1.9 1 5 1s5-.9 5-1v-2.4c-1.3.6-3 .9-5 .9s-3.7-.3-5-.9Z" />
    </svg>
  );
}
