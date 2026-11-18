"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { DEFAULT_PAGE_SIZES } from "@/components/ui/list-pagination";

// Estado de los listados de administración en la URL, con el mismo patrón que
// `/solicitudes` y `/clientes`: los valores por defecto no se escriben, y cambiar un
// filtro, el orden o el tamaño de página vuelve a la página 1.

/** Corte del shell: en 860 px o menos, tarjetas en lugar de tabla. */
export const MOBILE_QUERY = "(max-width: 860px)";
export const SEARCH_DEBOUNCE_MS = 300;
export const PAGE_SIZES = DEFAULT_PAGE_SIZES;
export const DEFAULT_PAGE_SIZE = 20;

export interface Sorting {
  field: string;
  desc: boolean;
}

/** `-created_at` → `{ field: "created_at", desc: true }`; un campo desconocido → el por defecto. */
export function parseOrdering(
  value: string | null | undefined,
  fields: readonly string[],
  fallback: string,
): Sorting {
  const raw = value ?? "";
  const desc = raw.startsWith("-");
  const field = desc ? raw.slice(1) : raw;
  if (fields.includes(field)) return { field, desc };
  const fallbackDesc = fallback.startsWith("-");
  return { field: fallbackDesc ? fallback.slice(1) : fallback, desc: fallbackDesc };
}

export function formatOrdering({ field, desc }: Sorting): string {
  return `${desc ? "-" : ""}${field}`;
}

export function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

/** Quita los valores vacíos antes de mandarlos a la API. */
export function compact<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined),
  ) as Partial<T>;
}

/** Valores de un listado: textos (filtros, orden, selección) y la paginación. */
export type ListValues = Record<string, string | number>;

export interface ListParamsConfig<P extends ListValues> {
  defaults: P;
  /** Orden de las claves en la URL. */
  order: readonly (keyof P & string)[];
  /** Lee y limpia los valores de la URL. */
  parse: (search: URLSearchParams) => P;
  /** Claves que no reinician la página al cambiar (la página misma, el panel abierto). */
  keepPage?: readonly (keyof P & string)[];
}

/** Query string sin los valores por defecto (`""` si todo está por defecto). */
export function serializeListParams<P extends ListValues>(
  params: P,
  config: Pick<ListParamsConfig<P>, "defaults" | "order">,
): string {
  const out = new URLSearchParams();
  for (const key of config.order) {
    const value = params[key];
    if (value !== "" && value !== config.defaults[key]) out.set(key, String(value));
  }
  return out.toString();
}

/** Tamaño de página de la URL, si es uno de los permitidos. */
export function parsePageSize(search: URLSearchParams): number {
  const size = positiveInt(search.get("page_size"));
  return size && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE;
}

/**
 * Estado del listado leído de la URL, y `update` para cambiarlo. `replace` cambia todo el
 * estado de una vez (cambiar de pestaña, por ejemplo).
 */
export function useListParams<P extends ListValues>(config: ListParamsConfig<P>) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const { parse, defaults, order, keepPage } = config;
  const params = useMemo(() => parse(new URLSearchParams(query)), [parse, query]);

  const write = useCallback(
    (next: P) => {
      const qs = serializeListParams(next, { defaults, order });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [defaults, order, pathname, router],
  );

  const update = useCallback(
    (patch: Partial<P>) => {
      const keep = new Set<string>(["page", ...(keepPage ?? [])]);
      const resetsPage = Object.keys(patch).some((key) => !keep.has(key));
      write({ ...params, ...(resetsPage ? { page: 1 } : {}), ...patch });
    },
    [keepPage, params, write],
  );

  const replace = useCallback(
    (patch: Partial<P>) => write({ ...defaults, ...patch }),
    [defaults, write],
  );

  return { params, update, replace };
}
