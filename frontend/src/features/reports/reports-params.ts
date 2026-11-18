"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  apiFilters,
  parseDashboardFilters,
  type DashboardFilters,
} from "@/features/dashboard/dashboard-params";

// Estado de `/reportes` en la URL: pestaña, los filtros del dashboard, el estado (se repite
// para varios: `status=FILED&status=APPROVED`), "Agrupar por" y la página.

export const REPORT_TABS = ["embudo", "solicitudes"] as const;
export type ReportTab = (typeof REPORT_TABS)[number];
export const DEFAULT_REPORT_TAB: ReportTab = "embudo";

/** `group_by` de `GET /reports/funnel`. */
export const GROUP_BY = ["advisor", "bank", "purpose"] as const;
export type GroupBy = (typeof GROUP_BY)[number];

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;

/** Filtros que reciben el embudo, el listado, el CSV y la exportación. */
export interface ReportFilters extends DashboardFilters {
  status: string[];
}

export interface ReportParams extends ReportFilters {
  tab: ReportTab;
  group_by: GroupBy | "";
  page: number;
  page_size: number;
}

/** Campos que pueden traer un error de filtro de la API. */
export const REPORT_FILTER_KEYS = [
  "date_from",
  "date_to",
  "advisor_id",
  "bank_id",
  "purpose_code",
  "status",
  "group_by",
] as const;

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

export function parseReportParams(search: URLSearchParams): ReportParams {
  const tab = search.get("tab") ?? "";
  const groupBy = search.get("group_by") ?? "";
  const size = positiveInt(search.get("page_size"));
  const status = [
    ...new Set(
      search
        .getAll("status")
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  return {
    ...parseDashboardFilters(search),
    status,
    tab: (REPORT_TABS as readonly string[]).includes(tab) ? (tab as ReportTab) : DEFAULT_REPORT_TAB,
    group_by: (GROUP_BY as readonly string[]).includes(groupBy) ? (groupBy as GroupBy) : "",
    page: positiveInt(search.get("page")) ?? 1,
    page_size: size && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

/** Query string sin los valores por defecto; el estado se repite. */
export function serializeReportParams(params: ReportParams): string {
  const out = new URLSearchParams();
  if (params.tab !== DEFAULT_REPORT_TAB) out.set("tab", params.tab);
  for (const [key, value] of Object.entries(apiFilters(params))) out.set(key, value);
  for (const status of params.status) out.append("status", status);
  if (params.group_by) out.set("group_by", params.group_by);
  if (params.page !== 1) out.set("page", String(params.page));
  if (params.page_size !== DEFAULT_PAGE_SIZE) out.set("page_size", String(params.page_size));
  return out.toString();
}

/** Filtros con valor, como los recibe la API (el estado como lista). */
export function reportQuery(filters: ReportFilters) {
  return {
    ...apiFilters(filters),
    ...(filters.status.length ? { status: filters.status } : {}),
  };
}

export function filtersOf(params: ReportParams): ReportFilters {
  return {
    date_from: params.date_from,
    date_to: params.date_to,
    advisor_id: params.advisor_id,
    bank_id: params.bank_id,
    purpose_code: params.purpose_code,
    status: params.status,
  };
}

export const CLEARED: Partial<ReportParams> = {
  date_from: "",
  date_to: "",
  advisor_id: "",
  bank_id: "",
  purpose_code: "",
  status: [],
  group_by: "",
};

/** Estado de la URL y `update`. Cambiar un filtro o la pestaña vuelve a la página 1. */
export function useReportParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseReportParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<ReportParams>) => {
      const resets = Object.keys(patch).some((k) => k !== "page");
      const qs = serializeReportParams({ ...params, ...(resets ? { page: 1 } : {}), ...patch });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
