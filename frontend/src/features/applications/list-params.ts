"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

// Estado del listado en la URL (`/solicitudes?bank_id=…&page=2`): un enlace copiado
// abre la misma vista. Los valores por defecto no se escriben en la URL.

/** Columnas que la API sabe ordenar (`ordering_fields` de `GET /applications`). */
export const SORTABLE_FIELDS = [
  "code",
  "applicant_name",
  "requested_amount",
  "bank_name",
  "updated_at",
] as const;
export type SortField = (typeof SORTABLE_FIELDS)[number];

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;
export const DEFAULT_ORDERING = "-updated_at";
/** Pestaña por defecto: la que no filtra. */
export const DEFAULT_QUICK_FILTER = "all";

/** Filtros que también reciben las pestañas (todo menos `quick_filter`, orden y página). */
export interface ListFilters {
  search: string;
  bank_id: string;
  product_type: string;
  purpose: string;
}

export interface ListParams extends ListFilters {
  quick_filter: string;
  ordering: string;
  page: number;
  page_size: number;
}

export type FilterKey = "bank_id" | "product_type" | "purpose";
export const FILTER_KEYS: FilterKey[] = ["bank_id", "product_type", "purpose"];

export interface Sorting {
  field: SortField;
  desc: boolean;
}

function isSortField(value: string): value is SortField {
  return (SORTABLE_FIELDS as readonly string[]).includes(value);
}

/** `-updated_at` → `{ field: "updated_at", desc: true }`; un valor desconocido → el por defecto. */
export function parseOrdering(value: string | null | undefined): Sorting {
  const raw = value ?? "";
  const desc = raw.startsWith("-");
  const field = desc ? raw.slice(1) : raw;
  if (isSortField(field)) return { field, desc };
  return parseOrdering(DEFAULT_ORDERING);
}

export function formatOrdering({ field, desc }: Sorting): string {
  return `${desc ? "-" : ""}${field}`;
}

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

/** Lee los parámetros de la URL, con los valores por defecto y sin valores inválidos. */
export function parseListParams(search: URLSearchParams): ListParams {
  const size = positiveInt(search.get("page_size"));
  return {
    quick_filter: search.get("quick_filter") || DEFAULT_QUICK_FILTER,
    search: (search.get("search") ?? "").trim(),
    bank_id: search.get("bank_id") ?? "",
    product_type: search.get("product_type") ?? "",
    purpose: search.get("purpose") ?? "",
    ordering: formatOrdering(parseOrdering(search.get("ordering"))),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: size && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

const DEFAULTS: Record<keyof ListParams, string | number> = {
  quick_filter: DEFAULT_QUICK_FILTER,
  search: "",
  bank_id: "",
  product_type: "",
  purpose: "",
  ordering: DEFAULT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
};

const ORDER: (keyof ListParams)[] = [
  "quick_filter",
  "search",
  "bank_id",
  "product_type",
  "purpose",
  "ordering",
  "page",
  "page_size",
];

/** Query string sin los valores por defecto (`""` si todo está por defecto). */
export function serializeListParams(params: ListParams): string {
  const out = new URLSearchParams();
  for (const key of ORDER) {
    const value = params[key];
    if (value !== "" && value !== DEFAULTS[key]) out.set(key, String(value));
  }
  return out.toString();
}

/** Los filtros de la lista que comparten las pestañas. */
export function filtersOf(params: ListParams): ListFilters {
  return {
    search: params.search,
    bank_id: params.bank_id,
    product_type: params.product_type,
    purpose: params.purpose,
  };
}

/** Quita los vacíos: es lo que se manda a la API. */
export function compact<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined),
  ) as Partial<T>;
}

/**
 * Estado del listado leído de la URL, y `update` para cambiarlo. Cambiar un filtro,
 * la búsqueda, la pestaña, el orden o el tamaño vuelve a la página 1.
 */
export function useListParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseListParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<ListParams>) => {
      const resetsPage = Object.keys(patch).some((key) => key !== "page");
      const next = { ...params, ...(resetsPage ? { page: 1 } : {}), ...patch };
      const qs = serializeListParams(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
