"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/applications/list-params";
import type { ClientListParams } from "@/features/clients/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Client = Schemas["Client"];
export type ClientDetail = Schemas["ClientDetail"];
export type ClientPage = Schemas["PaginatedClientList"];
export type ClientCreateRequest = Schemas["ClientCreateRequest"];
export type ClientUpdateRequest = Schemas["PatchedClientUpdateRequest"];

/** Catálogo del origen del cliente (filtro y formulario). */
export const ORIGIN_CATALOG = "lead_origin";
/** Catálogo de tipos de documento de identidad. */
export const DOCUMENT_TYPE_CATALOG = "identity_document_type";

/** Código de error de `POST`/`PATCH /clients` con un documento que ya existe (API §13). */
export const DUPLICATE_CLIENT_DOCUMENT = "DUPLICATE_CLIENT_DOCUMENT";

export const clientKeys = {
  all: ["clients"] as const,
  lists: ["clients", "list"] as const,
  list: (params: Omit<ClientListParams, "nueva_solicitud">) => ["clients", "list", params] as const,
  detail: (id: string) => ["clients", "detail", id] as const,
};

export const clientHref = (id: string) => `/clientes/${id}`;
export const editClientHref = (id: string) => `/clientes/${id}/editar`;
export const NEW_CLIENT_HREF = "/clientes/nuevo";
export const CLIENTS_HREF = "/clientes";

/**
 * El backoffice es de asesor y administrador: `/clients` les responde la forma interna
 * (`Client` / `ClientDetail`). El contrato también describe la del broker (`BrokerClient`,
 * `oneOf`), que esta pantalla no recibe.
 */

/** `GET /clients` con el estado de la URL. Mientras llega otra página, se ve la anterior. */
export function useClientsList(params: ClientListParams) {
  // `nueva_solicitud` es solo de la vista: no va a la API ni a la clave de la caché.
  const query = {
    search: params.search,
    origin: params.origin,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: clientKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/clients", { params: { query: compact(query) } })))
        .data as ClientPage,
    placeholderData: keepPreviousData,
  });
}

/** `GET /clients/{id}`: detalle con direcciones. */
export function useClient(id: string) {
  return useQuery({
    queryKey: clientKeys.detail(id),
    queryFn: async () =>
      (await call(api.GET("/api/v1/clients/{client_id}", { params: { path: { client_id: id } } })))
        .data as ClientDetail,
  });
}

/** `POST /clients`. El formulario maneja sus errores (campo o toast). */
export function useCreateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: ClientCreateRequest) =>
      (await call(api.POST("/api/v1/clients", { body }))).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clientKeys.lists }),
  });
}

/** `PATCH /clients/{id}` con solo los campos cambiados; deja el detalle nuevo en la caché. */
export function useUpdateClient(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: ClientUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/clients/{client_id}", {
            params: { path: { client_id: id } },
            body,
          }),
        )
      ).data,
    onSuccess: (client) => {
      queryClient.setQueryData(clientKeys.detail(id), client);
      return queryClient.invalidateQueries({ queryKey: clientKeys.lists });
    },
  });
}
