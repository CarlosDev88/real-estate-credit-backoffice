"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { applicationKeys } from "@/features/applications/queries";
import { workspaceKeys, type DetailWithVersion } from "@/features/applications/workspace-queries";
import { api, call, type ApiResult } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ifMatch } from "@/lib/api/version";

// Edición del expediente por el asesor (Parte 3 de la F7). Todas las escrituras cambian
// la versión de la solicitud: la del `ETag` de la respuesta queda en la caché del detalle
// al instante (la siguiente escritura usa esa en `If-Match`) y después se refresca todo.

type Schemas = components["schemas"];
export type ParticipantCreateRequest = Schemas["ParticipantCreateRequest"];
export type ParticipantUpdateRequest = Schemas["PatchedParticipantUpdateRequest"];
export type FinancialProfileInput = Schemas["FinancialProfileInputRequest"];
export type IncomeSource = Schemas["IncomeSource"];
export type IncomeSourceCreateRequest = Schemas["IncomeSourceCreateRequest"];
export type IncomeSourceUpdateRequest = Schemas["PatchedIncomeSourceUpdateRequest"];
export type PropertyInput = Schemas["ApplicationPropertyInputRequest"];
export type FinancingInput = Schemas["FinancingInputRequest"];
export type EligibleBankProduct = Schemas["EligibleBankProduct"];

export const dossierKeys = {
  incomeSources: (id: string, profileId: string) =>
    ["application", id, "income-sources", profileId] as const,
  eligible: (id: string) => ["application", id, "eligible-products"] as const,
};

/** Versión vigente (la de la caché, que las escrituras mantienen al día). */
export function useCurrentVersion(id: string, fallback: number) {
  const queryClient = useQueryClient();
  return () =>
    queryClient.getQueryData<DetailWithVersion>(workspaceKeys.detail(id))?.version ?? fallback;
}

/** Tras una escritura: la versión nueva a la caché y el expediente y el listado se refrescan. */
function useWritten(id: string) {
  const queryClient = useQueryClient();
  return async (result: ApiResult<unknown>) => {
    if (result.version !== null) {
      queryClient.setQueryData<DetailWithVersion>(workspaceKeys.detail(id), (old) =>
        old ? { ...old, version: result.version ?? old.version } : old,
      );
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all(id) }),
      queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
    ]);
  };
}

function useDossierMutation<V>(id: string, write: (vars: V) => Promise<ApiResult<unknown>>) {
  const written = useWritten(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: write,
    onSuccess: written,
  });
}

// ---------- participantes ----------

/** Agrega un participante (cliente existente o nuevo); un retirado se reactiva. */
export function useAddParticipant(id: string) {
  return useDossierMutation(id, (body: ParticipantCreateRequest) =>
    call(
      api.POST("/api/v1/applications/{application_id}/participants", {
        params: { path: { application_id: id } },
        body,
      }),
    ),
  );
}

export function useUpdateParticipant(id: string, version: () => number) {
  return useDossierMutation(
    id,
    ({ participantId, body }: { participantId: string; body: ParticipantUpdateRequest }) =>
      call(
        api.PATCH("/api/v1/application-participants/{participant_id}", {
          params: {
            path: { participant_id: participantId },
            header: { "If-Match": ifMatch(version()) },
          },
          body,
        }),
      ),
  );
}

/** Lo retira (`is_active=false`); el titular no se retira. */
export function useRemoveParticipant(id: string) {
  return useDossierMutation(id, (participantId: string) =>
    call(
      api.DELETE("/api/v1/application-participants/{participant_id}", {
        params: { path: { participant_id: participantId } },
      }),
    ),
  );
}

// ---------- perfil financiero e ingresos ----------

/** Reemplazo completo del perfil (`PUT`, `If-Match`); `201` si lo creó. */
export function useSaveFinancialProfile(id: string, version: () => number) {
  return useDossierMutation(
    id,
    ({ participantId, body }: { participantId: string; body: FinancialProfileInput }) =>
      call(
        api.PUT("/api/v1/application-participants/{participant_id}/financial-profile", {
          params: {
            path: { participant_id: participantId },
            header: { "If-Match": ifMatch(version()) },
          },
          body,
        }),
      ),
  );
}

export function useIncomeSources(id: string, profileId: string | null) {
  return useQuery({
    queryKey: dossierKeys.incomeSources(id, profileId ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/financial-profiles/{profile_id}/income-sources", {
            params: { path: { profile_id: profileId ?? "" }, query: { page_size: 100 } },
          }),
        )
      ).data.items,
    enabled: !!profileId,
  });
}

export function useCreateIncomeSource(id: string) {
  return useDossierMutation(
    id,
    ({ profileId, body }: { profileId: string; body: IncomeSourceCreateRequest }) =>
      call(
        api.POST("/api/v1/financial-profiles/{profile_id}/income-sources", {
          params: { path: { profile_id: profileId } },
          body,
        }),
      ),
  );
}

export function useUpdateIncomeSource(id: string, version: () => number) {
  return useDossierMutation(
    id,
    ({ sourceId, body }: { sourceId: string; body: IncomeSourceUpdateRequest }) =>
      call(
        api.PATCH("/api/v1/income-sources/{income_source_id}", {
          params: {
            path: { income_source_id: sourceId },
            header: { "If-Match": ifMatch(version()) },
          },
          body,
        }),
      ),
  );
}

export function useDeleteIncomeSource(id: string) {
  return useDossierMutation(id, (sourceId: string) =>
    call(
      api.DELETE("/api/v1/income-sources/{income_source_id}", {
        params: { path: { income_source_id: sourceId } },
      }),
    ),
  );
}

// ---------- inmueble y financiación ----------

export function useSaveProperty(id: string, version: () => number) {
  return useDossierMutation(id, (body: PropertyInput) =>
    call(
      api.PUT("/api/v1/applications/{application_id}/property", {
        params: { path: { application_id: id }, header: { "If-Match": ifMatch(version()) } },
        body,
      }),
    ),
  );
}

export function useSaveFinancing(id: string, version: () => number) {
  return useDossierMutation(id, (body: FinancingInput) =>
    call(
      api.PUT("/api/v1/applications/{application_id}/financing", {
        params: { path: { application_id: id }, header: { "If-Match": ifMatch(version()) } },
        body,
      }),
    ),
  );
}

/** Productos que admiten la finalidad, con una evaluación no guardada de cada uno. */
export function useEligibleProducts(id: string, enabled: boolean) {
  return useQuery({
    queryKey: dossierKeys.eligible(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/eligible-bank-products", {
            params: { path: { application_id: id }, query: { page_size: 100 } },
          }),
        )
      ).data.items,
    enabled,
  });
}

/** Clientes para agregar como participante (`GET /clients?search=`, de a 20). */
export function useClientOptions(search: string, enabled: boolean) {
  return useQuery({
    queryKey: ["clients", "options", search],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/clients", {
            params: { query: { page_size: 20, ...(search ? { search } : {}) } },
          }),
        )
      ).data.items as Schemas["Client"][],
    placeholderData: keepPreviousData,
    enabled,
  });
}
