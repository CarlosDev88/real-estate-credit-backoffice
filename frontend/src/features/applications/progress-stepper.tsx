import type { components } from "@/lib/api/schema";

type ProgressStage = components["schemas"]["ProgressStage"];

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={10} height={10} aria-hidden="true">
      <path d="M8 13.2 4.8 10l-1.4 1.4L8 16l9-9-1.4-1.4L8 13.2Z" />
    </svg>
  );
}

const LINE = "absolute top-[9px] h-0.5";

/**
 * Etapas del expediente (`progress_stages`, mockup `solicitud.html`): línea horizontal
 * que en pantallas angostas se desplaza. El estado de cada etapa también va en texto
 * (`state_label`), no solo en el color. Sin etapas (solicitud cerrada sin resultado),
 * no se pinta.
 */
export function ProgressStepper({ stages }: { stages: ProgressStage[] }) {
  if (stages.length === 0) return null;
  return (
    // Región enfocable: en móvil se desplaza y debe poder recorrerse con el teclado.
    <div role="region" aria-label="Etapas de la solicitud" tabIndex={0} className="overflow-x-auto">
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
                {done && <CheckIcon />}
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
