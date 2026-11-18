import type { components } from "@/lib/api/schema";

export type ProgressStage = components["schemas"]["ProgressStage"];

function CheckIcon({ size }: { size: number }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={size} height={size} aria-hidden="true">
      <path d="M8 13.2 4.8 10l-1.4 1.4L8 16l9-9-1.4-1.4L8 13.2Z" />
    </svg>
  );
}

const LINE = "absolute top-[9px] h-0.5";

interface StepperProps {
  /** Etapas de la API (`progress_stages` o `stages`), con `label` y `state_label`. */
  stages: ProgressStage[];
  ariaLabel: string;
  /**
   * `horizontal`: línea del expediente (mockup `solicitud.html`); en pantallas angostas se
   * desplaza. `vertical`: lista del portal, dentro de la tarjeta de estado (fondo oscuro).
   */
  orientation?: "horizontal" | "vertical";
}

/**
 * Etapas de una solicitud. El estado de cada una va también en texto (`state_label`), no
 * solo en el color, y la actual lleva `aria-current="step"`. Sin etapas no se pinta.
 */
export function Stepper({ stages, ariaLabel, orientation = "horizontal" }: StepperProps) {
  if (stages.length === 0) return null;
  if (orientation === "vertical") return <VerticalStepper stages={stages} ariaLabel={ariaLabel} />;
  return (
    // Región enfocable: en móvil se desplaza y debe poder recorrerse con el teclado.
    <div role="region" aria-label={ariaLabel} tabIndex={0} className="overflow-x-auto">
      <ol className="m-0 flex list-none p-0">
        {stages.map((stage, i) => {
          const done = stage.state === "done";
          const current = stage.state === "current";
          const first = i === 0;
          const last = i === stages.length - 1;
          return (
            <li
              key={stage.code}
              aria-current={current ? "step" : undefined}
              className={`relative min-w-[110px] flex-1 pt-[26px] text-center text-xs ${
                done || current ? "text-text-primary" : "text-text-tertiary"
              } ${current ? "font-semibold" : ""}`}
            >
              {/* Mitad izquierda y derecha de la línea, para que la actual quede a medias. */}
              {!first && (
                <span
                  aria-hidden="true"
                  className={`${LINE} left-0 w-1/2 ${done || current ? "bg-brand-primary" : "bg-border-default"}`}
                />
              )}
              {!last && (
                <span
                  aria-hidden="true"
                  className={`${LINE} right-0 w-1/2 ${done ? "bg-brand-primary" : "bg-border-default"}`}
                />
              )}
              <span
                aria-hidden="true"
                className={`absolute top-0.5 left-1/2 grid size-4 -translate-x-1/2 place-items-center rounded-full border-2 ${
                  done
                    ? "bg-brand-primary border-brand-primary text-brand-on-primary"
                    : current
                      ? "bg-bg-surface border-brand-primary shadow-[0_0_0_4px_var(--um-brand-subtle)]"
                      : "bg-bg-surface border-border-strong"
                }`}
              >
                {done && <CheckIcon size={10} />}
                {current && <span className="bg-brand-primary size-1.5 rounded-full" />}
              </span>
              {stage.label}
              <span className="sr-only">: {stage.state_label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Lista vertical sobre `bg.sidebar` (tarjeta de estado del portal). */
function VerticalStepper({ stages, ariaLabel }: { stages: ProgressStage[]; ariaLabel: string }) {
  return (
    <ol aria-label={ariaLabel} className="m-0 grid list-none p-0">
      {stages.map((stage, index) => {
        const last = index === stages.length - 1;
        const done = stage.state === "done";
        const current = stage.state === "current";
        return (
          <li
            key={stage.code}
            aria-current={current ? "step" : undefined}
            className={`text-md relative grid grid-cols-[22px_1fr] gap-3 ${last ? "" : "pb-3"} ${
              current ? "text-text-on-sidebar-strong font-medium" : ""
            }`}
          >
            {!last && (
              <span
                aria-hidden="true"
                className="bg-sidebar-item-active absolute top-6 bottom-0.5 left-2.5 w-0.5"
              />
            )}
            <span
              aria-hidden="true"
              className={`grid size-[22px] place-items-center rounded-full border-2 ${
                done
                  ? "bg-text-on-sidebar-strong border-text-on-sidebar-strong text-bg-sidebar"
                  : current
                    ? "border-text-on-sidebar-strong"
                    : "border-text-on-sidebar"
              }`}
            >
              {done && <CheckIcon size={12} />}
              {current && <span className="bg-text-on-sidebar-strong size-2 rounded-full" />}
            </span>
            <div>
              {stage.label}
              <small className="text-text-on-sidebar block text-xs font-normal">
                {stage.state_label}
              </small>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
