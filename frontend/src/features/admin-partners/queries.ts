"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import { partnerOptionKeys } from "@/features/admin-common/partner-select";
import type { PartnerStatusCode, PartnersParams } from "@/features/admin-partners/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Partner = Schemas["Partner"];
export type PartnerDetail = Schemas["PartnerDetail"];
export type PartnerPage = Schemas["PaginatedPartnerList"];
export type PartnerCreateRequest = Schemas["PartnerCreateRequest"];
export type PartnerUpdateRequest = Schemas["PatchedPartnerUpdateRequest"];
export type Membership = Schemas["Membership"];
export type MembershipPage = Schemas["PaginatedMembershipList"];
export type MembershipCreateRequest = Schemas["MembershipCreateRequest"];
export type UserOption = Schemas["User"];

/** `metrics` de `PartnerDetail` (objeto libre en el contrato; forma de `partner_metrics`). */
export interface PartnerMetrics {
  projects_by_status?: Record<string, number>;
  active_members?: number;
}

export const partnerKeys = {
  all: ["admin-partners"] as const,
  lists: ["admin-partners", "list"] as const,
  list: (query: object) => ["admin-partners", "list", query] as const,
  detail: (id: string) => ["admin-partners", "detail", id] as const,
  members: (id: string) => ["admin-partners", "members", id] as const,
  memberPage: (id: string, page: number) => ["admin-partners", "members", id, page] as const,
  memberCandidates: (search: string) => ["admin-partners", "candidates", search] as const,
};

/** `GET /partners` con el estado de la URL. */
export function usePartnersList(params: PartnersParams) {
  const query = {
    search: params.search,
    status: (params.status || undefined) as PartnerStatusCode | undefined,
    city_code: params.city,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: partnerKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/partners", { params: { query: compact(query) } })))
        .data as PartnerPage,
    placeholderData: keepPreviousData,
  });
}

/** `GET /partners/{id}`: datos y métricas del panel. */
export function usePartner(id: string) {
  return useQuery({
    queryKey: partnerKeys.detail(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/partners/{partner_id}", { params: { path: { partner_id: id } } }),
        )
      ).data as PartnerDetail,
    enabled: id !== "",
  });
}

export const MEMBERS_PAGE_SIZE = 10;

/** `GET /partners/{id}/members`: miembros (activos e históricos), los más recientes primero. */
export function useMembers(partnerId: string, page: number, enabled: boolean) {
  return useQuery({
    queryKey: partnerKeys.memberPage(partnerId, page),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/partners/{partner_id}/members", {
            params: {
              path: { partner_id: partnerId },
              query: { page, page_size: MEMBERS_PAGE_SIZE, ordering: "-started_at" },
            },
          }),
        )
      ).data as MembershipPage,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Usuarios de constructora que se pueden agregar (`GET /users?role=…`), con búsqueda. */
export function useMemberCandidates(role: string, search: string, enabled: boolean) {
  return useQuery({
    queryKey: partnerKeys.memberCandidates(search),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/users", {
            params: {
              query: compact({ role, search, status: "ACTIVE" as const, page_size: 50 }),
            },
          }),
        )
      ).data.items as UserOption[],
    placeholderData: keepPreviousData,
    enabled,
  });
}

function useRefreshPartners() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: partnerKeys.lists }),
      // Los selectores de constructora (usuarios, proyectos) también cambian.
      queryClient.invalidateQueries({ queryKey: partnerOptionKeys.all }),
    ]);
}

/** `POST /partners`. El formulario maneja sus errores. */
export function useCreatePartner() {
  const refresh = useRefreshPartners();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: PartnerCreateRequest) =>
      (await call(api.POST("/api/v1/partners", { body }))).data as Partner,
    onSuccess: refresh,
  });
}

/** `PATCH /partners/{id}` con los campos cambiados (el NIT no se edita). */
export function useUpdatePartner(id: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshPartners();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: PartnerUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/partners/{partner_id}", {
            params: { path: { partner_id: id } },
            body,
          }),
        )
      ).data as PartnerDetail,
    onSuccess: (partner) => {
      queryClient.setQueryData(partnerKeys.detail(id), partner);
      return refresh();
    },
  });
}

/** `POST /partners/{id}/activate` o `/deactivate` (motivo obligatorio al desactivar). */
export function useSetPartnerActive(id: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshPartners();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ active, reason }: { active: boolean; reason: string }) => {
      const path = { params: { path: { partner_id: id } } };
      return active
        ? (
            await call(
              api.POST("/api/v1/partners/{partner_id}/activate", {
                ...path,
                body: reason ? { reason } : {},
              }),
            )
          ).data
        : (
            await call(
              api.POST("/api/v1/partners/{partner_id}/deactivate", { ...path, body: { reason } }),
            )
          ).data;
    },
    onSuccess: async () => {
      // La respuesta no trae las métricas: se vuelve a pedir el detalle.
      await queryClient.invalidateQueries({ queryKey: partnerKeys.detail(id) });
      return refresh();
    },
  });
}

/**
 * `POST /partners/{id}/members`: con `user_id` agrega la membresía (`201`); con `email`
 * crea una invitación de constructora (`202`) y la membresía nace al aceptarla.
 */
export function useAddMember(partnerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: MembershipCreateRequest) => {
      const result = await call(
        api.POST("/api/v1/partners/{partner_id}/members", {
          params: { path: { partner_id: partnerId } },
          body,
        }),
      );
      return { invited: result.response.status === 202 };
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: partnerKeys.members(partnerId) }),
        queryClient.invalidateQueries({ queryKey: partnerKeys.detail(partnerId) }),
        // La invitación aparece en `/admin/usuarios`.
        queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
      ]),
  });
}
