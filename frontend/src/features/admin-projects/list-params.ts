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

// Estado de `/proyectos` en la URL: búsqueda, estado, constructora, municipio, orden,
// página y el proyecto abierto en el panel (`proyecto`).

/** Campos que la API sabe ordenar (`ordering_fields` de `GET /projects`). */
export const PROJECT_SORT_FIELDS = [
  "name",
  "status",
  "estimated_delivery_date",
  "created_at",
  "updated_at",
] as const;
export const DEFAULT_PROJECT_ORDERING = "-created_at";

/** `enum` del contrato (`ProjectStatusEnum`); la etiqueta sale del catálogo `project_status`. */
export const PROJECT_STATUS_CODES = ["DRAFT", "PENDING_REVIEW", "ACTIVE", "ARCHIVED"] as const;
export type ProjectStatusCode = (typeof PROJECT_STATUS_CODES)[number];

export type ProjectsParams = {
  search: string;
  status: string;
  /** Id de la constructora (`partner_id`). */
  partner: string;
  /** Código DANE del municipio (`city_code`). */
  city: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Id del proyecto abierto en el panel lateral. */
  proyecto: string;
};

export const PROJECTS_DEFAULTS: ProjectsParams = {
  search: "",
  status: "",
  partner: "",
  city: "",
  ordering: DEFAULT_PROJECT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  proyecto: "",
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CODE = /^[A-Za-z0-9_-]{1,50}$/;
const uuidOrEmpty = (value: string | null) => (value && UUID.test(value) ? value : "");

export function parseProjectsParams(search: URLSearchParams): ProjectsParams {
  const status = search.get("status") ?? "";
  const city = search.get("city") ?? "";
  return {
    search: (search.get("search") ?? "").trim(),
    status: (PROJECT_STATUS_CODES as readonly string[]).includes(status) ? status : "",
    partner: uuidOrEmpty(search.get("partner")),
    city: CODE.test(city) ? city : "",
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), PROJECT_SORT_FIELDS, DEFAULT_PROJECT_ORDERING),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    proyecto: uuidOrEmpty(search.get("proyecto")),
  };
}

export const PROJECTS_CONFIG: ListParamsConfig<ProjectsParams> = {
  defaults: PROJECTS_DEFAULTS,
  order: ["search", "status", "partner", "city", "ordering", "page", "page_size", "proyecto"],
  parse: parseProjectsParams,
  keepPage: ["proyecto"],
};

export function useProjectsParams() {
  return useListParams(PROJECTS_CONFIG);
}

export const PROJECTS_HREF = "/proyectos";
