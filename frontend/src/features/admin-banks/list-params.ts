"use client";

import { ACTIVE_STATUS_CODES } from "@/features/admin-common/active-status";
import {
  DEFAULT_PAGE_SIZE,
  formatOrdering,
  parseOrdering,
  parsePageSize,
  positiveInt,
  useListParams,
  type ListParamsConfig,
} from "@/features/admin-common/list-params";
import { RULE_STATUS_CODES, SEVERITY_CODES } from "@/features/admin-banks/labels";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CODE = /^[A-Za-z0-9_-]{1,80}$/;
const uuidOrEmpty = (value: string | null) => (value && UUID.test(value) ? value : "");
const oneOf = (values: readonly string[], value: string | null) =>
  value && values.includes(value) ? value : "";

// ---------- /admin/bancos ----------

/** Campos que la API sabe ordenar (`ordering_fields` de `GET /banks`). */
export const BANK_SORT_FIELDS = ["name", "code", "created_at", "updated_at"] as const;
export const DEFAULT_BANK_ORDERING = "name";

export type BanksParams = {
  search: string;
  status: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Id del banco abierto en el panel lateral. */
  banco: string;
};

export const BANKS_DEFAULTS: BanksParams = {
  search: "",
  status: "",
  ordering: DEFAULT_BANK_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  banco: "",
};

export function parseBanksParams(search: URLSearchParams): BanksParams {
  return {
    search: (search.get("search") ?? "").trim(),
    status: oneOf(ACTIVE_STATUS_CODES, search.get("status")),
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), BANK_SORT_FIELDS, DEFAULT_BANK_ORDERING),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    banco: uuidOrEmpty(search.get("banco")),
  };
}

export const BANKS_CONFIG: ListParamsConfig<BanksParams> = {
  defaults: BANKS_DEFAULTS,
  order: ["search", "status", "ordering", "page", "page_size", "banco"],
  parse: parseBanksParams,
  keepPage: ["banco"],
};

export const useBanksParams = () => useListParams(BANKS_CONFIG);

export const BANKS_HREF = "/admin/bancos";
export const bankHref = (bankId: string) => `${BANKS_HREF}?banco=${bankId}`;
export const productHref = (productId: string) => `${BANKS_HREF}/productos/${productId}`;

// ---------- reglas de un producto (/admin/bancos/productos/[id]) ----------

/** Campos que la API sabe ordenar (`ordering_fields` de `GET /bank-policy-rules`). */
export const RULE_SORT_FIELDS = [
  "code",
  "version",
  "valid_from",
  "created_at",
  "updated_at",
] as const;
export const DEFAULT_RULE_ORDERING = "code";

export type RulesParams = {
  search: string;
  status: string;
  severity: string;
  /** Código de `loan_purpose`. */
  purpose: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Id de la versión de la regla abierta en el panel. */
  regla: string;
};

export const RULES_DEFAULTS: RulesParams = {
  search: "",
  status: "",
  severity: "",
  purpose: "",
  ordering: DEFAULT_RULE_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  regla: "",
};

export function parseRulesParams(search: URLSearchParams): RulesParams {
  const purpose = search.get("purpose") ?? "";
  return {
    search: (search.get("search") ?? "").trim(),
    status: oneOf(RULE_STATUS_CODES, search.get("status")),
    severity: oneOf(SEVERITY_CODES, search.get("severity")),
    purpose: CODE.test(purpose) ? purpose : "",
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), RULE_SORT_FIELDS, DEFAULT_RULE_ORDERING),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    regla: uuidOrEmpty(search.get("regla")),
  };
}

export const RULES_CONFIG: ListParamsConfig<RulesParams> = {
  defaults: RULES_DEFAULTS,
  order: ["search", "status", "severity", "purpose", "ordering", "page", "page_size", "regla"],
  parse: parseRulesParams,
  keepPage: ["regla"],
};

export const useRulesParams = () => useListParams(RULES_CONFIG);
