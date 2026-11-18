"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Catalog = Schemas["Catalog"];
export type CatalogPage = Schemas["PaginatedCatalogList"];
export type CatalogCreateRequest = Schemas["CatalogCreateRequest"];
export type CatalogUpdateRequest = Schemas["PatchedCatalogUpdateRequest"];
export type CatalogItem = Schemas["CatalogItem"];
export type CatalogItemPage = Schemas["PaginatedCatalogItemList"];
export type CatalogItemCreateRequest = Schemas["CatalogItemCreateRequest"];
export type CatalogItemUpdateRequest = Schemas["PatchedCatalogItemUpdateRequest"];

/** Máximo de `page_size` de la API: el orden se cambia sobre todos los valores a la vez. */
export const MAX_ITEMS = 100;

export const catalogKeys = {
  all: ["admin-catalogs"] as const,
  lists: ["admin-catalogs", "list"] as const,
  list: (query: object) => ["admin-catalogs", "list", query] as const,
  detail: (id: string) => ["admin-catalogs", "detail", id] as const,
  items: (id: string) => ["admin-catalogs", "items", id] as const,
};

export type CatalogsListParams = {
  search: string;
  /** "true"/"false" (`is_public`). */
  public: string;
  ordering: string;
  page: number;
  page_size: number;
};

export function useCatalogs(params: CatalogsListParams) {
  const query = {
    search: params.search,
    is_public: params.public === "" ? undefined : params.public === "true",
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: catalogKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/catalogs", { params: { query: compact(query) } })))
        .data as CatalogPage,
    placeholderData: keepPreviousData,
  });
}

export function useCatalogDetail(id: string) {
  return useQuery({
    queryKey: catalogKeys.detail(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/catalogs/{catalog_id}", { params: { path: { catalog_id: id } } }),
        )
      ).data as Catalog,
    enabled: id !== "",
  });
}

/** Valores del catálogo en su orden (activos e inactivos), hasta `MAX_ITEMS`. */
export function useCatalogItems(id: string) {
  return useQuery({
    queryKey: catalogKeys.items(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/catalogs/{catalog_id}/items", {
            params: {
              path: { catalog_id: id },
              query: { ordering: "sort_order", page_size: MAX_ITEMS },
            },
          }),
        )
      ).data as CatalogItemPage,
    enabled: id !== "",
  });
}

function useRefresh(catalogId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: catalogKeys.all }),
      // Los catálogos viajan en el bootstrap: el resto de la app los vuelve a pedir.
      queryClient.invalidateQueries({ queryKey: ["metadata"] }),
      catalogId ? queryClient.invalidateQueries({ queryKey: catalogKeys.items(catalogId) }) : null,
    ]);
}

export function useCreateCatalog() {
  const refresh = useRefresh("");
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: CatalogCreateRequest) =>
      (await call(api.POST("/api/v1/catalogs", { body }))).data as Catalog,
    onSuccess: refresh,
  });
}

export function useUpdateCatalog(id: string) {
  const refresh = useRefresh(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: CatalogUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/catalogs/{catalog_id}", {
            params: { path: { catalog_id: id } },
            body,
          }),
        )
      ).data as Catalog,
    onSuccess: refresh,
  });
}

export function useCreateCatalogItem(catalogId: string) {
  const refresh = useRefresh(catalogId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: CatalogItemCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/catalogs/{catalog_id}/items", {
            params: { path: { catalog_id: catalogId } },
            body,
          }),
        )
      ).data as CatalogItem,
    onSuccess: refresh,
  });
}

export function useUpdateCatalogItem(catalogId: string, itemId: string) {
  const refresh = useRefresh(catalogId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: CatalogItemUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/catalog-items/{item_id}", {
            params: { path: { item_id: itemId } },
            body,
          }),
        )
      ).data as CatalogItem,
    onSuccess: refresh,
  });
}

export function useSetCatalogItemActive(catalogId: string) {
  const refresh = useRefresh(catalogId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      const options = { params: { path: { item_id: id } } };
      return (
        active
          ? (await call(api.POST("/api/v1/catalog-items/{item_id}/activate", options))).data
          : (await call(api.POST("/api/v1/catalog-items/{item_id}/deactivate", options))).data
      ) as CatalogItem;
    },
    onSuccess: refresh,
  });
}

/** `PUT /catalogs/{id}/items/order`: todos los valores, en el orden nuevo. */
export function useReorderCatalogItems(catalogId: string) {
  const refresh = useRefresh(catalogId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (item_ids: string[]) =>
      (
        await call(
          api.PUT("/api/v1/catalogs/{catalog_id}/items/order", {
            params: { path: { catalog_id: catalogId } },
            body: { item_ids },
          }),
        )
      ).data as CatalogItemPage,
    onSuccess: refresh,
  });
}
