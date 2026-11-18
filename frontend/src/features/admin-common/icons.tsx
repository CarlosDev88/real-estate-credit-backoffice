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

/** Libro con marcador: entrada "Catálogos". */
export function CatalogIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M4 2h11a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm0 2v12h10V4h-2v5l-2-1.5L8 9V4H4Z" />
    </svg>
  );
}

/** Hoja con renglones: entrada "Documentos". */
export function DocumentsIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M5 2h7l4 4v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm1 2v12h8V7h-3V4H6Zm1 6h6v1.5H7V10Zm0 3h6v1.5H7V13Z" />
    </svg>
  );
}

/** Nodos conectados: entrada "Flujos". */
export function FlowIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M3 3h5v5H3V3Zm9 9h5v5h-5v-5ZM5 9h1.5v3.25c0 .41.34.75.75.75H11v1.5H7.25A2.25 2.25 0 0 1 5 12.25V9Zm5-4.75h3.75A2.25 2.25 0 0 1 16 6.5V11h-1.5V6.5a.75.75 0 0 0-.75-.75H10v-1.5Z" />
    </svg>
  );
}

/** Flecha arriba (subir un puesto). */
export function ArrowUpIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="M10 4 4.5 9.5l1.4 1.4L9 7.8V16h2V7.8l3.1 3.1 1.4-1.4L10 4Z" />
    </svg>
  );
}

/** Flecha abajo (bajar un puesto). */
export function ArrowDownIcon(props: IconProps) {
  return (
    <svg {...base} fill="currentColor" width={16} height={16} {...props}>
      <path d="m10 16 5.5-5.5-1.4-1.4L11 12.2V4H9v8.2L5.9 9.1 4.5 10.5 10 16Z" />
    </svg>
  );
}
