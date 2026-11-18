"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

// Pestaña del detalle del cliente en `?tab=` y oportunidad abierta en el panel lateral en
// `?oportunidad=` (solo en la pestaña Oportunidades). La pestaña por defecto no se escribe.

export const CLIENT_TABS = ["resumen", "oportunidades", "solicitudes"] as const;
export type ClientTab = (typeof CLIENT_TABS)[number];
export const DEFAULT_CLIENT_TAB: ClientTab = "resumen";
export const OPPORTUNITY_PARAM = "oportunidad";

export function parseClientTab(raw: string | null): ClientTab {
  return (CLIENT_TABS as readonly string[]).includes(raw ?? "")
    ? (raw as ClientTab)
    : DEFAULT_CLIENT_TAB;
}

/** `?tab=oportunidades&oportunidad=<id>` para un enlace directo a una oportunidad. */
export function clientTabQuery(tab: ClientTab, opportunityId?: string | null): string {
  const query = new URLSearchParams();
  if (tab !== DEFAULT_CLIENT_TAB) query.set("tab", tab);
  if (tab === "oportunidades" && opportunityId) query.set(OPPORTUNITY_PARAM, opportunityId);
  return query.toString();
}

export function useClientTab() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = parseClientTab(searchParams.get("tab"));
  const opportunityId = tab === "oportunidades" ? searchParams.get(OPPORTUNITY_PARAM) : null;

  const go = useCallback(
    (next: ClientTab, opportunity: string | null = null) => {
      const qs = clientTabQuery(next, opportunity);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  return { tab, opportunityId, go };
}
