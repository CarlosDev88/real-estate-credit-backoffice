"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  buyerKeys,
  fetchFinancialProfile,
  type BuyerFinancialProfile,
} from "@/features/buyer-portal/queries";
import { api, call } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { ifMatch } from "@/lib/api/version";

type Schemas = components["schemas"];
export type BuyerProfile = Schemas["BuyerProfile"];
export type BuyerProfileUpdate = Schemas["PatchedBuyerProfileUpdateRequest"];
export type BuyerAddressInput = Schemas["BuyerAddressInputRequest"];
export type BuyerParticipantSummary = Schemas["BuyerParticipantSummary"];
export type FinancialProfileInput = Schemas["BuyerFinancialProfileInputRequest"];
export type BuyerIncomeSource = Schemas["BuyerIncomeSource"];
export type IncomeSourceCreate = Schemas["BuyerIncomeSourceCreateRequest"];
export type IncomeSourceUpdate = Schemas["PatchedBuyerIncomeSourceUpdateRequest"];
export type BuyerProperty = Schemas["BuyerProperty"];
export type PropertyInput = Schemas["BuyerPropertyInputRequest"];
export type BuyerFinancing = Schemas["BuyerFinancing"];
export type FinancingInput = Schemas["FinancingInputRequest"];
export type EligibleProduct = Schemas["BuyerEligibleBankProduct"];

/** Dirección tal como la devuelve `GET /profile` (el contrato no la tipa). */
export interface BuyerAddress {
  id: string;
  address_type: { code: string; label: string } | null;
  city: { code: string; label: string } | null;
  line1: string;
  line2: string;
  postal_code: string;
  is_primary: boolean;
}

export const formKeys = {
  version: (id: string) => ["buyer", id, "version"] as const,
  profile: (id: string) => ["buyer", id, "profile"] as const,
  participants: (id: string) => ["buyer", id, "participants"] as const,
  incomeSources: (id: string, profileId: string) =>
    ["buyer", id, "income-sources", profileId] as const,
  property: (id: string) => ["buyer", id, "property"] as const,
  financing: (id: string) => ["buyer", id, "financing"] as const,
  products: (id: string) => ["buyer", id, "eligible-products"] as const,
};

// ---------- versión de la solicitud ----------

/**
 * Toda escritura del comprador sube la versión de la solicitud (API §6). Se guarda la
 * mayor que llegó en un `ETag`, así dos formularios de la misma página no chocan entre sí;
 * un cambio de otra persona sigue llegando como `409 STALE_VERSION`.
 */
export function rememberVersion(client: QueryClient, id: string, version: number | null) {
  if (version === null) return;
  // Sin observadores, Query la borraría a los 5 minutos: se guarda mientras dure la sesión.
  client.setQueryDefaults(formKeys.version(id), { gcTime: Infinity });
  const current = client.getQueryData<number>(formKeys.version(id));
  if (current === undefined || version > current) {
    client.setQueryData(formKeys.version(id), version);
  }
}

/**
 * `If-Match` con la última versión vista de la solicitud. Si todavía no llegó ninguna
 * (por ejemplo, el inmueble no existe y su `GET` respondió `404`), se toma del detalle.
 */
export async function currentIfMatch(client: QueryClient, id: string): Promise<string> {
  let version = client.getQueryData<number>(formKeys.version(id));
  if (version === undefined) {
    const { data, version: etag } = await call(
      api.GET("/api/v1/buyer/applications/{application_id}", {
        params: { path: { application_id: id } },
      }),
    );
    version = etag ?? data.version;
    rememberVersion(client, id, version);
  }
  return ifMatch(version);
}

/** Después de escribir: la versión nueva y todo lo de la solicitud se vuelve a pedir. */
async function afterWrite(client: QueryClient, id: string, version: number | null) {
  rememberVersion(client, id, version);
  await client.invalidateQueries({
    queryKey: buyerKeys.all,
    predicate: (query) => query.queryKey[1] === id && query.queryKey[2] !== "version",
  });
}

/** `null` si el recurso todavía no existe (`404`). */
async function orNull<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (isApiError(error) && error.status === 404) return null;
    throw error;
  }
}

// ---------- datos personales ----------

export function useBuyerProfile(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.profile(id),
    queryFn: async () => {
      const { data, version } = await call(
        api.GET("/api/v1/buyer/applications/{application_id}/profile", {
          params: { path: { application_id: id } },
        }),
      );
      rememberVersion(client, id, version);
      return data;
    },
  });
}

export function useSaveProfile(id: string) {
  const client = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BuyerProfileUpdate) => {
      const { data, version } = await call(
        api.PATCH("/api/v1/buyer/applications/{application_id}/profile", {
          params: {
            path: { application_id: id },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
}

// ---------- participantes, perfil financiero e ingresos ----------

export function useBuyerParticipants(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.participants(id),
    queryFn: async () => {
      const { data, version } = await call(
        api.GET("/api/v1/buyer/applications/{application_id}/participants", {
          params: { path: { application_id: id }, query: { page_size: 100 } },
        }),
      );
      rememberVersion(client, id, version);
      return data.items;
    },
  });
}

/** Perfil financiero de un participante; `data: null` si todavía no tiene. */
export function useFinancialProfile(id: string, participantId: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: buyerKeys.financialProfile(id, participantId),
    queryFn: async () => {
      const result = await fetchFinancialProfile(participantId);
      rememberVersion(client, id, result?.version ?? null);
      return result;
    },
    select: (result): BuyerFinancialProfile | null => result?.data ?? null,
  });
}

export function useSaveFinancialProfile(id: string, participantId: string) {
  const client = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: FinancialProfileInput) => {
      const { data, version } = await call(
        api.PUT("/api/v1/buyer/participants/{participant_id}/financial-profile", {
          params: {
            path: { participant_id: participantId },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
}

export function useConfirmFinancialProfile(id: string, participantId: string) {
  const client = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async () => {
      const { data, version } = await call(
        api.POST("/api/v1/buyer/participants/{participant_id}/financial-profile/confirmation", {
          params: {
            path: { participant_id: participantId },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
}

export function useIncomeSources(id: string, profileId: string | null) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.incomeSources(id, profileId ?? ""),
    queryFn: async () => {
      const { data, version } = await call(
        api.GET("/api/v1/buyer/financial-profiles/{profile_id}/income-sources", {
          params: { path: { profile_id: profileId! }, query: { page_size: 100 } },
        }),
      );
      rememberVersion(client, id, version);
      return data.items;
    },
    enabled: !!profileId,
  });
}

/** Crea (sin `If-Match`), edita (`If-Match`) o elimina una fuente de ingreso. */
export function useIncomeSourceActions(id: string, profileId: string) {
  const client = useQueryClient();
  const create = useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: IncomeSourceCreate) => {
      const { data, version } = await call(
        api.POST("/api/v1/buyer/financial-profiles/{profile_id}/income-sources", {
          params: { path: { profile_id: profileId } },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
  const update = useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ sourceId, body }: { sourceId: string; body: IncomeSourceUpdate }) => {
      const { data, version } = await call(
        api.PATCH("/api/v1/buyer/income-sources/{income_source_id}", {
          params: {
            path: { income_source_id: sourceId },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
  const remove = useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (sourceId: string) => {
      const { version } = await call(
        api.DELETE("/api/v1/buyer/income-sources/{income_source_id}", {
          params: { path: { income_source_id: sourceId } },
        }),
      );
      await afterWrite(client, id, version);
    },
  });
  return { create, update, remove };
}

// ---------- inmueble ----------

export function useBuyerProperty(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.property(id),
    queryFn: async () => {
      const result = await orNull(
        call(
          api.GET("/api/v1/buyer/applications/{application_id}/property", {
            params: { path: { application_id: id } },
          }),
        ),
      );
      rememberVersion(client, id, result?.version ?? null);
      return result?.data ?? null;
    },
  });
}

export function useSaveProperty(id: string) {
  const client = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: PropertyInput) => {
      const { data, version } = await call(
        api.PUT("/api/v1/buyer/applications/{application_id}/property", {
          params: {
            path: { application_id: id },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
}

// ---------- financiación ----------

export function useBuyerFinancing(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.financing(id),
    queryFn: async () => {
      const result = await orNull(
        call(
          api.GET("/api/v1/buyer/applications/{application_id}/financing", {
            params: { path: { application_id: id } },
          }),
        ),
      );
      rememberVersion(client, id, result?.version ?? null);
      return result?.data ?? null;
    },
  });
}

export function useEligibleProducts(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: formKeys.products(id),
    queryFn: async () => {
      const { data, version } = await call(
        api.GET("/api/v1/buyer/applications/{application_id}/eligible-bank-products", {
          params: { path: { application_id: id }, query: { page_size: 100 } },
        }),
      );
      rememberVersion(client, id, version);
      return data.items;
    },
  });
}

export function useSaveFinancing(id: string) {
  const client = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: FinancingInput) => {
      const { data, version } = await call(
        api.PUT("/api/v1/buyer/applications/{application_id}/financing", {
          params: {
            path: { application_id: id },
            header: { "If-Match": await currentIfMatch(client, id) },
          },
          body,
        }),
      );
      await afterWrite(client, id, version);
      return data;
    },
  });
}
