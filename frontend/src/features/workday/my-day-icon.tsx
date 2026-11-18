import type { SVGProps } from "react";

/**
 * Sol sobre el horizonte: entrada "Mi día" del menú. Decorativo, como los de
 * `components/ui/icons` (candidato a pasar a la librería).
 */
export function MyDayIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M9 2h2v3H9V2ZM3.5 5l1.4-1.4 2 2L5.5 7l-2-2Zm11.6-1.4L16.5 5l-2 2-1.4-1.4 2-2ZM10 7a5 5 0 0 1 5 5H5a5 5 0 0 1 5-5ZM2 14h16v2H2v-2Z" />
    </svg>
  );
}
