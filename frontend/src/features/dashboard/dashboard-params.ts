"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

// Filtros del dashboard en la URL (`/dashboard?date_from=2026-11-01&bank_id=…`), con los
// mismos nombres que los parámetros de la API. Vacío es "sin filtro": sin fechas, la API
// usa el mes en curso y lo devuelve en `period`.

export interface DashboardFilters {
  date_from: string;
  date_to: string;
  advisor_id: string;
  bank_id: string;
  purpose_code: string;
}

export type DashboardFilterKey = keyof DashboardFilters;

export const DASHBOARD_FILTER_KEYS: DashboardFilterKey[] = [
  "date_from",
  "date_to",
  "advisor_id",
  "bank_id",
  "purpose_code",
];

export const EMPTY_FILTERS: DashboardFilters = {
  date_from: "",
  date_to: "",
  advisor_id: "",
  bank_id: "",
  purpose_code: "",
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Lee los filtros de la URL. Una fecha mal escrita se ignora (vuelve al rango por defecto). */
export function parseDashboardFilters(search: URLSearchParams): DashboardFilters {
  const date = (key: string) => {
    const value = (search.get(key) ?? "").trim();
    return ISO_DATE.test(value) ? value : "";
  };
  const text = (key: string) => (search.get(key) ?? "").trim();
  return {
    date_from: date("date_from"),
    date_to: date("date_to"),
    advisor_id: text("advisor_id"),
    bank_id: text("bank_id"),
    purpose_code: text("purpose_code"),
  };
}

/** Query string sin los vacíos (`""` si no hay filtros). */
export function serializeDashboardFilters(filters: DashboardFilters): string {
  const out = new URLSearchParams();
  for (const key of DASHBOARD_FILTER_KEYS) {
    if (filters[key]) out.set(key, filters[key]);
  }
  return out.toString();
}

/** Solo los filtros con valor: es lo que se manda a la API. */
export function apiFilters(filters: DashboardFilters): Partial<DashboardFilters> {
  return Object.fromEntries(
    DASHBOARD_FILTER_KEYS.filter((key) => filters[key]).map((key) => [key, filters[key]]),
  );
}

export function hasActiveFilters(filters: DashboardFilters): boolean {
  return DASHBOARD_FILTER_KEYS.some((key) => filters[key] !== "");
}

/** Filtros leídos de la URL y `update` para cambiarlos (con `router.replace`). */
export function useDashboardFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const filters = useMemo(() => parseDashboardFilters(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<DashboardFilters>) => {
      const qs = serializeDashboardFilters({ ...filters, ...patch });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [filters, pathname, router],
  );

  return { filters, update };
}
