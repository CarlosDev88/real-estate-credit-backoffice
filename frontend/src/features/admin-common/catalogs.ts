"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type MetadataItem = components["schemas"]["MetadataItem"];

// Catálogos de la administración. Misma clave de caché que el resto de la app
// (`["metadata", "bootstrap"]`), así que el bootstrap se pide una sola vez.

/** `/metadata/bootstrap`: catálogos, permisos y banderas. Cambian poco. */
export function useBootstrap() {
  return useQuery({
    queryKey: ["metadata", "bootstrap"],
    queryFn: async () => (await call(api.GET("/api/v1/metadata/bootstrap"))).data,
    staleTime: 10 * 60_000,
  });
}

const activeSorted = (items: readonly MetadataItem[] | undefined) =>
  (items ?? []).filter((item) => item.active).sort((a, b) => a.order - b.order);

/** Valores activos de un catálogo del bootstrap, en el orden de la API. */
export function useCatalog(code: string): { items: MetadataItem[]; isPending: boolean } {
  const bootstrap = useBootstrap();
  const raw = bootstrap.data?.catalogs[code];
  const items = useMemo(() => activeSorted(raw), [raw]);
  return { items, isPending: bootstrap.isPending };
}

/** Etiqueta de un código del catálogo; mientras llega (o si no está), el código. */
export function labelOf(items: readonly MetadataItem[], code: string | null | undefined): string {
  if (!code) return "";
  return items.find((item) => item.code === code)?.label ?? code;
}

/** Estados del proyecto (bootstrap): etiquetas de `ProjectStatusEnum`. */
export const PROJECT_STATUS_CATALOG = "project_status";

export const MUNICIPALITY_CATALOG = "municipality";
/** Departamentos (bootstrap): padres de los municipios (`parent_code`). */
export const DEPARTMENT_CATALOG = "department";

/** Municipios: catálogo bajo demanda (no viene en el bootstrap). */
export function useMunicipalities(enabled = true) {
  const query = useQuery({
    queryKey: ["metadata", "catalogs", MUNICIPALITY_CATALOG],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/metadata/catalogs/{catalog_code}", {
            params: { path: { catalog_code: MUNICIPALITY_CATALOG } },
          }),
        )
      ).data.items,
    staleTime: 30 * 60_000,
    enabled,
  });
  const items = useMemo(() => activeSorted(query.data), [query.data]);
  return { items, isPending: query.isPending && enabled, isError: query.isError };
}

/** "Medellín (Antioquia)": el municipio con su departamento, para distinguir homónimos. */
export function cityOptionLabel(item: MetadataItem, departments: readonly MetadataItem[]): string {
  const department = item.parent_code ? labelOf(departments, item.parent_code) : "";
  return department ? `${item.label} (${department})` : item.label;
}
