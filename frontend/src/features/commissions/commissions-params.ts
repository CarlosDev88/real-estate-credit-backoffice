"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

// Estado de `/comisiones` y `/mis-comisiones` en la URL, con los nombres de los parámetros
// de la API. Vacío es "sin filtro". Cambiar un filtro o la pestaña vuelve a la página 1.

export const COMMISSION_TABS = ["liquidaciones", "planes"] as const;
export type CommissionTab = (typeof COMMISSION_TABS)[number];
export const DEFAULT_COMMISSION_TAB: CommissionTab = "liquidaciones";

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;

/** Estados de `GET /commission-settlements?status=` (enum del contrato). */
export const SETTLEMENT_STATUSES = ["ACTIVE", "VOIDED"] as const;
/** Estados de `GET /me/commissions?status=` (enum del contrato). */
export const SHARE_STATUSES = ["PENDING", "PAID", "VOIDED"] as const;
export const REVIEW_VALUES = ["true", "false"] as const;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface SettlementFilters {
  status: string;
  bank_id: string;
  advisor_id: string;
  broker_id: string;
  needs_review: string;
  date_from: string;
  date_to: string;
}

export interface SettlementParams extends SettlementFilters {
  page: number;
  page_size: number;
}

export interface PlanParams {
  bank_product_id: string;
  page: number;
  page_size: number;
}

export interface CommissionParams {
  tab: CommissionTab;
  settlements: SettlementParams;
  plans: PlanParams;
  /** Liquidación abierta en el panel (`?liquidacion=<id>`). */
  open: string;
}

export interface MyCommissionParams {
  status: string;
  date_from: string;
  date_to: string;
  page: number;
  page_size: number;
}

export const SETTLEMENT_FILTER_KEYS: readonly (keyof SettlementFilters)[] = [
  "status",
  "bank_id",
  "advisor_id",
  "broker_id",
  "needs_review",
  "date_from",
  "date_to",
];

export const EMPTY_SETTLEMENT_FILTERS: SettlementFilters = {
  status: "",
  bank_id: "",
  advisor_id: "",
  broker_id: "",
  needs_review: "",
  date_from: "",
  date_to: "",
};

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

function pageSize(value: string | null): number {
  const n = positiveInt(value);
  return n && (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
}

function oneOf(value: string | null, allowed: readonly string[]): string {
  const v = (value ?? "").trim();
  return allowed.includes(v) ? v : "";
}

const text = (search: URLSearchParams, key: string) => (search.get(key) ?? "").trim();
const date = (search: URLSearchParams, key: string) => {
  const v = text(search, key);
  return ISO_DATE.test(v) ? v : "";
};

export function parseCommissionParams(search: URLSearchParams): CommissionParams {
  const tab = search.get("tab") ?? "";
  return {
    tab: (COMMISSION_TABS as readonly string[]).includes(tab)
      ? (tab as CommissionTab)
      : DEFAULT_COMMISSION_TAB,
    settlements: {
      status: oneOf(search.get("status"), SETTLEMENT_STATUSES),
      bank_id: text(search, "bank_id"),
      advisor_id: text(search, "advisor_id"),
      broker_id: text(search, "broker_id"),
      needs_review: oneOf(search.get("needs_review"), REVIEW_VALUES),
      date_from: date(search, "date_from"),
      date_to: date(search, "date_to"),
      page: positiveInt(search.get("page")) ?? 1,
      page_size: pageSize(search.get("page_size")),
    },
    plans: {
      bank_product_id: text(search, "bank_product_id"),
      page: positiveInt(search.get("page")) ?? 1,
      page_size: pageSize(search.get("page_size")),
    },
    open: text(search, "liquidacion"),
  };
}

/** Query string sin los valores por defecto. Solo se escriben los de la pestaña activa. */
export function serializeCommissionParams(params: CommissionParams): string {
  const out = new URLSearchParams();
  if (params.tab !== DEFAULT_COMMISSION_TAB) out.set("tab", params.tab);
  const paging = params.tab === "planes" ? params.plans : params.settlements;
  if (params.tab === "liquidaciones") {
    for (const key of SETTLEMENT_FILTER_KEYS) {
      if (params.settlements[key]) out.set(key, params.settlements[key]);
    }
    if (params.open) out.set("liquidacion", params.open);
  } else if (params.plans.bank_product_id) {
    out.set("bank_product_id", params.plans.bank_product_id);
  }
  if (paging.page !== 1) out.set("page", String(paging.page));
  if (paging.page_size !== DEFAULT_PAGE_SIZE) out.set("page_size", String(paging.page_size));
  return out.toString();
}

/** Parámetros de `GET /commission-settlements`: solo los que tienen valor. */
export function settlementsQuery(params: SettlementParams) {
  const out: Record<string, string | number | boolean> = {
    page: params.page,
    page_size: params.page_size,
  };
  for (const key of SETTLEMENT_FILTER_KEYS) {
    const value = params[key];
    if (!value) continue;
    out[key] = key === "needs_review" ? value === "true" : value;
  }
  return out as {
    page: number;
    page_size: number;
    status?: "ACTIVE" | "VOIDED";
    bank_id?: string;
    advisor_id?: string;
    broker_id?: string;
    needs_review?: boolean;
    date_from?: string;
    date_to?: string;
  };
}

export function plansQuery(params: PlanParams) {
  return {
    page: params.page,
    page_size: params.page_size,
    ...(params.bank_product_id ? { bank_product_id: params.bank_product_id } : {}),
  };
}

export function hasSettlementFilters(filters: SettlementFilters): boolean {
  return SETTLEMENT_FILTER_KEYS.some((key) => filters[key] !== "");
}

/** Estado de `/comisiones` y `update`. */
export function useCommissionParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseCommissionParams(new URLSearchParams(query)), [query]);

  const write = useCallback(
    (next: CommissionParams) => {
      const qs = serializeCommissionParams(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  /** Cambia filtros de las liquidaciones; si no es solo la página, vuelve a la 1. */
  const updateSettlements = useCallback(
    (patch: Partial<SettlementParams>) => {
      const resets = Object.keys(patch).some((k) => k !== "page");
      write({
        ...params,
        settlements: { ...params.settlements, ...(resets ? { page: 1 } : {}), ...patch },
      });
    },
    [params, write],
  );

  const updatePlans = useCallback(
    (patch: Partial<PlanParams>) => {
      const resets = Object.keys(patch).some((k) => k !== "page");
      write({ ...params, plans: { ...params.plans, ...(resets ? { page: 1 } : {}), ...patch } });
    },
    [params, write],
  );

  const setTab = useCallback(
    (tab: CommissionTab) =>
      write({
        ...parseCommissionParams(new URLSearchParams()),
        tab,
      }),
    [write],
  );

  const openSettlement = useCallback(
    (id: string | null) => write({ ...params, open: id ?? "" }),
    [params, write],
  );

  return { params, updateSettlements, updatePlans, setTab, openSettlement };
}

// ---------- mis comisiones ----------

export function parseMyCommissionParams(search: URLSearchParams): MyCommissionParams {
  return {
    status: oneOf(search.get("status"), SHARE_STATUSES),
    date_from: date(search, "date_from"),
    date_to: date(search, "date_to"),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: pageSize(search.get("page_size")),
  };
}

export function serializeMyCommissionParams(params: MyCommissionParams): string {
  const out = new URLSearchParams();
  if (params.status) out.set("status", params.status);
  if (params.date_from) out.set("date_from", params.date_from);
  if (params.date_to) out.set("date_to", params.date_to);
  if (params.page !== 1) out.set("page", String(params.page));
  if (params.page_size !== DEFAULT_PAGE_SIZE) out.set("page_size", String(params.page_size));
  return out.toString();
}

export function myCommissionsQuery(params: MyCommissionParams) {
  return {
    page: params.page,
    page_size: params.page_size,
    ...(params.status ? { status: params.status as "PENDING" | "PAID" | "VOIDED" } : {}),
    ...(params.date_from ? { date_from: params.date_from } : {}),
    ...(params.date_to ? { date_to: params.date_to } : {}),
  };
}

export function useMyCommissionParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseMyCommissionParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<MyCommissionParams>) => {
      const resets = Object.keys(patch).some((k) => k !== "page");
      const qs = serializeMyCommissionParams({
        ...params,
        ...(resets ? { page: 1 } : {}),
        ...patch,
      });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
