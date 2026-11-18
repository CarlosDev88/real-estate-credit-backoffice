import { Bar } from "@/features/dashboard/bar-list";
import type { FunnelStage } from "@/features/dashboard/queries";
import { formatInteger, formatRatio } from "@/lib/format";

const DASH = <span className="text-text-tertiary">—</span>;

/**
 * Embudo como tabla (la tabla es el gráfico): etapa, barra proporcional a la primera etapa
 * con el número escrito, conversión contra la primera y contra la anterior. Lo reusa
 * `/reportes` (embudo sin agrupar).
 */
export function FunnelTable({ stages, caption }: { stages: FunnelStage[]; caption: string }) {
  const max = Math.max(0, ...stages.map((stage) => stage.count));
  return (
    <div className="@container overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-text-secondary text-xs font-medium">
            <th scope="col" className="pb-2 text-left font-medium">
              Etapa
            </th>
            <th scope="col" className="pb-2 pl-3 text-right font-medium @[30rem]:text-left">
              Solicitudes
            </th>
            <th scope="col" className="pb-2 pl-3 text-right font-medium">
              Del total
            </th>
            <th scope="col" className="pb-2 pl-3 text-right font-medium">
              De la anterior
            </th>
          </tr>
        </thead>
        <tbody>
          {stages.map((stage) => (
            <tr key={stage.code} className="border-border-default border-t">
              <th scope="row" className="py-2.5 pr-2 text-left font-normal">
                {stage.label}
                {/* En un contenedor angosto, la barra va debajo del nombre de la etapa. */}
                <span className="mt-1.5 block @[30rem]:hidden">
                  <Bar value={stage.count} max={max} />
                </span>
              </th>
              <td className="py-2.5 pl-3">
                <span className="flex items-center justify-end gap-3 @[30rem]:justify-start">
                  <span className="hidden min-w-16 flex-1 @[30rem]:block">
                    <Bar value={stage.count} max={max} />
                  </span>
                  <span className="min-w-10 text-right font-medium tabular-nums">
                    {formatInteger(stage.count) || "0"}
                  </span>
                </span>
              </td>
              <td className="py-2.5 pl-3 text-right whitespace-nowrap tabular-nums">
                {formatRatio(stage.conversion) ?? DASH}
              </td>
              <td className="py-2.5 pl-3 text-right whitespace-nowrap tabular-nums">
                {formatRatio(stage.step_conversion) ?? DASH}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
