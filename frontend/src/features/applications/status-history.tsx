"use client";

import { Pagination } from "antd";
import { useState } from "react";

import { toneFor, type Tone } from "@design/status-tones";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import {
  HISTORY_PAGE_SIZE,
  useStatusHistory,
  type StatusHistoryEntry,
} from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";

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

/** Pestaña "Historial": la lista paginada de `status-history`. */
export function HistoryPanel({ applicationId }: { applicationId: string }) {
  const [page, setPage] = useState(1);
  const history = useStatusHistory(applicationId, page);

  if (history.isPending) return <LoadingState label="Cargando historial…" blocks={[]} />;
  if (history.isError) {
    return (
      <ErrorState
        title="No pudimos cargar el historial"
        message={history.error.message}
        onRetry={() => void history.refetch()}
        retrying={history.isFetching}
      />
    );
  }
  const { items, total } = history.data;
  if (items.length === 0) return <EmptyState title="Sin cambios de estado" />;
  return (
    <div className="grid gap-4">
      <ul className="m-0 grid list-none gap-4 p-0">
        {items.map((entry, i) => (
          <HistoryEntry key={entry.id} entry={entry} last={i === items.length - 1} />
        ))}
      </ul>
      {total > HISTORY_PAGE_SIZE && (
        <Pagination
          size="small"
          current={page}
          pageSize={HISTORY_PAGE_SIZE}
          total={total}
          onChange={setPage}
          showSizeChanger={false}
        />
      )}
    </div>
  );
}
