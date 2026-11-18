"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact, ALL, type TaskParams, type TrayParams } from "@/features/workday/workday-params";
import { api, call } from "@/lib/api/client";
import type { components, operations } from "@/lib/api/schema";

export type WorkdaySummary = components["schemas"]["WorkdaySummary"];
export type WorkdaySegment = components["schemas"]["WorkdaySegment"];
export type WorkdayApplication = components["schemas"]["WorkdayApplication"];
export type Task = components["schemas"]["Task"];
export type TaskCreateRequest = components["schemas"]["TaskCreateRequest"];
export type TaskUpdateRequest = components["schemas"]["PatchedTaskUpdateRequest"];

type TrayQuery = NonNullable<operations["workday_applications_list"]["parameters"]["query"]>;
type SummaryQuery = NonNullable<operations["workday_summary"]["parameters"]["query"]>;
type TasksQuery = NonNullable<operations["tasks_list"]["parameters"]["query"]>;

/**
 * Estados no terminales que acepta `stage` (enum `stage` de `GET /workday/applications`).
 * Son códigos: los textos salen del catálogo `application_status`.
 */
export const WORKDAY_STAGES = [
  "DRAFT",
  "WAITING_BUYER_DATA",
  "WAITING_DOCUMENTS",
  "DOCUMENTS_REVIEW",
  "READY_TO_FILE",
  "FILED",
  "FILING_VALIDATION",
  "CREDIT_ANALYSIS",
  "APPROVED",
  "LEGALIZATION",
  "BANK_OBSERVATION",
] as const satisfies readonly NonNullable<TrayQuery["stage"]>[];

/** Prioridad que la API pone por omisión al crear (`TaskCreateRequest.priority_code`). */
export const DEFAULT_PRIORITY = "MEDIUM";

export const workdayKeys = {
  all: ["workday"] as const,
  summary: (filters: ReturnType<typeof summaryFilters>) => ["workday", "summary", filters] as const,
  tray: (params: TrayParams) => ["workday", "applications", params] as const,
  options: (search: string) => ["workday", "application-options", search] as const,
};

export const taskKeys = {
  all: ["tasks"] as const,
  list: (query: TasksQuery) => ["tasks", "list", query] as const,
};

/**
 * Filtros de la bandeja que también recibe el resumen: no el segmento, el orden ni la
 * página, y tampoco la búsqueda (`GET /workday/summary` no la acepta).
 */
export function summaryFilters(params: TrayParams) {
  return {
    stage: params.stage,
    bank_id: params.bank_id,
    purpose: params.purpose,
    advisor_id: params.advisor_id,
  };
}

/** `GET /workday/summary`: total y conteo por segmento, con los filtros de la bandeja. */
export function useWorkdaySummary(params: TrayParams) {
  const filters = summaryFilters(params);
  return useQuery({
    queryKey: workdayKeys.summary(filters),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/workday/summary", {
            params: { query: compact(filters) as SummaryQuery },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

/** `GET /workday/applications` con el estado de la URL. */
export function useWorkdayApplications(params: TrayParams) {
  return useQuery({
    queryKey: workdayKeys.tray(params),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/workday/applications", {
            params: { query: compact(params) as TrayQuery },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

/** Solicitudes para vincular una tarea nueva (búsqueda por código, nombre o documento). */
export function useApplicationOptions(search: string, enabled: boolean) {
  return useQuery({
    queryKey: workdayKeys.options(search),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/workday/applications", {
            params: { query: compact({ search, page_size: 20 }) },
          }),
        )
      ).data.items,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/**
 * Consulta de `GET /tasks` a partir de la URL. `assigned_to_id` vacío es el usuario actual;
 * `all` no filtra por responsable (el administrador ve todas).
 */
export function tasksQuery(params: TaskParams, meId: string): TasksQuery {
  const assigned = params.assigned_to_id || meId;
  return compact({
    assigned_to_id: assigned === ALL ? "" : assigned,
    due: params.due as TasksQuery["due"] | "",
    status: params.task_status === ALL ? "" : (params.task_status as TasksQuery["status"]),
    priority: params.priority,
    page: params.task_page,
    page_size: params.task_page_size,
  }) as TasksQuery;
}

export function useTasks(query: TasksQuery, enabled: boolean) {
  return useQuery({
    queryKey: taskKeys.list(query),
    queryFn: async () => (await call(api.GET("/api/v1/tasks", { params: { query } }))).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Pendientes del usuario: el número de la pestaña "Mis tareas". */
export function usePendingTasksCount(meId: string | undefined) {
  const query: TasksQuery = { assigned_to_id: meId, status: "PENDING", page_size: 1 };
  return useQuery({
    queryKey: taskKeys.list(query),
    queryFn: async () => (await call(api.GET("/api/v1/tasks", { params: { query } }))).data,
    enabled: !!meId,
    select: (data) => data.total,
  });
}

// ---------- escrituras ----------

/** Una tarea cambia: se refrescan las tareas, la bandeja (tareas pendientes) y el dashboard. */
function useInvalidateTasks() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: workdayKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
}

export function useCreateTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: TaskCreateRequest) =>
      (await call(api.POST("/api/v1/tasks", { body }))).data,
    onSuccess: () => invalidate(),
  });
}

export function useUpdateTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, body }: { id: string; body: TaskUpdateRequest }) =>
      (
        await call(
          api.PATCH("/api/v1/tasks/{task_id}", { params: { path: { task_id: id } }, body }),
        )
      ).data,
    onSuccess: () => invalidate(),
  });
}

export function useCompleteTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async (id: string) =>
      (
        await call(
          api.POST("/api/v1/tasks/{task_id}/complete", { params: { path: { task_id: id } } }),
        )
      ).data,
    // Con `409 TASK_NOT_PENDING`, la lista también está vieja: se refresca igual.
    onSettled: () => invalidate(),
  });
}

export function useCancelTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, reason }: { id: string; reason: string }) =>
      (
        await call(
          api.POST("/api/v1/tasks/{task_id}/cancel", {
            params: { path: { task_id: id } },
            body: { reason },
          }),
        )
      ).data,
    onSettled: () => invalidate(),
  });
}
