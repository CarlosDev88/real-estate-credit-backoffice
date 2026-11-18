"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  apiFilters,
  DASHBOARD_FILTER_KEYS,
  type DashboardFilterKey,
  type DashboardFilters,
} from "@/features/dashboard/dashboard-params";
import { api, call } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type DashboardSummary = components["schemas"]["DashboardSummary"];
export type DashboardFunnel = components["schemas"]["DashboardFunnel"];
export type DashboardWorkload = components["schemas"]["DashboardWorkload"];
export type DashboardBankResults = components["schemas"]["DashboardBankResults"];
export type StatusCount = components["schemas"]["StatusCount"];
export type FunnelStage = components["schemas"]["FunnelStage"];
export type AdvisorWorkload = components["schemas"]["AdvisorWorkload"];
export type BankResult = components["schemas"]["BankResult"];
export type Period = components["schemas"]["Period"];
type MetadataItem = components["schemas"]["MetadataItem"];

export const dashboardKeys = {
  all: ["dashboard"] as const,
  block: (block: string, filters: DashboardFilters) => ["dashboard", block, filters] as const,
};

// Los cuatro bloques reciben los mismos filtros; cada uno carga y falla por su cuenta.
// Mientras llegan los datos de otro filtro, se ven los anteriores.

export function useDashboardSummary(filters: DashboardFilters) {
  return useQuery({
    queryKey: dashboardKeys.block("summary", filters),
    queryFn: async () =>
      (await call(api.GET("/api/v1/dashboard/summary", { params: { query: apiFilters(filters) } })))
        .data,
    placeholderData: keepPreviousData,
  });
}

export function useDashboardFunnel(filters: DashboardFilters) {
  return useQuery({
    queryKey: dashboardKeys.block("funnel", filters),
    queryFn: async () =>
      (await call(api.GET("/api/v1/dashboard/funnel", { params: { query: apiFilters(filters) } })))
        .data,
    placeholderData: keepPreviousData,
  });
}

export function useDashboardWorkload(filters: DashboardFilters) {
  return useQuery({
    queryKey: dashboardKeys.block("workload", filters),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/dashboard/workload", { params: { query: apiFilters(filters) } }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

export function useDashboardBankResults(filters: DashboardFilters) {
  return useQuery({
    queryKey: dashboardKeys.block("bank-results", filters),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/dashboard/bank-results", { params: { query: apiFilters(filters) } }),
        )
      ).data,
    placeholderData: keepPreviousData,
  });
}

// ---------- opciones de los filtros ----------

/**
 * Código del rol de asesor en `GET /users?role=`. Es un código de la API (no un texto
 * que se muestre), como los códigos de estado que deciden el tono.
 */
export const ADVISOR_ROLE = "ADVISOR";

/** Asesores activos, para el filtro del administrador (pide `users.read`). */
export function useAdvisors(enabled: boolean) {
  return useQuery({
    queryKey: ["users", "advisors", "active"],
    queryFn: async () => {
      const { data } = await call(
        api.GET("/api/v1/users", {
          params: { query: { role: ADVISOR_ROLE, status: "ACTIVE", page_size: 100 } },
        }),
      );
      return [...data.items].sort((a, b) =>
        (a.name || a.email).localeCompare(b.name || b.email, "es"),
      );
    },
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Bancos activos (pide `banks.read`). Misma clave de caché que el listado de solicitudes. */
export function useActiveBanks(enabled: boolean) {
  return useQuery({
    queryKey: ["banks", "active"],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/banks", {
            params: { query: { status: "ACTIVE", ordering: "name", page_size: 100 } },
          }),
        )
      ).data.items,
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Nombre del banco para listas: `short_name`, o `name` si viene vacío. */
export function bankLabel(bank: { name: string; short_name: string }): string {
  return bank.short_name.trim() || bank.name;
}

/** `/metadata/bootstrap` (misma clave de caché que el resto de la app). */
function useBootstrap() {
  return useQuery({
    queryKey: ["metadata", "bootstrap"],
    queryFn: async () => (await call(api.GET("/api/v1/metadata/bootstrap"))).data,
    staleTime: 10 * 60_000,
  });
}

/** Valores activos de un catálogo del bootstrap, en el orden de la API. */
export function useCatalog(code: string): { items: MetadataItem[]; isPending: boolean } {
  const bootstrap = useBootstrap();
  const raw = bootstrap.data?.catalogs[code];
  const items = useMemo(
    () => (raw ?? []).filter((item) => item.active).sort((a, b) => a.order - b.order),
    [raw],
  );
  return { items, isPending: bootstrap.isPending };
}

// ---------- errores de los filtros ----------

/**
 * El error viene de un filtro: un `400` de validación o un `403 FILTER_OUT_OF_SCOPE` con
 * `details[].field` en uno de los filtros. Se muestra en el filtro, no como falla del bloque.
 */
export function isFilterError(error: unknown): boolean {
  if (!isApiError(error)) return false;
  if (error.status !== 400 && error.code !== "FILTER_OUT_OF_SCOPE") return false;
  return error.fieldDetails.some((d) =>
    (DASHBOARD_FILTER_KEYS as string[]).includes(d.field ?? ""),
  );
}

/** Mensaje de la API por filtro, del primer error de filtro entre los bloques. */
export function filterErrorsOf(errors: unknown[]): Partial<Record<DashboardFilterKey, string>> {
  const error = errors.find(isFilterError);
  if (!isApiError(error)) return {};
  const out: Partial<Record<DashboardFilterKey, string>> = {};
  for (const detail of error.fieldDetails) {
    const key = detail.field as DashboardFilterKey;
    if (DASHBOARD_FILTER_KEYS.includes(key) && !out[key]) out[key] = detail.message;
  }
  return out;
}

/** El bloque no es para este usuario (`403` que no es de un filtro): no se muestra. */
export function isForbidden(error: unknown): boolean {
  return isApiError(error) && error.status === 403 && !isFilterError(error);
}
