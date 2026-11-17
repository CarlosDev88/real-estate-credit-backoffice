"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, call } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type BuyerSession = Schemas["BuyerSessionResponse"];
export type BuyerApplicationRef = Schemas["BuyerApplicationRef"];
export type BuyerConsent = Schemas["BuyerConsent"];
export type BuyerConsentList = Schemas["BuyerConsentList"];
export type BuyerConsentAction = Schemas["BuyerConsentActionRequest"]["action"];
export type BuyerDocumentSlot = Schemas["BuyerDocumentSlot"];
export type BuyerApplicationDetail = Schemas["BuyerApplicationDetail"];
export type BuyerParticipant = Schemas["BuyerParticipant"];
export type BuyerFinancialProfile = Schemas["BuyerFinancialProfile"];
export type MetadataItem = Schemas["MetadataItem"];
export type WithdrawalRequest = Schemas["WithdrawalRequest"];

/** Todo lo del portal cuelga de `["buyer"]`: al salir o vencer la sesión se borra de una vez. */
export const buyerKeys = {
  all: ["buyer"] as const,
  session: ["buyer", "session"] as const,
  consents: (id: string) => ["buyer", id, "consents"] as const,
  slots: (id: string) => ["buyer", id, "document-slots"] as const,
  detail: (id: string) => ["buyer", id, "detail"] as const,
  financialProfile: (participantId: string) =>
    ["buyer", "financial-profile", participantId] as const,
  catalog: (code: string, parentCode?: string | null) =>
    ["buyer", "catalog", code, parentCode ?? null] as const,
};

/** Los catálogos casi no cambian: se piden una vez por visita. */
const CATALOG_STALE_TIME = 60 * 60_000;

/** Tamaño de página de los slots: una solicitud tiene unas decenas, se piden de una vez. */
export const SLOTS_PAGE_SIZE = 100;

/** Sesión del comprador: quién es, su solicitud y los consentimientos pendientes. */
export function useBuyerSession(enabled: boolean) {
  return useQuery({
    queryKey: buyerKeys.session,
    queryFn: async () => (await call(api.GET("/api/v1/buyer/session"))).data,
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

/** Cambia el token del enlace por la cookie de sesión. Los errores los pinta `/acceso`. */
export function useConsumeLink() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (token: string) =>
      (await call(api.POST("/api/v1/buyer-access/consume", { body: { token } }))).data,
    onSuccess: () => queryClient.removeQueries({ queryKey: buyerKeys.all }),
  });
}

export function useBuyerLogout() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async () => {
      await call(api.POST("/api/v1/buyer/session/logout"));
    },
  });
}

export function useConsents(applicationId: string) {
  return useQuery({
    queryKey: buyerKeys.consents(applicationId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/buyer/applications/{application_id}/consents", {
            params: { path: { application_id: applicationId } },
          }),
        )
      ).data,
  });
}

/** Acepta o retira un consentimiento. Los errores van al toast global. */
export function useConsentAction(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { consent_definition_id: string; action: BuyerConsentAction }) =>
      (
        await call(
          api.POST("/api/v1/buyer/applications/{application_id}/consents", {
            params: { path: { application_id: applicationId } },
            body,
          }),
        )
      ).data,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: buyerKeys.consents(applicationId) }),
        queryClient.invalidateQueries({ queryKey: buyerKeys.session }),
      ]),
  });
}

/** Slots de documentos de la solicitud (inicio, navegación y documentos). */
export function useBuyerSlots(applicationId: string, enabled = true) {
  return useQuery({
    queryKey: buyerKeys.slots(applicationId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/buyer/applications/{application_id}/document-slots", {
            params: {
              path: { application_id: applicationId },
              query: { page_size: SLOTS_PAGE_SIZE },
            },
          }),
        )
      ).data.items,
    enabled,
  });
}

export interface DetailWithVersion {
  detail: BuyerApplicationDetail;
  /** Versión del `ETag` (API §6); si no llega, la del cuerpo. */
  version: number;
}

/** Detalle de la solicitud para el comprador, con su versión. */
export function useBuyerDetail(applicationId: string) {
  return useQuery({
    queryKey: buyerKeys.detail(applicationId),
    queryFn: async (): Promise<DetailWithVersion> => {
      const { data, version } = await call(
        api.GET("/api/v1/buyer/applications/{application_id}", {
          params: { path: { application_id: applicationId } },
        }),
      );
      return { detail: data, version: version ?? data.version };
    },
  });
}

async function fetchFinancialProfile(participantId: string): Promise<BuyerFinancialProfile | null> {
  try {
    const { data } = await call(
      api.GET("/api/v1/buyer/participants/{participant_id}/financial-profile", {
        params: { path: { participant_id: participantId } },
      }),
    );
    return data;
  } catch (error) {
    // Sin perfil todavía: `404`.
    if (isApiError(error) && error.status === 404) return null;
    throw error;
  }
}

/**
 * Suma del ingreso mensual de los participantes que aportan ingresos. `null` mientras
 * carga o si ninguno tiene perfil.
 */
export function useMonthlyIncome(participants: BuyerParticipant[]): number | null {
  const earners = participants.filter((p) => p.contributes_income);
  const results = useQueries({
    queries: earners.map((p) => ({
      queryKey: buyerKeys.financialProfile(p.id),
      queryFn: () => fetchFinancialProfile(p.id),
    })),
  });
  const profiles = results.map((r) => r.data);
  if (profiles.some((p) => p === undefined)) return null;
  const present = profiles.filter((p): p is BuyerFinancialProfile => !!p);
  return present.length ? present.reduce((sum, p) => sum + p.monthly_income_cop, 0) : null;
}

/** Catálogo del portal (`/buyer/metadata/catalogs/{code}`), solo activos y en su orden. */
export function useBuyerCatalog(code: string, parentCode?: string | null, enabled = true) {
  const query = useQuery({
    queryKey: buyerKeys.catalog(code, parentCode),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/buyer/metadata/catalogs/{catalog_code}", {
            params: {
              path: { catalog_code: code },
              query: parentCode ? { parent_code: parentCode } : {},
            },
          }),
        )
      ).data.items,
    staleTime: CATALOG_STALE_TIME,
    enabled,
  });
  const items = useMemo(
    () => (query.data ?? []).filter((i) => i.active).sort((a, b) => a.order - b.order),
    [query.data],
  );
  return { items, isPending: query.isPending && enabled, isError: query.isError };
}

/** Desistimiento del comprador. El formulario maneja sus errores. */
export function useBuyerWithdraw(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: WithdrawalRequest) =>
      (
        await call(
          api.POST("/api/v1/buyer/applications/{application_id}/withdrawals", {
            params: { path: { application_id: applicationId } },
            body,
          }),
        )
      ).data,
    // La solicitud queda cerrada: se recarga todo lo del portal (y la franja de solo lectura).
    onSettled: () => queryClient.invalidateQueries({ queryKey: buyerKeys.all }),
  });
}
