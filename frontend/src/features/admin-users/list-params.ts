"use client";

import {
  DEFAULT_PAGE_SIZE,
  formatOrdering,
  parseOrdering,
  parsePageSize,
  positiveInt,
  useListParams,
  type ListParamsConfig,
} from "@/features/admin-common/list-params";
import { INVITATION_STATUSES, USER_STATUSES } from "@/features/admin-users/status";

// Estado de `/admin/usuarios` en la URL: la pestaña (`vista`), los filtros, el orden, la
// página y el usuario abierto en el panel (`usuario`). Cambiar de pestaña limpia el resto.

export type AdminUsersView = "usuarios" | "invitaciones";
export const VIEWS: readonly AdminUsersView[] = ["usuarios", "invitaciones"];

/** Campos que la API sabe ordenar (`ordering_fields` de cada vista). */
export const USER_SORT_FIELDS = ["first_name", "email", "created_at", "last_login"] as const;
export const INVITATION_SORT_FIELDS = ["email", "created_at", "expires_at"] as const;
export const DEFAULT_ORDERING = "-created_at";

export type AdminUsersParams = {
  vista: AdminUsersView;
  /** Nombre o correo (solo usuarios). */
  search: string;
  /** Código del rol. */
  role: string;
  status: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Id del usuario abierto en el panel lateral. */
  usuario: string;
};

export const ADMIN_USERS_DEFAULTS: AdminUsersParams = {
  vista: "usuarios",
  search: "",
  role: "",
  status: "",
  ordering: DEFAULT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  usuario: "",
};

const ORDER = [
  "vista",
  "search",
  "role",
  "status",
  "ordering",
  "page",
  "page_size",
  "usuario",
] as const;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROLE_CODE = /^[A-Z0-9_]{1,50}$/;

export function sortFieldsOf(view: AdminUsersView): readonly string[] {
  return view === "invitaciones" ? INVITATION_SORT_FIELDS : USER_SORT_FIELDS;
}

/** Lee los parámetros de la URL, con los valores por defecto y sin valores inválidos. */
export function parseAdminUsersParams(search: URLSearchParams): AdminUsersParams {
  const vista: AdminUsersView =
    search.get("vista") === "invitaciones" ? "invitaciones" : "usuarios";
  const users = vista === "usuarios";
  const statuses = users ? USER_STATUSES : INVITATION_STATUSES;
  const status = search.get("status") ?? "";
  const role = search.get("role") ?? "";
  const usuario = search.get("usuario") ?? "";
  return {
    vista,
    search: users ? (search.get("search") ?? "").trim() : "",
    role: ROLE_CODE.test(role) ? role : "",
    status: statuses.some((s) => s.value === status) ? status : "",
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), sortFieldsOf(vista), DEFAULT_ORDERING),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    usuario: users && UUID.test(usuario) ? usuario : "",
  };
}

export const ADMIN_USERS_CONFIG: ListParamsConfig<AdminUsersParams> = {
  defaults: ADMIN_USERS_DEFAULTS,
  order: ORDER,
  parse: parseAdminUsersParams,
  keepPage: ["usuario"],
};

export function useAdminUsersParams() {
  return useListParams(ADMIN_USERS_CONFIG);
}

export const ADMIN_USERS_HREF = "/admin/usuarios";
