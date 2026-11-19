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
import { PARTICIPANT_ROLES, REQUIREMENT_STATUSES } from "@/features/admin-documents/labels";

// Estado de `/admin/documentos` en la URL: la pestaña (`vista`), sus filtros, el orden, la
// página y el elemento abierto en el panel. Cambiar de pestaña limpia el resto.

export type DocumentsView = "tipos" | "requisitos" | "vista-previa";
export const DOCUMENT_VIEWS: readonly DocumentsView[] = ["tipos", "requisitos", "vista-previa"];

export const TYPE_SORT_FIELDS = ["name", "code", "created_at", "updated_at"] as const;
export const REQUIREMENT_SORT_FIELDS = [
  "sort_order",
  "version",
  "valid_from",
  "created_at",
] as const;
const DEFAULT_ORDERING: Record<DocumentsView, string> = {
  tipos: "name",
  requisitos: "sort_order",
  "vista-previa": "name",
};

/** Valor del filtro de producto para "solo requisitos generales" (`general=true`). */
export const GENERAL = "general";

export type DocumentsParams = {
  vista: DocumentsView;
  search: string;
  /** Tipos: "true"/"false" (`is_active`). */
  active: string;
  /** Requisitos. */
  status: string;
  /** Id del producto o `general`. */
  product: string;
  /** Id del tipo documental. */
  doc_type: string;
  purpose: string;
  role: string;
  ordering: string;
  page: number;
  page_size: number;
  /** Panel abierto: tipo o requisito, según la pestaña. */
  abierto: string;
};

export const DOCUMENTS_DEFAULTS: DocumentsParams = {
  vista: "tipos",
  search: "",
  active: "",
  status: "",
  product: "",
  doc_type: "",
  purpose: "",
  role: "",
  ordering: DEFAULT_ORDERING.tipos,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  abierto: "",
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CODE = /^[A-Za-z0-9_-]{1,80}$/;
const uuid = (value: string | null) => (value && UUID.test(value) ? value : "");
const oneOf = (values: readonly string[], value: string | null) =>
  value && values.includes(value) ? value : "";

export function sortFieldsFor(view: DocumentsView): readonly string[] {
  return view === "requisitos" ? REQUIREMENT_SORT_FIELDS : TYPE_SORT_FIELDS;
}

export function defaultOrdering(view: DocumentsView): string {
  return DEFAULT_ORDERING[view];
}

export function parseDocumentsParams(search: URLSearchParams): DocumentsParams {
  const raw = search.get("vista");
  const vista: DocumentsView = DOCUMENT_VIEWS.includes(raw as DocumentsView)
    ? (raw as DocumentsView)
    : "tipos";
  const types = vista === "tipos";
  const requirements = vista === "requisitos";
  const product = search.get("product") ?? "";
  const purpose = search.get("purpose") ?? "";
  return {
    vista,
    search: types ? (search.get("search") ?? "").trim() : "",
    active: types ? oneOf(["true", "false"], search.get("active")) : "",
    status: requirements ? oneOf(REQUIREMENT_STATUSES, search.get("status")) : "",
    product: requirements && (product === GENERAL || UUID.test(product)) ? product : "",
    doc_type: requirements ? uuid(search.get("doc_type")) : "",
    purpose: requirements && CODE.test(purpose) ? purpose : "",
    role: requirements ? oneOf(PARTICIPANT_ROLES, search.get("role")) : "",
    ordering: formatOrdering(
      parseOrdering(search.get("ordering"), sortFieldsFor(vista), DEFAULT_ORDERING[vista]),
    ),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
    abierto: vista === "vista-previa" ? "" : uuid(search.get("abierto")),
  };
}

export const DOCUMENTS_CONFIG: ListParamsConfig<DocumentsParams> = {
  defaults: DOCUMENTS_DEFAULTS,
  order: [
    "vista",
    "search",
    "active",
    "status",
    "product",
    "doc_type",
    "purpose",
    "role",
    "ordering",
    "page",
    "page_size",
    "abierto",
  ],
  parse: parseDocumentsParams,
  keepPage: ["abierto"],
};

export const useDocumentsParams = () => useListParams(DOCUMENTS_CONFIG);
