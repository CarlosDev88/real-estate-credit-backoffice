"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import type { ProjectEndpoint } from "@/features/admin-projects/actions";
import type { ProjectStatusCode, ProjectsParams } from "@/features/admin-projects/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Project = Schemas["Project"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type ProjectPage = Schemas["PaginatedProjectList"];
export type ProjectCreateRequest = Schemas["ProjectCreateRequest"];
export type ProjectUpdateRequest = Schemas["PatchedProjectUpdateRequest"];

export const projectKeys = {
  all: ["admin-projects"] as const,
  lists: ["admin-projects", "list"] as const,
  list: (query: object) => ["admin-projects", "list", query] as const,
  detail: (id: string) => ["admin-projects", "detail", id] as const,
};

/** `GET /projects` con el estado de la URL. La constructora solo recibe los suyos (API). */
export function useProjectsList(params: ProjectsParams) {
  const query = {
    search: params.search,
    status: (params.status || undefined) as ProjectStatusCode | undefined,
    partner_id: params.partner,
    city_code: params.city,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: projectKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/projects", { params: { query: compact(query) } })))
        .data as ProjectPage,
    placeholderData: keepPreviousData,
  });
}

/** `GET /projects/{id}`: el detalle trae `available_actions` para el usuario actual. */
export function useProject(id: string) {
  return useQuery({
    queryKey: projectKeys.detail(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } }),
        )
      ).data as ProjectDetail,
    enabled: id !== "",
  });
}

function useSaveProject() {
  const queryClient = useQueryClient();
  return (project: ProjectDetail) => {
    queryClient.setQueryData(projectKeys.detail(project.id), project);
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: projectKeys.lists }),
      // Las métricas de la constructora cuentan proyectos por estado.
      queryClient.invalidateQueries({ queryKey: ["admin-partners", "detail"] }),
    ]);
  };
}

/** `POST /projects`. El formulario maneja sus errores. */
export function useCreateProject() {
  const save = useSaveProject();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: ProjectCreateRequest) =>
      (await call(api.POST("/api/v1/projects", { body }))).data as ProjectDetail,
    onSuccess: save,
  });
}

/** `PATCH /projects/{id}` con los campos cambiados. */
export function useUpdateProject(id: string) {
  const save = useSaveProject();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: ProjectUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/projects/{project_id}", {
            params: { path: { project_id: id } },
            body,
          }),
        )
      ).data as ProjectDetail,
    onSuccess: save,
  });
}

/**
 * `POST /projects/{id}/submit|activate|reject|archive`. `reject` y `archive` exigen motivo
 * (`ReasonRequest`); `submit` y `activate` lo dejan opcional.
 */
export function useProjectTransition(id: string) {
  const save = useSaveProject();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ endpoint, reason }: { endpoint: ProjectEndpoint; reason: string }) => {
      const params = { path: { project_id: id } };
      const optional = reason ? { reason } : {};
      switch (endpoint) {
        case "submit":
          return (
            await call(api.POST("/api/v1/projects/{project_id}/submit", { params, body: optional }))
          ).data as ProjectDetail;
        case "activate":
          return (
            await call(
              api.POST("/api/v1/projects/{project_id}/activate", { params, body: optional }),
            )
          ).data as ProjectDetail;
        case "reject":
          return (
            await call(
              api.POST("/api/v1/projects/{project_id}/reject", { params, body: { reason } }),
            )
          ).data as ProjectDetail;
        case "archive":
          return (
            await call(
              api.POST("/api/v1/projects/{project_id}/archive", { params, body: { reason } }),
            )
          ).data as ProjectDetail;
      }
    },
    onSuccess: save,
  });
}
