"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import type { AdminUsersParams } from "@/features/admin-users/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type User = Schemas["User"];
export type UserPage = Schemas["PaginatedUserList"];
export type UserUpdateRequest = Schemas["PatchedUserUpdateRequest"];
export type UserRolesRequest = Schemas["UserRolesRequest"];
export type Role = Schemas["Role"];
export type Invitation = Schemas["Invitation"];
export type InvitationPage = Schemas["PaginatedInvitationList"];
export type InvitationCreateRequest = Schemas["InvitationCreateRequest"];
export type InvitationAcceptRequest = Schemas["InvitationAcceptRequest"];
export type AcceptedUser = Schemas["AcceptedUser"];

/** Lo que la API devuelve en `partner` e `invited_by`: `{ id, name }`. */
export interface NamedRef {
  id?: string;
  name?: string;
}

export function refName(ref: { [key: string]: string } | null | undefined): string | null {
  return (ref as NamedRef | null | undefined)?.name || null;
}

export const adminUserKeys = {
  all: ["admin-users"] as const,
  lists: ["admin-users", "list"] as const,
  list: (query: object) => ["admin-users", "list", query] as const,
  detail: (id: string) => ["admin-users", "detail", id] as const,
  roles: ["admin-users", "roles"] as const,
  invitations: ["admin-users", "invitations"] as const,
  invitationList: (query: object) => ["admin-users", "invitations", query] as const,
};

/** Límite de `page_size` de la API: los roles caben en una sola página. */
const MAX_PAGE_SIZE = 100;

/** `GET /users` con el estado de la URL. Mientras llega otra página, se ve la anterior. */
export function useUsersList(params: AdminUsersParams, enabled = true) {
  const query = {
    search: params.search,
    role: params.role,
    // Validado contra `USER_STATUSES` al leer la URL.
    status: (params.status || undefined) as "ACTIVE" | "INACTIVE" | "PENDING" | undefined,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: adminUserKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/users", { params: { query: compact(query) } })))
        .data as UserPage,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** `GET /users/{id}`: el usuario del panel lateral. */
export function useUser(id: string) {
  return useQuery({
    queryKey: adminUserKeys.detail(id),
    queryFn: async () =>
      (await call(api.GET("/api/v1/users/{user_id}", { params: { path: { user_id: id } } })))
        .data as User,
    enabled: id !== "",
  });
}

/** `GET /roles`: nombres de los roles (filtro, tabla y formularios). Cambian poco. */
export function useRoles(enabled = true) {
  return useQuery({
    queryKey: adminUserKeys.roles,
    queryFn: async () =>
      (await call(api.GET("/api/v1/roles", { params: { query: { page_size: MAX_PAGE_SIZE } } })))
        .data.items as Role[],
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Nombre del rol por su código; mientras llegan los roles (o si no existe), el código. */
export function roleName(roles: readonly Role[] | undefined, code: string): string {
  return roles?.find((role) => role.code === code)?.name ?? code;
}

function useSaveUser(id: string) {
  const queryClient = useQueryClient();
  return (user: User) => {
    queryClient.setQueryData(adminUserKeys.detail(id), user);
    return queryClient.invalidateQueries({ queryKey: adminUserKeys.lists });
  };
}

/** `PATCH /users/{id}`: nombre y teléfono. El formulario maneja sus errores. */
export function useUpdateUser(id: string) {
  const save = useSaveUser(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: UserUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body }),
        )
      ).data as User,
    onSuccess: save,
  });
}

/** `PUT /users/{id}/roles`: reemplaza los roles (y la constructora, si aplica). */
export function useReplaceRoles(id: string) {
  const save = useSaveUser(id);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: UserRolesRequest) =>
      (
        await call(
          api.PUT("/api/v1/users/{user_id}/roles", { params: { path: { user_id: id } }, body }),
        )
      ).data as User,
    onSuccess: save,
  });
}

/** `POST /users/{id}/activate` o `/deactivate`, con el motivo (obligatorio al desactivar). */
export function useSetUserActive(id: string) {
  const save = useSaveUser(id);
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ active, reason }: { active: boolean; reason: string }) => {
      const path = { params: { path: { user_id: id } } };
      const result = active
        ? await call(
            api.POST("/api/v1/users/{user_id}/activate", {
              ...path,
              body: reason ? { reason } : {},
            }),
          )
        : await call(api.POST("/api/v1/users/{user_id}/deactivate", { ...path, body: { reason } }));
      return result.data as User;
    },
    onSuccess: async (user) => {
      await save(user);
      // Desactivar revoca sus invitaciones pendientes.
      return queryClient.invalidateQueries({ queryKey: adminUserKeys.invitations });
    },
  });
}

/** `GET /invitations` con el estado de la URL. */
export function useInvitationsList(params: AdminUsersParams, enabled = true) {
  const query = {
    role: params.role,
    status: params.status,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: adminUserKeys.invitationList(query),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/invitations", {
            params: {
              query: compact({
                ...query,
                status: (query.status || undefined) as
                  "ACCEPTED" | "EXPIRED" | "PENDING" | "REVOKED" | undefined,
              }),
            },
          }),
        )
      ).data as InvitationPage,
    placeholderData: keepPreviousData,
    enabled,
  });
}

function useInvalidateInvitations() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: adminUserKeys.invitations });
}

/** `POST /invitations`. El formulario maneja sus errores (campo o toast). */
export function useCreateInvitation() {
  const invalidate = useInvalidateInvitations();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: InvitationCreateRequest) =>
      (await call(api.POST("/api/v1/invitations", { body }))).data as Invitation,
    onSuccess: invalidate,
  });
}

/** `POST /invitations/{id}/resend`: revoca el enlace anterior y manda uno nuevo. */
export function useResendInvitation() {
  const invalidate = useInvalidateInvitations();
  return useMutation({
    mutationFn: async (id: string) =>
      (
        await call(
          api.POST("/api/v1/invitations/{invitation_id}/resend", {
            params: { path: { invitation_id: id } },
          }),
        )
      ).data as Invitation,
    onSuccess: invalidate,
  });
}

/** `DELETE /invitations/{id}`: revoca una invitación pendiente. */
export function useRevokeInvitation() {
  const invalidate = useInvalidateInvitations();
  return useMutation({
    mutationFn: async (id: string) => {
      await call(
        api.DELETE("/api/v1/invitations/{invitation_id}", {
          params: { path: { invitation_id: id } },
        }),
      );
    },
    onSuccess: invalidate,
  });
}

/** `POST /invitations/accept` (público): define la contraseña. No inicia sesión. */
export function useAcceptInvitation() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: InvitationAcceptRequest) =>
      (await call(api.POST("/api/v1/invitations/accept", { body }))).data as AcceptedUser,
  });
}
