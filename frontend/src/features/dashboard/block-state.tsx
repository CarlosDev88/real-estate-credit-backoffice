"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { isFilterError } from "@/features/dashboard/queries";

/** Error de un filtro: el detalle va en el filtro; el bloque solo lo avisa. */
export function FilterErrorNote() {
  return (
    <p className="text-text-tertiary m-0 text-sm">
      Corrige el filtro marcado arriba para ver estos datos.
    </p>
  );
}

/**
 * Cargando, error o el contenido de un bloque. Cada bloque tiene el suyo, para que uno
 * caído no tumbe la página. Mientras llega otro filtro, el contenido anterior sigue.
 */
export function BlockState<T>({
  query,
  errorTitle,
  loadingLabel,
  loadingBlocks = [160],
  children,
}: {
  query: UseQueryResult<T>;
  errorTitle: string;
  loadingLabel: string;
  loadingBlocks?: number[];
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <LoadingState label={loadingLabel} blocks={loadingBlocks} />;
  if (query.isError) {
    if (isFilterError(query.error)) return <FilterErrorNote />;
    return (
      <ErrorState
        variant="inline"
        title={errorTitle}
        onRetry={() => void query.refetch()}
        retrying={query.isRefetching}
      />
    );
  }
  return (
    <div aria-busy={(query.isFetching && query.isPlaceholderData) || undefined}>
      {children(query.data)}
    </div>
  );
}
