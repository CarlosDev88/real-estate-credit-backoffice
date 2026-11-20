"use client";

import { toneFor, type Tone } from "@design/status-tones";
import type { StatusHistoryEntry } from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";

// Una entrada del historial de estados. Aparte del panel paginado (`status-history.tsx`): el
// Resumen la usa en la primera carga y el panel, con su paginación, se carga al abrirlo (PERF-01).

const DOT: Record<Tone, string> = {
  neutral: "bg-border-strong",
  info: "bg-brand-primary",
  accent: "bg-tone-accent-fg",
  success: "bg-tone-success-fg",
  warning: "bg-tone-warning-fg",
  danger: "bg-tone-danger-fg",
};

/**
 * "Pasó de <estado> a <estado>" (etiquetas `from_status_label` y `to_status_label` de la
 * API), con quién, la versión, el motivo y el comentario.
 */
export function HistoryEntry({ entry, last }: { entry: StatusHistoryEntry; last: boolean }) {
  const who = entry.actor?.name ?? (entry.buyer_session_id ? "portal del comprador" : null);
  const meta = [formatDateTime(entry.created_at), who, `versión ${entry.application_version}`]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="relative grid grid-cols-[12px_1fr] gap-3 text-sm">
      <span
        aria-hidden="true"
        className={`mt-[5px] size-2.5 rounded-full ${DOT[toneFor("application", entry.to_status)]}`}
      />
      {!last && (
        <span
          aria-hidden="true"
          className="bg-border-default absolute top-[18px] -bottom-[14px] left-1 w-0.5"
        />
      )}
      <div>
        {entry.from_status_label ? (
          <>
            Pasó de <b className="font-semibold">{entry.from_status_label}</b> a{" "}
            <b className="font-semibold">{entry.to_status_label}</b>
          </>
        ) : (
          <>
            Se creó en <b className="font-semibold">{entry.to_status_label}</b>
          </>
        )}
        <small className="text-text-tertiary mt-0.5 block text-xs">{meta}</small>
        {entry.reason && (
          <span className="text-text-secondary mt-1 block">Motivo: {entry.reason.label}</span>
        )}
        {entry.comment && (
          <q className="bg-bg-subtle text-text-secondary mt-1 block rounded-md px-2.5 py-1.5 [quotes:none]">
            {entry.comment}
          </q>
        )}
      </div>
    </li>
  );
}
