"use client";

import { Alert, Button, Pagination } from "antd";
import { useMemo, useState } from "react";

import { toneFor, type Tone } from "@design/status-tones";
import { EmptyState } from "@/components/ui/empty-state";
import { useBootstrap } from "@/features/applications/queries";
import {
  HISTORY_PAGE_SIZE,
  useStatusHistory,
  type StatusHistoryEntry,
} from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";

/** Etiqueta de un estado de solicitud, desde el catálogo `application_status`. */
export type StatusLabels = (code: string) => string;

/**
 * Etiquetas de estado del catálogo `application_status` de `/metadata/bootstrap`
 * (también los inactivos: el historial puede tenerlos). El estado actual, que ya trae
 * su `status_label`, sirve de respaldo.
 */
export function useStatusLabels(currentCode?: string, currentLabel?: string): StatusLabels {
  const bootstrap = useBootstrap();
  const items = bootstrap.data?.catalogs.application_status;
  return useMemo(() => {
    const map = new Map((items ?? []).map((item) => [item.code, item.label]));
    if (currentCode && currentLabel && !map.has(currentCode)) map.set(currentCode, currentLabel);
    return (code: string) => map.get(code) ?? code;
  }, [items, currentCode, currentLabel]);
}

const DOT: Record<Tone, string> = {
  neutral: "bg-border-strong",
  info: "bg-brand-primary",
  accent: "bg-tone-accent-fg",
  success: "bg-tone-success-fg",
  warning: "bg-tone-warning-fg",
  danger: "bg-tone-danger-fg",
};

/** "Pasó de <estado> a <estado>", con quién, la versión, el motivo y el comentario. */
export function HistoryEntry({
  entry,
  labels,
  last,
}: {
  entry: StatusHistoryEntry;
  labels: StatusLabels;
  last: boolean;
}) {
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
        {entry.from_status ? (
          <>
            Pasó de <b className="font-semibold">{labels(entry.from_status)}</b> a{" "}
            <b className="font-semibold">{labels(entry.to_status)}</b>
          </>
        ) : (
          <>
            Se creó en <b className="font-semibold">{labels(entry.to_status)}</b>
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
export function HistoryPanel({
  applicationId,
  labels,
}: {
  applicationId: string;
  labels: StatusLabels;
}) {
  const [page, setPage] = useState(1);
  const history = useStatusHistory(applicationId, page);

  if (history.isPending) {
    return (
      <p role="status" className="text-text-tertiary m-0 text-sm">
        Cargando historial…
      </p>
    );
  }
  if (history.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="No pudimos cargar el historial"
        description={history.error.message}
        action={
          <Button size="small" onClick={() => void history.refetch()}>
            Reintentar
          </Button>
        }
      />
    );
  }
  const { items, total } = history.data;
  if (items.length === 0) return <EmptyState title="Sin cambios de estado" />;
  return (
    <div className="grid gap-4">
      <ul className="m-0 grid list-none gap-4 p-0">
        {items.map((entry, i) => (
          <HistoryEntry
            key={entry.id}
            entry={entry}
            labels={labels}
            last={i === items.length - 1}
          />
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
