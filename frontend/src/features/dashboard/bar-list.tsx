import type { ReactNode } from "react";

import type { Tone } from "@design/status-tones";

// Barras horizontales en HTML/CSS (sin librería de gráficos): cada fila tiene su texto y
// su número escritos, así que la lista misma es la tabla equivalente y la barra es
// decorativa (`aria-hidden`). Candidato a la librería (`components/ui`).

/** Relleno de la barra por tono (clases completas para que Tailwind las detecte). */
export const BAR_FILL: Record<Tone | "brand", string> = {
  brand: "bg-brand-primary",
  neutral: "bg-tone-neutral-fg",
  info: "bg-tone-info-fg",
  accent: "bg-tone-accent-fg",
  success: "bg-tone-success-fg",
  warning: "bg-tone-warning-fg",
  danger: "bg-tone-danger-fg",
};

/** Ancho de la barra en %: proporcional al mayor; un valor > 0 se ve aunque sea pequeño. */
export function barWidth(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  return Math.max(1.5, Math.min(100, (value / max) * 100));
}

/** Barra fina con el extremo de datos redondeado, anclada a la izquierda. */
export function Bar({
  value,
  max,
  fill = "brand",
}: {
  value: number;
  max: number;
  fill?: Tone | "brand";
}) {
  const width = barWidth(value, max);
  return (
    <span aria-hidden="true" className="bg-bg-muted block h-2 w-full overflow-hidden rounded-r">
      {width > 0 && (
        <span
          data-testid="bar-fill"
          className={`block h-full rounded-r ${BAR_FILL[fill]}`}
          style={{ width: `${width}%` }}
        />
      )}
    </span>
  );
}

export interface BarItem {
  key: string;
  /** Texto de la fila (viene de la API). */
  label: ReactNode;
  value: number;
  /** Número escrito junto a la barra (por defecto, `value`). */
  display?: ReactNode;
  fill?: Tone | "brand";
  /** Marca antes del texto (por ejemplo, el punto del tono). */
  marker?: ReactNode;
}

/**
 * Lista de barras: nombre, barra y número. En un contenedor angosto, la barra baja debajo
 * del nombre y el número queda a la derecha.
 */
export function BarList({ items, ariaLabel }: { items: BarItem[]; ariaLabel: string }) {
  const max = Math.max(0, ...items.map((item) => item.value));
  return (
    <div className="@container">
      <ul aria-label={ariaLabel} className="m-0 grid list-none gap-3 p-0">
        {items.map((item) => (
          <li
            key={item.key}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 text-sm @[30rem]:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_3.5rem]"
          >
            <span className="col-start-1 row-start-1 flex min-w-0 items-center gap-2">
              {item.marker}
              <span className="min-w-0 break-words">{item.label}</span>
            </span>
            <span className="col-span-2 col-start-1 row-start-2 @[30rem]:col-span-1 @[30rem]:col-start-2 @[30rem]:row-start-1">
              <Bar value={item.value} max={max} fill={item.fill} />
            </span>
            <span className="col-start-2 row-start-1 text-right font-medium tabular-nums @[30rem]:col-start-3">
              {item.display ?? item.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
