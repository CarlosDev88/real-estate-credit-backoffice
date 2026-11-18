"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { applicationKeys } from "@/features/applications/queries";
import { clientKeys } from "@/features/clients/queries";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Address = Schemas["Address"];
export type AddressCreateRequest = Schemas["AddressCreateRequest"];
export type Opportunity = Schemas["Opportunity"];
export type OpportunityDetail = Schemas["OpportunityDetail"];
export type OpportunityPage = Schemas["PaginatedOpportunityList"];
export type OpportunityCreateRequest = Schemas["OpportunityCreateRequest"];
export type AssignmentCreateRequest = Schemas["AssignmentCreateRequest"];
export type ApplicationCreateRequest = Schemas["ApplicationCreateRequest"];
export type ClientApplication = Schemas["Application"];
export type Project = Schemas["Project"];
export type MetadataItem = Schemas["MetadataItem"];

/**
 * Asignación del historial de una oportunidad. El contrato la deja como objeto libre
 * (`OpportunityDetail.assignments`); estos son los campos que manda `AssignmentSerializer`.
 */
export interface OpportunityAssignment {
  id: string;
  advisor: { id: string; name: string } | null;
  assigned_by: { id: string; name: string } | null;
  reason: string;
  created_at: string;
  ended_at: string | null;
}

/** Catálogos de la Parte 2. Los valores y etiquetas vienen de la API. */
export const OPPORTUNITY_STATUS_CATALOG = "opportunity_status";
export const LOAN_PURPOSE_CATALOG = "loan_purpose";
export const ADDRESS_TYPE_CATALOG = "address_type";
export const MUNICIPALITY_CATALOG = "municipality";

/** Código de `POST /applications` cuando la oportunidad ya tiene una solicitud en curso. */
export const APPLICATION_ALREADY_OPEN = "APPLICATION_ALREADY_OPEN";

/** La API pagina de a 100 como máximo; un cliente tiene pocas oportunidades y solicitudes. */
const MAX_PAGE = 100;

export const detailKeys = {
  addresses: (clientId: string) => ["clients", "detail", clientId, "addresses"] as const,
  opportunities: (clientId: string) => ["clients", "detail", clientId, "opportunities"] as const,
  applications: (clientId: string) => ["clients", "detail", clientId, "applications"] as const,
  opportunity: (id: string) => ["opportunities", "detail", id] as const,
};

/** `GET /clients/{id}/addresses`. La primera es la principal (la API lo decide). */
export function useClientAddresses(clientId: string) {
  return useQuery({
    queryKey: detailKeys.addresses(clientId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/clients/{client_id}/addresses", {
            params: { path: { client_id: clientId }, query: { page_size: MAX_PAGE } },
          }),
        )
      ).data,
  });
}

export function useCreateAddress(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: AddressCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/clients/{client_id}/addresses", {
            params: { path: { client_id: clientId } },
            body,
          }),
        )
      ).data,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: detailKeys.addresses(clientId) }),
        queryClient.invalidateQueries({ queryKey: clientKeys.detail(clientId), exact: true }),
      ]),
  });
}

// El backoffice es de asesor y administrador: `/opportunities` les responde la forma
// interna (`Opportunity` / `OpportunityDetail`); `BrokerOpportunity` es del broker.

/** `GET /clients/{id}/opportunities`, las más recientes primero (orden de la API). */
export function useClientOpportunities(clientId: string) {
  return useQuery({
    queryKey: detailKeys.opportunities(clientId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/clients/{client_id}/opportunities", {
            params: { path: { client_id: clientId }, query: { page_size: MAX_PAGE } },
          }),
        )
      ).data as OpportunityPage,
  });
}

/** `GET /opportunities/{id}`: detalle con acciones y asignaciones (panel lateral). */
export function useOpportunity(id: string | null) {
  return useQuery({
    queryKey: detailKeys.opportunity(id ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/opportunities/{opportunity_id}", {
            params: { path: { opportunity_id: id! } },
          }),
        )
      ).data as OpportunityDetail,
    enabled: id !== null,
  });
}

export function useCreateOpportunity(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: OpportunityCreateRequest) =>
      (await call(api.POST("/api/v1/opportunities", { body }))).data as OpportunityDetail,
    onSuccess: (opportunity) => {
      queryClient.setQueryData(detailKeys.opportunity(opportunity.id), opportunity);
      return queryClient.invalidateQueries({ queryKey: detailKeys.opportunities(clientId) });
    },
  });
}

/** `POST /opportunities/{id}/assignments`: asigna el asesor y conserva el historial. */
export function useAssignOpportunity(clientId: string, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: AssignmentCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/opportunities/{opportunity_id}/assignments", {
            params: { path: { opportunity_id: id } },
            body,
          }),
        )
      ).data,
    onSuccess: (opportunity) => {
      queryClient.setQueryData(detailKeys.opportunity(id), opportunity);
      return queryClient.invalidateQueries({ queryKey: detailKeys.opportunities(clientId) });
    },
  });
}

/** `GET /clients/{id}/applications` (exige `applications.read`). */
export function useClientApplications(clientId: string, enabled: boolean) {
  return useQuery({
    queryKey: detailKeys.applications(clientId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/clients/{client_id}/applications", {
            params: { path: { client_id: clientId }, query: { page_size: MAX_PAGE } },
          }),
        )
      ).data,
    enabled,
  });
}

/**
 * `POST /applications` desde una oportunidad. La API la convierte en la misma
 * transacción: se refrescan las oportunidades, las solicitudes del cliente y el listado.
 */
export function useCreateApplication(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: ApplicationCreateRequest) =>
      (await call(api.POST("/api/v1/applications", { body }))).data,
    onSuccess: (_application, body) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: detailKeys.opportunities(clientId) }),
        queryClient.invalidateQueries({ queryKey: detailKeys.applications(clientId) }),
        queryClient.invalidateQueries({ queryKey: detailKeys.opportunity(body.opportunity_id) }),
        queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
      ]),
  });
}

/** Proyectos `ACTIVE` (los únicos que acepta una oportunidad), por nombre. */
export function useActiveProjects(enabled: boolean) {
  return useQuery({
    queryKey: ["projects", "active"],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/projects", {
            params: { query: { status: "ACTIVE", ordering: "name", page_size: MAX_PAGE } },
          }),
        )
      ).data.items,
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Municipios (catálogo bajo demanda: no viene en el bootstrap). */
export function useMunicipalities(enabled: boolean) {
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
  const items = useMemo(
    () => (query.data ?? []).filter((item) => item.active).sort((a, b) => a.order - b.order),
    [query.data],
  );
  return { items, isPending: query.isPending && enabled };
}
