// Íconos propios de clientes. Candidatos a `components/ui/icons.tsx` (dueño: front 1).
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = { viewBox: "0 0 20 20", "aria-hidden": true, focusable: false } as const;

/** Personas: entrada "Clientes" del menú. */
export function UsersIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M7.5 3a3.25 3.25 0 1 1 0 6.5 3.25 3.25 0 0 1 0-6.5ZM1.5 16.5c0-3 2.7-5 6-5s6 2 6 5V17h-12v-.5ZM13.6 3.2a3.1 3.1 0 0 1 0 6.1 4.7 4.7 0 0 0 0-6.1ZM15 17v-.5c0-1.8-.7-3.3-1.9-4.4 2.9.3 5.4 1.9 5.4 4.4v.5H15Z" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M9 3h2v6h6v2h-6v6H9v-6H3V9h6V3Z" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M8.5 2a6.5 6.5 0 0 1 5.2 10.4l4.2 4.2-1.4 1.4-4.2-4.2A6.5 6.5 0 1 1 8.5 2Zm0 2a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9Z" />
    </svg>
  );
}

export function FilterIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M3 4h14v2l-5 5v5l-4 1v-6L3 6V4Z" />
    </svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="m12.6 4 1.4 1.4L9.4 10l4.6 4.6-1.4 1.4-6-6 6-6Z" />
    </svg>
  );
}
