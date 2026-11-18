"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { BrokerParams } from "@/features/broker/broker-params";
import { api, call } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type BrokerOpportunity = Schemas["BrokerOpportunity"];
export type ApplicationSummary = Schemas["ApplicationSummary"];
export type ClientCreateRequest = Schemas["ClientCreateRequest"];
export type StatusCount = Schemas["StatusCount"];

/** Código del origen "broker" del catálogo `lead_origin` (código de la API, no un texto). */
export const BROKER_ORIGIN = "BROKER";
/** Códigos de `409` de la API al dar de alta. */
export const DUPLICATE_CLIENT_DOCUMENT = "DUPLICATE_CLIENT_DOCUMENT";
export const DUPLICATE_OPPORTUNITY = "DUPLICATE_OPPORTUNITY";

export const brokerKeys = {
  all: ["broker"] as const,
  opportunities: (status: string, page: number, pageSize: number) =>
    ["broker", "opportunities", status, page, pageSize] as const,
  applications: (page: number, pageSize: number) =>
    ["broker", "applications", page, pageSize] as const,
  snapshot: ["broker", "snapshot"] as const,
};

/** Bandeja del broker: `GET /broker/opportunities` (solo sus prospectos, en resumen). */
export function useBrokerOpportunities(params: BrokerParams, enabled: boolean) {
  return useQuery({
    queryKey: brokerKeys.opportunities(params.status, params.page, params.page_size),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/broker/opportunities", {
            params: {
              query: {
                page: params.page,
                page_size: params.page_size,
                ...(params.status ? { status: params.status } : {}),
              },
            },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/**
 * Solicitudes de sus prospectos: `GET /applications`. Al broker la API le responde el
 * resumen (`ApplicationSummary`: sin finanzas, inmueble ni documentos), aunque el
 * contrato declare `Application` en esa ruta.
 */
export function useBrokerApplications(params: BrokerParams, enabled: boolean) {
  return useQuery({
    queryKey: brokerKeys.applications(params.page, params.page_size),
    queryFn: async () => {
      const { data } = await call(
        api.GET("/api/v1/applications", {
          params: { query: { page: params.page, page_size: params.page_size } },
        }),
      );
      return { ...data, items: data.items as unknown as ApplicationSummary[] };
    },
    placeholderData: keepPreviousData,
    enabled,
  });
}

/**
 * Foto de hoy por estado de sus solicitudes (`GET /dashboard/summary`, `snapshot`): al
 * broker solo le llegan conteos. Un `403` no es error: no se muestra el bloque.
 */
export function useStatusSnapshot(enabled: boolean) {
  return useQuery({
    queryKey: brokerKeys.snapshot,
    queryFn: async () => {
      try {
        return (await call(api.GET("/api/v1/dashboard/summary"))).data.snapshot;
      } catch (error) {
        if (isApiError(error) && error.status === 403) return null;
        throw error;
      }
    },
    enabled,
  });
}

/** Id del cliente que ya existe y el broker puede ver (`409` con `resource_id`). */
export function existingClientId(error: unknown): string | null {
  if (!isApiError(error) || error.code !== DUPLICATE_CLIENT_DOCUMENT) return null;
  return error.details.find((d) => d.resource_id)?.resource_id ?? null;
}

export interface ProspectInput {
  client: ClientCreateRequest;
  project_id: string | null;
  notes: string;
  /** Cliente ya creado en un intento anterior (no se vuelve a crear al reintentar). */
  clientId: string | null;
}

export interface ProspectResult {
  clientId: string;
  /** El cliente ya existía (el `409` trajo su id): solo se creó la oportunidad. */
  existing: boolean;
}

/**
 * Alta de un prospecto: el cliente (`POST /clients`) y su oportunidad (`POST
 * /opportunities`, origen broker). Si el documento ya existe y el broker lo ve, usa ese
 * cliente. Si la oportunidad falla, el error lleva el cliente creado para reintentar.
 */
export function useCreateProspect() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (input: ProspectInput): Promise<ProspectResult> => {
      let clientId = input.clientId;
      let existing = false;
      if (!clientId) {
        try {
          clientId = (await call(api.POST("/api/v1/clients", { body: input.client }))).data.id;
        } catch (error) {
          const found = existingClientId(error);
          if (!found) throw error;
          clientId = found;
          existing = true;
        }
      }
      try {
        await call(
          api.POST("/api/v1/opportunities", {
            body: {
              client_id: clientId,
              origin_type: BROKER_ORIGIN,
              project_id: input.project_id,
              ...(input.notes ? { notes: input.notes } : {}),
            },
          }),
        );
      } catch (error) {
        throw new ProspectError(error, clientId);
      }
      return { clientId, existing };
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: brokerKeys.all }),
  });
}

/** Falló la oportunidad después de crear (o encontrar) el cliente. */
export class ProspectError extends Error {
  /** El error de `POST /opportunities`. */
  readonly reason: unknown;
  readonly clientId: string;

  constructor(reason: unknown, clientId: string) {
    super(reason instanceof Error ? reason.message : "No se pudo crear la oportunidad.");
    this.reason = reason;
    this.clientId = clientId;
  }
}
