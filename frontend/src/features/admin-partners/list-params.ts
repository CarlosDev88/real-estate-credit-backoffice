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

// Estado de `/admin/constructoras` en la URL: búsqueda, estado, municipio (constructoras
// con proyectos allí), orden, página y la constructora abierta en el panel.

/** Campos que la API sabe ordenar (`ordering_fields` de `GET /partners`). */
export const PARTNER_SORT_FIELDS = ["legal_name", "created_at", "updated_at"] as const;
export const DEFAULT_PARTNER_ORDERING = "-created_at";

/** `enum` del contrato (`PartnerStatusEnum`); la etiqueta va en `status.ts`. */
export const PARTNER_STATUS_CODES = ["ACTIVE", "INACTIVE"] as const;
export type PartnerStatusCode = (typeof PARTNER_STATUS_CODES)[number];

export type PartnersParams = {
  search: string;
  status: string;
  /** Código DANE del municipio (`city_code`). */
  city: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Id de la constructora abierta en el panel lateral. */
  constructora: string;
};

export const PARTNERS_DEFAULTS: PartnersParams = {
  search: "",
  status: "",
  city: "",
  ordering: DEFAULT_PARTNER_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  constructora: "",
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CODE = /^[A-Za-z0-9_-]{1,50}$/;

export function parsePartnersParams(search: URLSearchParams): PartnersParams {
  const status = search.get("status") ?? "";
  const city = search.get("city") ?? "";
  const constructora = search.get("constructora") ?? "";
  return {
    search: (search.get("search") ?? "").trim(),
    status: (PARTNER_STATUS_CODES as readonly string[]).includes(status) ? status : "",
    city: CODE.test(city) ? city : "",
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), PARTNER_SORT_FIELDS, DEFAULT_PARTNER_ORDERING),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    constructora: UUID.test(constructora) ? constructora : "",
  };
}

export const PARTNERS_CONFIG: ListParamsConfig<PartnersParams> = {
  defaults: PARTNERS_DEFAULTS,
  order: ["search", "status", "city", "ordering", "page", "page_size", "constructora"],
  parse: parsePartnersParams,
  keepPage: ["constructora"],
};

export function usePartnersParams() {
  return useListParams(PARTNERS_CONFIG);
}

export const PARTNERS_HREF = "/admin/constructoras";
