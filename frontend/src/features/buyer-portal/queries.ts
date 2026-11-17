"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type BuyerSession = Schemas["BuyerSessionResponse"];
export type BuyerApplicationRef = Schemas["BuyerApplicationRef"];
export type BuyerConsent = Schemas["BuyerConsent"];
export type BuyerConsentList = Schemas["BuyerConsentList"];
export type BuyerConsentAction = Schemas["BuyerConsentActionRequest"]["action"];
export type BuyerDocumentSlot = Schemas["BuyerDocumentSlot"];

/** Todo lo del portal cuelga de `["buyer"]`: al salir o vencer la sesión se borra de una vez. */
export const buyerKeys = {
  all: ["buyer"] as const,
  session: ["buyer", "session"] as const,
  consents: (id: string) => ["buyer", id, "consents"] as const,
  slots: (id: string) => ["buyer", id, "document-slots"] as const,
};

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
