"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { compact, type ListFilters, type ListParams } from "@/features/applications/list-params";
import { api, call } from "@/lib/api/client";
import type { components, operations } from "@/lib/api/schema";

export type Application = components["schemas"]["Application"];
export type ApplicationPage = components["schemas"]["PaginatedApplicationList"];
export type QuickFilter = components["schemas"]["QuickFilter"];
export type Bank = components["schemas"]["Bank"];
export type MetadataItem = components["schemas"]["MetadataItem"];

type ListQuery = NonNullable<operations["applications_list"]["parameters"]["query"]>;

export const applicationKeys = {
  all: ["applications"] as const,
  list: (params: ListParams) => ["applications", "list", params] as const,
  quickFilters: (filters: ListFilters) => ["applications", "quick-filters", filters] as const,
};

/** `GET /applications` con el estado de la URL. Mientras llega otra página, se ve la anterior. */
export function useApplicationsList(params: ListParams) {
  return useQuery({
    queryKey: applicationKeys.list(params),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications", {
            // `quick_filter` sale de la URL; si la API no lo conoce, responde 400.
            params: { query: compact(params) as ListQuery },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

/** Pestañas del listado con su conteo, con los mismos filtros (sin `quick_filter`). */
export function useQuickFilters(filters: ListFilters) {
  return useQuery({
    queryKey: applicationKeys.quickFilters(filters),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/quick-filters", { params: { query: compact(filters) } }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

/** Bancos activos para el filtro (la API pagina de a 100 como máximo). */
export function useActiveBanks(enabled: boolean) {
  return useQuery({
    queryKey: ["banks", "active"],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/banks", {
            params: { query: { status: "ACTIVE", ordering: "name", page_size: 100 } },
          }),
        )
      ).data.items,
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Nombre del banco para listas: `short_name`, o `name` si viene vacío. */
export function bankLabel(bank: { name: string; short_name: string }): string {
  return bank.short_name.trim() || bank.name;
}

/**
 * Metadatos de `/metadata/bootstrap` (catálogos, permisos y banderas). Cambian poco:
 * se cachean y el navegador revalida con `If-None-Match`.
 */
export function useBootstrap() {
  return useQuery({
    queryKey: ["metadata", "bootstrap"],
    queryFn: async () => (await call(api.GET("/api/v1/metadata/bootstrap"))).data,
    staleTime: 10 * 60_000,
  });
}

/** Valores activos de un catálogo del bootstrap, en el orden de la API. */
export function useCatalog(code: string): { items: MetadataItem[]; isPending: boolean } {
  const bootstrap = useBootstrap();
  const raw = bootstrap.data?.catalogs[code];
  const items = useMemo(
    () => (raw ?? []).filter((item) => item.active).sort((a, b) => a.order - b.order),
    [raw],
  );
  return { items, isPending: bootstrap.isPending };
}
