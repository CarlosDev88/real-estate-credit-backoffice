"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from "@/features/applications/list-params";

// Estado del listado de clientes en la URL (`/clientes?origin=BROKER&page=2`), con el
// mismo patrón que `/solicitudes`: los valores por defecto no se escriben.

/** Columnas que la API sabe ordenar (`ordering_fields` de `GET /clients`). */
export const CLIENT_SORT_FIELDS = ["last_names", "created_at"] as const;
export type ClientSortField = (typeof CLIENT_SORT_FIELDS)[number];
export const DEFAULT_CLIENT_ORDERING = "-created_at";

export interface ClientListParams {
  search: string;
  /** Código de `lead_origin`. */
  origin: string;
  /** "1" si viene de "Nueva solicitud": se ve la ayuda y el cliente abre en Oportunidades. */
  nueva_solicitud: string;
  ordering: string;
  page: number;
  page_size: number;
}

export interface ClientSorting {
  field: ClientSortField;
  desc: boolean;
}

export function isClientSortField(value: string): value is ClientSortField {
  return (CLIENT_SORT_FIELDS as readonly string[]).includes(value);
}

/** `-created_at` → `{ field: "created_at", desc: true }`; un valor desconocido → el por defecto. */
export function parseClientOrdering(value: string | null | undefined): ClientSorting {
  const raw = value ?? "";
  const desc = raw.startsWith("-");
  const field = desc ? raw.slice(1) : raw;
  if (isClientSortField(field)) return { field, desc };
  return parseClientOrdering(DEFAULT_CLIENT_ORDERING);
}

export function formatClientOrdering({ field, desc }: ClientSorting): string {
  return `${desc ? "-" : ""}${field}`;
}

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

export const CLIENT_LIST_DEFAULTS: ClientListParams = {
  search: "",
  origin: "",
  nueva_solicitud: "",
  ordering: DEFAULT_CLIENT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
};

const ORDER: (keyof ClientListParams)[] = [
  "nueva_solicitud",
  "search",
  "origin",
  "ordering",
  "page",
  "page_size",
];

/** Lee los parámetros de la URL, con los valores por defecto y sin valores inválidos. */
export function parseClientListParams(search: URLSearchParams): ClientListParams {
  const size = positiveInt(search.get("page_size"));
  return {
    search: (search.get("search") ?? "").trim(),
    origin: search.get("origin") ?? "",
    nueva_solicitud: search.get("nueva_solicitud") === "1" ? "1" : "",
    ordering: formatClientOrdering(parseClientOrdering(search.get("ordering"))),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: size && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

/** Query string sin los valores por defecto (`""` si todo está por defecto). */
export function serializeClientListParams(params: ClientListParams): string {
  const out = new URLSearchParams();
  for (const key of ORDER) {
    const value = params[key];
    if (value !== "" && value !== CLIENT_LIST_DEFAULTS[key]) out.set(key, String(value));
  }
  return out.toString();
}

/**
 * Estado del listado leído de la URL, y `update` para cambiarlo. Cambiar la búsqueda,
 * el filtro, el orden o el tamaño vuelve a la página 1.
 */
export function useClientListParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseClientListParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<ClientListParams>) => {
      const resetsPage = Object.keys(patch).some((key) => key !== "page");
      const next = { ...params, ...(resetsPage ? { page: 1 } : {}), ...patch };
      const qs = serializeClientListParams(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
