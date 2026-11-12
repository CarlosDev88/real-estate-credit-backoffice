import { toneFor, type StatusKind, type Tone } from "@design/status-tones";

// Clases completas (no interpoladas) para que Tailwind las detecte.
export const TONE_CLASS: Record<Tone, string> = {
  neutral: "text-tone-neutral-fg bg-tone-neutral-bg border-tone-neutral-border",
  info: "text-tone-info-fg bg-tone-info-bg border-tone-info-border",
  accent: "text-tone-accent-fg bg-tone-accent-bg border-tone-accent-border",
  success: "text-tone-success-fg bg-tone-success-bg border-tone-success-border",
  warning: "text-tone-warning-fg bg-tone-warning-bg border-tone-warning-border",
  danger: "text-tone-danger-fg bg-tone-danger-bg border-tone-danger-border",
};

interface StatusBadgeProps {
  /** Qué tipo de estado es (solicitud, documento, archivo, regla). */
  kind: StatusKind;
  /** Código del estado; solo decide el color. Un código desconocido es `neutral`. */
  code: string | null | undefined;
  /** Texto del estado: siempre viene de la API. */
  label: string;
  className?: string;
}

/** Etiqueta de estado: punto de color y texto de la API (el estado nunca es solo color). */
export function StatusBadge({ kind, code, label, className = "" }: StatusBadgeProps) {
  const tone = toneFor(kind, code);
  return (
    <span
      data-tone={tone}
      className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium whitespace-nowrap ${TONE_CLASS[tone]} ${className}`}
    >
      <span aria-hidden="true" className="size-1.5 flex-none rounded-full bg-current" />
      {label}
    </span>
  );
}
