// Íconos de administración. Viven aquí hasta que pasen a `components/ui/icons.tsx`
// (candidatos a la librería, F6). Decorativos: el texto accesible va en el control.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = { viewBox: "0 0 20 20", "aria-hidden": true, focusable: false } as const;

/** Persona con escudo: entrada "Usuarios" del grupo "Administración". */
export function UserShieldIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M7.5 2.5a3.25 3.25 0 1 1 0 6.5 3.25 3.25 0 0 1 0-6.5ZM1.5 16c0-3 2.7-5 6-5 1 0 1.9.2 2.7.5V17H1.5v-1ZM15 9.5l3.5 1.4v2.4c0 2.2-1.5 3.9-3.5 4.7-2-.8-3.5-2.5-3.5-4.7v-2.4L15 9.5Z" />
    </svg>
  );
}

/** Edificio: entrada "Constructoras". */
export function BuildingIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M3 2h9v5h5v11H3V2Zm2 2v12h2v-3h2v3h1V4H5Zm1 1h2v2H6V5Zm0 4h2v2H6V9Zm6 0v7h3V9h-3Z" />
    </svg>
  );
}

/** Plano con grúa: entrada "Proyectos". */
export function ProjectIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M2 3h10v2H8v3h4l5 4v6H3v-6l3-2.4V5H2V3Zm3 10v3h3v-3H5Zm5 0v3h5v-3.1L12 10.6V13h-2Z" />
    </svg>
  );
}

/** Edificio con columnas: entrada "Bancos". */
export function BankIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M10 2 18 6v2H2V6l8-4ZM4 9h2v6H4V9Zm5 0h2v6H9V9Zm5 0h2v6h-2V9ZM2 16h16v2H2v-2Z" />
    </svg>
  );
}
