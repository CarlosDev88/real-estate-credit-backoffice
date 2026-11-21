"use client";

import { Pagination } from "antd";
import { useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { HISTORY_PAGE_SIZE, useStatusHistory } from "@/features/applications/workspace-queries";
import { HistoryEntry } from "@/features/applications/status-history-entry";

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
