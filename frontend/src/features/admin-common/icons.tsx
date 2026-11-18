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
