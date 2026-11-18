"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

// Estado de `/prospectos` en la URL: pestaña, estado del prospecto y página.

export const BROKER_TABS = ["prospectos", "solicitudes"] as const;
export type BrokerTab = (typeof BROKER_TABS)[number];
export const DEFAULT_BROKER_TAB: BrokerTab = "prospectos";

/** Estados de `GET /broker/opportunities?status=` (enum del contrato). */
export const OPPORTUNITY_STATUSES = [
  "NEW",
  "ASSIGNED",
  "CONTACTED",
  "IN_PROGRESS",
  "CONVERTED",
  "LOST",
  "CANCELLED",
] as const;
export type OpportunityStatusCode = (typeof OPPORTUNITY_STATUSES)[number];

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;

export interface BrokerParams {
  tab: BrokerTab;
  /** Solo en la pestaña de prospectos. */
  status: OpportunityStatusCode | "";
  page: number;
  page_size: number;
}

function positiveInt(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 ? n : null;
}

export function parseBrokerParams(search: URLSearchParams): BrokerParams {
  const tab = search.get("tab") ?? "";
  const status = search.get("status") ?? "";
  const size = positiveInt(search.get("page_size"));
  const parsedTab = (BROKER_TABS as readonly string[]).includes(tab)
    ? (tab as BrokerTab)
    : DEFAULT_BROKER_TAB;
  return {
    tab: parsedTab,
    status:
      parsedTab === "prospectos" && (OPPORTUNITY_STATUSES as readonly string[]).includes(status)
        ? (status as OpportunityStatusCode)
        : "",
    page: positiveInt(search.get("page")) ?? 1,
    page_size: size && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

export function serializeBrokerParams(params: BrokerParams): string {
  const out = new URLSearchParams();
  if (params.tab !== DEFAULT_BROKER_TAB) out.set("tab", params.tab);
  if (params.tab === "prospectos" && params.status) out.set("status", params.status);
  if (params.page !== 1) out.set("page", String(params.page));
  if (params.page_size !== DEFAULT_PAGE_SIZE) out.set("page_size", String(params.page_size));
  return out.toString();
}

/** Estado de la URL y `update`. Cambiar la pestaña o el estado vuelve a la página 1. */
export function useBrokerParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = searchParams.toString();
  const params = useMemo(() => parseBrokerParams(new URLSearchParams(query)), [query]);

  const update = useCallback(
    (patch: Partial<BrokerParams>) => {
      const resets = Object.keys(patch).some((k) => k !== "page");
      const next = { ...params, ...(resets ? { page: 1 } : {}), ...patch };
      if (patch.tab && patch.tab !== params.tab) next.status = "";
      const qs = serializeBrokerParams(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return { params, update };
}
