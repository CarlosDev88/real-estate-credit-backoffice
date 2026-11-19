"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Transition = Schemas["WorkflowTransition"];
export type TransitionPage = Schemas["PaginatedWorkflowTransitionList"];
export type TransitionUpdateRequest = Schemas["PatchedWorkflowTransitionUpdateRequest"];
export type FlowType = Schemas["FlowTypeEnum"];

/**
 * Flujos del contrato (`FlowTypeEnum`). La API no manda su etiqueta: el texto copia el
 * `TextChoices` del backend (brecha anotada), y los estados salen del catálogo de cada flujo.
 */
export const FLOWS: readonly { code: FlowType; label: string; statusCatalog: string }[] = [
  { code: "APPLICATION", label: "Solicitudes de crédito", statusCatalog: "application_status" },
  { code: "OPPORTUNITY", label: "Oportunidades", statusCatalog: "opportunity_status" },
  { code: "PROJECT", label: "Proyectos", statusCatalog: "project_status" },
];

export const workflowKeys = {
  all: ["admin-workflow"] as const,
  list: (query: object) => ["admin-workflow", "list", query] as const,
};

export type TransitionsParams = {
  flujo: FlowType;
  search: string;
  /** "true"/"false" (`is_active`). */
  active: string;
  ordering: string;
  page: number;
  page_size: number;
  abierta: string;
};

export function useTransitions(params: TransitionsParams) {
  const query = {
    flow_type: params.flujo,
    search: params.search,
    is_active: params.active === "" ? undefined : params.active === "true",
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: workflowKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/workflow-transitions", { params: { query: compact(query) } })))
        .data as TransitionPage,
    placeholderData: keepPreviousData,
  });
}

function useRefresh() {
  const queryClient = useQueryClient();
  // Cambian las acciones disponibles de solicitudes, oportunidades y proyectos.
  return () => queryClient.invalidateQueries();
}

/** `PATCH /workflow-transitions/{id}`: solo una transición inactiva se edita. */
export function useUpdateTransition(id: string) {
  const refresh = useRefresh();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: TransitionUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/workflow-transitions/{transition_id}", {
            params: { path: { transition_id: id } },
            body,
          }),
        )
      ).data as Transition,
    onSuccess: refresh,
  });
}

export function useSetTransitionActive() {
  const refresh = useRefresh();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      const options = { params: { path: { transition_id: id } } };
      return (
        active
          ? (await call(api.POST("/api/v1/workflow-transitions/{transition_id}/activate", options)))
              .data
          : (
              await call(
                api.POST("/api/v1/workflow-transitions/{transition_id}/deactivate", options),
              )
            ).data
      ) as Transition;
    },
    onSuccess: refresh,
  });
}
