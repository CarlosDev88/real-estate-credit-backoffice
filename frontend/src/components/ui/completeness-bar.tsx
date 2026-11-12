import { formatPercent } from "@/lib/format";

function clamp(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

/** Barra simple. Siempre en el color de marca: el teal es estado, no avance. */
function Bar({ value, label, thick = false }: { value: number; label: string; thick?: boolean }) {
  const pct = clamp(value);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={`bg-bg-muted flex-1 overflow-hidden rounded-full ${thick ? "h-2" : "h-1.5"}`}
    >
      <div className="bg-brand-primary h-full rounded-full" style={{ width: `${pct}%` }} />
    </div>
  );
}

interface CompletenessBarProps {
  /** `percentage` de la API: promedio de datos y documentos. */
  percentage: number;
  dataPercentage?: number;
  documentsPercentage?: number;
  documentsCompleted?: number;
  documentsRequired?: number;
  /** `mini`: barra corta con el porcentaje (filas del listado). */
  variant?: "full" | "mini";
  className?: string;
}

/** Completitud del expediente (mockups `solicitud.html` y `solicitudes.html`). */
export function CompletenessBar({
  percentage,
  dataPercentage,
  documentsPercentage,
  documentsCompleted,
  documentsRequired,
  variant = "full",
  className = "",
}: CompletenessBarProps) {
  if (variant === "mini") {
    return (
      <div className={`flex w-20 items-center gap-2 ${className}`}>
        <Bar value={percentage} label="Completitud del expediente" />
        <span className="text-text-secondary min-w-[38px] text-right text-xs whitespace-nowrap tabular-nums">
          {formatPercent(percentage)}
        </span>
      </div>
    );
  }

  const documentsText =
    documentsRequired !== undefined && documentsCompleted !== undefined
      ? `${documentsCompleted} de ${documentsRequired} · ${formatPercent(documentsPercentage ?? 0)}`
      : formatPercent(documentsPercentage ?? 0);

  return (
    <div className={`grid gap-3 ${className}`}>
      <div className="flex items-center gap-3">
        <Bar value={percentage} label="Completitud total" thick />
        <span className="text-text-secondary text-sm whitespace-nowrap tabular-nums">
          {formatPercent(percentage)} en total
        </span>
      </div>
      {dataPercentage !== undefined && (
        <div className="grid gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-text-secondary">Datos</span>
            <b className="font-medium tabular-nums">{formatPercent(dataPercentage)}</b>
          </div>
          <Bar value={dataPercentage} label="Completitud de datos" />
        </div>
      )}
      {documentsPercentage !== undefined && (
        <div className="grid gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-text-secondary">Documentos</span>
            <b className="font-medium tabular-nums">{documentsText}</b>
          </div>
          <Bar value={documentsPercentage} label="Completitud de documentos" />
        </div>
      )}
    </div>
  );
}
