"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { applicationKeys } from "@/features/applications/queries";
import { api, call } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type ApplicationDetail = Schemas["ApplicationDetail"];
export type AvailableAction = Schemas["AvailableAction"];
export type Completeness = Schemas["Completeness"];
export type Participant = Schemas["ApplicationParticipant"];
export type FinancialProfile = Schemas["FinancialProfile"];
export type Property = Schemas["Property"];
export type Financing = Schemas["Financing"];
export type BankRuleEvaluation = Schemas["BankRuleEvaluation"];
export type BuyerAccessLink = Schemas["BuyerAccessLink"];
export type BuyerAccessLinkCreated = Schemas["BuyerAccessLinkCreated"];
export type ConsentRecord = Schemas["ConsentRecord"];
export type StatusHistoryEntry = Schemas["StatusHistory"];
export type DocumentSlot = Schemas["DocumentSlot"];
export type InternalUser = Schemas["User"];
export type StatusTransitionRequest = Schemas["StatusTransitionRequest"];
export type WithdrawalRequest = Schemas["WithdrawalRequest"];
export type AssignmentCreateRequest = Schemas["AssignmentCreateRequest"];
export type BuyerAccessLinkCreateRequest = Schemas["BuyerAccessLinkCreateRequest"];

/** Todo lo del expediente cuelga de `["application", id]`: se invalida de una vez. */
export const workspaceKeys = {
  all: (id: string) => ["application", id] as const,
  detail: (id: string) => ["application", id, "detail"] as const,
  completeness: (id: string) => ["application", id, "completeness"] as const,
  participants: (id: string) => ["application", id, "participants"] as const,
  profile: (id: string, participantId: string) =>
    ["application", id, "financial-profile", participantId] as const,
  property: (id: string) => ["application", id, "property"] as const,
  financing: (id: string) => ["application", id, "financing"] as const,
  evaluation: (id: string) => ["application", id, "evaluation"] as const,
  buyerLinks: (id: string) => ["application", id, "buyer-links"] as const,
  consents: (id: string) => ["application", id, "consents"] as const,
  history: (id: string, page: number) => ["application", id, "history", page] as const,
  toReview: (id: string) => ["application", id, "to-review"] as const,
};

/** Un recurso opcional que todavía no existe (`404`) es `null`, no un error. */
async function nullOn404<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (isApiError(error) && error.status === 404) return null;
    throw error;
  }
}

export interface DetailWithVersion {
  detail: ApplicationDetail;
  /** Versión del `ETag` (API §6); si no llega, la del cuerpo. */
  version: number;
}

/** Expediente con su versión. Un `404` (inexistente o fuera del alcance) es error. */
export function useApplicationDetail(id: string) {
  return useQuery({
    queryKey: workspaceKeys.detail(id),
    queryFn: async (): Promise<DetailWithVersion> => {
      const { data, version } = await call(
        api.GET("/api/v1/applications/{application_id}", {
          params: { path: { application_id: id } },
        }),
      );
      return { detail: data, version: version ?? data.version };
    },
  });
}

export function useCompleteness(id: string) {
  return useQuery({
    queryKey: workspaceKeys.completeness(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/completeness", {
            params: { path: { application_id: id } },
          }),
        )
      ).data,
  });
}

/** Participantes vigentes y el perfil financiero de cada uno (si lo tiene). */
export function useParticipants(id: string) {
  const participants = useQuery({
    queryKey: workspaceKeys.participants(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/participants", {
            params: { path: { application_id: id }, query: { page_size: 100 } },
          }),
        )
      ).data.items,
  });
  const withProfile = (participants.data ?? []).filter((p) => p.financial_profile_id);
  const profiles = useQueries({
    queries: withProfile.map((p) => ({
      queryKey: workspaceKeys.profile(id, p.id),
      queryFn: () =>
        nullOn404(
          call(
            api.GET("/api/v1/application-participants/{participant_id}/financial-profile", {
              params: { path: { participant_id: p.id } },
            }),
          ).then((r) => r.data),
        ),
    })),
  });
  const byParticipant = new Map<string, FinancialProfile>();
  withProfile.forEach((p, i) => {
    const profile = profiles[i]?.data;
    if (profile) byParticipant.set(p.id, profile);
  });
  return {
    participants: participants.data,
    profiles: byParticipant,
    isPending: participants.isPending || profiles.some((q) => q.isPending),
    isError: participants.isError || profiles.some((q) => q.isError),
    refetch: () => void participants.refetch(),
  };
}

export function useProperty(id: string) {
  return useQuery({
    queryKey: workspaceKeys.property(id),
    queryFn: () =>
      nullOn404(
        call(
          api.GET("/api/v1/applications/{application_id}/property", {
            params: { path: { application_id: id } },
          }),
        ).then((r) => r.data),
      ),
  });
}

export function useFinancing(id: string) {
  return useQuery({
    queryKey: workspaceKeys.financing(id),
    queryFn: () =>
      nullOn404(
        call(
          api.GET("/api/v1/applications/{application_id}/financing", {
            params: { path: { application_id: id } },
          }),
        ).then((r) => r.data),
      ),
  });
}

/** Última evaluación de las reglas del banco; `null` si nunca se evaluó. */
export function useLatestEvaluation(id: string) {
  return useQuery({
    queryKey: workspaceKeys.evaluation(id),
    queryFn: () =>
      nullOn404(
        call(
          api.GET("/api/v1/applications/{application_id}/bank-rule-evaluations/latest", {
            params: { path: { application_id: id } },
          }),
        ).then((r) => r.data),
      ),
  });
}

/** El enlace más reciente del comprador (la API los da del más reciente al más antiguo). */
export function useLatestBuyerLink(id: string, enabled: boolean) {
  return useQuery({
    queryKey: workspaceKeys.buyerLinks(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/buyer-access-links", {
            params: { path: { application_id: id }, query: { page_size: 1 } },
          }),
        )
      ).data.items[0] ?? null,
    enabled,
  });
}

export function useConsents(id: string, enabled: boolean) {
  return useQuery({
    queryKey: workspaceKeys.consents(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/consents", {
            params: { path: { application_id: id }, query: { page_size: 100 } },
          }),
        )
      ).data.items,
    enabled,
  });
}

export const HISTORY_PAGE_SIZE = 20;

export function useStatusHistory(id: string, page: number, enabled = true) {
  return useQuery({
    queryKey: workspaceKeys.history(id, page),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/status-history", {
            params: {
              path: { application_id: id },
              query: { page, page_size: HISTORY_PAGE_SIZE },
            },
          }),
        )
      ).data,
    enabled,
  });
}

/** Slots cargados y pendientes de decisión (`status=UPLOADED`): los 3 primeros y el total. */
export function useSlotsToReview(id: string) {
  return useQuery({
    queryKey: workspaceKeys.toReview(id),
    queryFn: async () => {
      const { data } = await call(
        api.GET("/api/v1/applications/{application_id}/document-slots", {
          params: { path: { application_id: id }, query: { status: "UPLOADED", page_size: 3 } },
        }),
      );
      return { slots: data.items, total: data.total };
    },
  });
}

/** Asesores activos para reasignar (exige `users.read`). */
export function useAdvisors(enabled: boolean) {
  return useQuery({
    queryKey: ["users", "advisors"],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/users", {
            params: {
              query: { role: "ADVISOR", status: "ACTIVE", ordering: "first_name", page_size: 100 },
            },
          }),
        )
      ).data.items,
    enabled,
    staleTime: 5 * 60_000,
  });
}

// ---------- escrituras ----------

function useInvalidateApplication(id: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all(id) }),
      queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
    ]);
}

/** Transición de estado con `expected_version`. Al terminar, se refresca todo el expediente. */
export function useTransition(id: string) {
  const invalidate = useInvalidateApplication(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: StatusTransitionRequest) =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/status-transitions", {
            params: { path: { application_id: id } },
            body,
          }),
        )
      ).data,
    onSuccess: invalidate,
  });
}

export function useWithdraw(id: string) {
  const invalidate = useInvalidateApplication(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: WithdrawalRequest) =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/withdrawals", {
            params: { path: { application_id: id } },
            body,
          }),
        )
      ).data,
    onSuccess: invalidate,
  });
}

/** Reasignación. `lostAccess`: el `204` dice que quien reasignó ya no ve la solicitud. */
export function useAssign(id: string) {
  const invalidate = useInvalidateApplication(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: AssignmentCreateRequest) => {
      const { response } = await call(
        api.POST("/api/v1/applications/{application_id}/assignments", {
          params: { path: { application_id: id } },
          body,
        }),
      );
      return { lostAccess: response.status === 204 };
    },
    onSuccess: async ({ lostAccess }) => {
      if (!lostAccess) await invalidate();
    },
  });
}

export function useCreateBuyerLink(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BuyerAccessLinkCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/buyer-access-links", {
            params: { path: { application_id: id } },
            body,
          }),
        )
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: workspaceKeys.buyerLinks(id) }),
  });
}

/** Evalúa las reglas del banco; no cambia la versión. Refresca la evaluación y la completitud. */
export function useEvaluateRules(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/bank-rule-evaluations", {
            params: { path: { application_id: id } },
          }),
        )
      ).data,
    onSuccess: async (evaluation) => {
      queryClient.setQueryData(workspaceKeys.evaluation(id), evaluation);
      await queryClient.invalidateQueries({ queryKey: workspaceKeys.completeness(id) });
    },
  });
}
