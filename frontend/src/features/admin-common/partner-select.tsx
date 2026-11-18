"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Select } from "antd";
import { useState } from "react";

import { compact } from "@/features/admin-common/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Partner = components["schemas"]["Partner"];

/** Nombre de una constructora: el comercial y, si no hay, la razón social. */
export function partnerName(partner: Pick<Partner, "trade_name" | "legal_name">): string {
  return partner.trade_name || partner.legal_name;
}

export const partnerOptionKeys = {
  all: ["admin-partner-options"] as const,
  search: (status: string, search: string) => ["admin-partner-options", status, search] as const,
};

/**
 * `GET /partners` para un selector: con búsqueda en la API, 50 por página y orden por
 * razón social (`trade_name` no es campo de orden). `status` vacío: todas.
 */
export function usePartnerOptions(
  search: string,
  enabled: boolean,
  status: "ACTIVE" | "" = "ACTIVE",
) {
  return useQuery({
    queryKey: partnerOptionKeys.search(status, search),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/partners", {
            params: {
              query: compact({
                status: status || undefined,
                search,
                ordering: "legal_name",
                page_size: 50,
              }),
            },
          }),
        )
      ).data.items as Partner[],
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Selector de una constructora (activa por defecto), con búsqueda en la API. */
export function PartnerSelect({
  value,
  onChange,
  control,
  enabled,
  status = "ACTIVE",
  placeholder = "Busca la constructora",
  allowClear = false,
}: {
  value: string;
  onChange: (value: string) => void;
  /** Props de `FormField` (id, aria-*, status) o, en un filtro, su `aria-label`. */
  control: object;
  enabled: boolean;
  status?: "ACTIVE" | "";
  placeholder?: string;
  allowClear?: boolean;
}) {
  const [search, setSearch] = useState("");
  const partners = usePartnerOptions(search, enabled, status);
  return (
    <Select
      {...control}
      value={value || undefined}
      onChange={(next?: string) => onChange(next ?? "")}
      placeholder={placeholder}
      allowClear={allowClear}
      showSearch={{ filterOption: false, onSearch: setSearch }}
      loading={partners.isFetching}
      notFoundContent={
        partners.isPending
          ? "Cargando…"
          : status
            ? "No hay constructoras activas"
            : "No hay constructoras"
      }
      options={(partners.data ?? []).map((partner) => ({
        value: partner.id,
        label: partnerName(partner),
      }))}
    />
  );
}
