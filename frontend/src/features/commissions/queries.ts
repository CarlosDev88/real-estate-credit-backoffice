"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  myCommissionsQuery,
  plansQuery,
  settlementsQuery,
  type MyCommissionParams,
  type PlanParams,
  type SettlementParams,
} from "@/features/commissions/commissions-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ifMatch } from "@/lib/api/version";

type Schemas = components["schemas"];
export type CommissionSettlement = Schemas["CommissionSettlement"];
export type CommissionShare = Schemas["CommissionShare"];
export type CommissionPlan = Schemas["CommissionPlan"];
export type MyCommission = Schemas["MyCommission"];
export type BankProduct = Schemas["BankProduct"];
export type DisbursedApplication = Schemas["Application"];
export type PlanCreateRequest = Schemas["CommissionPlanCreateRequest"];
export type PlanUpdateRequest = Schemas["PatchedCommissionPlanUpdateRequest"];
export type SharePayRequest = Schemas["SharePayRequest"];

/** Código del rol de broker en `GET /users?role=` (código de la API, no un texto). */
export const BROKER_ROLE = "INDEPENDENT_BROKER";
/** Estado de la solicitud que se puede liquidar (código de la API). */
export const DISBURSED = "DISBURSED";
/** Tope de `page_size` de la API (`config/api.py`). */
const MAX_PAGE_SIZE = 100;

export const commissionKeys = {
  all: ["commissions"] as const,
  settlements: (query: object) => ["commissions", "settlements", query] as const,
  settlement: (id: string) => ["commissions", "settlement", id] as const,
  active: ["commissions", "settlements", "active-ids"] as const,
  ofApplication: (id: string) => ["commissions", "of-application", id] as const,
  plans: (query: object) => ["commissions", "plans", query] as const,
  mine: (query: object) => ["commissions", "mine", query] as const,
};

// ---------- liquidaciones ----------

export function useSettlements(params: SettlementParams, enabled = true) {
  const query = settlementsQuery(params);
  return useQuery({
    queryKey: commissionKeys.settlements(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/commission-settlements", { params: { query } }))).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Detalle de una liquidación (el panel lo pide si la fila no está en la página actual). */
export function useSettlement(id: string | null, initial?: CommissionSettlement) {
  return useQuery({
    queryKey: commissionKeys.settlement(id ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/commission-settlements/{settlement_id}", {
            params: { path: { settlement_id: id ?? "" } },
          }),
        )
      ).data,
    initialData: initial,
    enabled: !!id,
  });
}

/**
 * Ids de las solicitudes con una liquidación vigente (hasta 100): el modal "Liquidar a
 * mano" las marca como ya liquidadas. Si hay más, la API igual responde la existente
 * (`200`) sin crear otra.
 */
export function useActiveSettlementApplicationIds(enabled: boolean) {
  return useQuery({
    queryKey: commissionKeys.active,
    queryFn: async () => {
      const { data } = await call(
        api.GET("/api/v1/commission-settlements", {
          params: { query: { status: "ACTIVE", page_size: MAX_PAGE_SIZE } },
        }),
      );
      return new Set(data.items.map((s) => s.application.id));
    },
    enabled,
  });
}

/** Al cambiar una liquidación: el detalle queda con la respuesta y los listados se piden de nuevo. */
function useSettlementChanged() {
  const queryClient = useQueryClient();
  return (settlement: CommissionSettlement) => {
    queryClient.setQueryData(commissionKeys.settlement(settlement.id), settlement);
    void queryClient.invalidateQueries({ queryKey: ["commissions", "settlements"] });
    void queryClient.invalidateQueries({
      queryKey: commissionKeys.ofApplication(settlement.application.id),
    });
    void queryClient.invalidateQueries({ queryKey: ["commissions", "mine"] });
  };
}

/** Pagar una parte (`POST /commission-shares/{id}/pay`): responde la liquidación completa. */
export function usePayShare() {
  const changed = useSettlementChanged();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, body, key }: { id: string; body: SharePayRequest; key: string }) =>
      (
        await call(
          api.POST("/api/v1/commission-shares/{share_id}/pay", {
            params: { path: { share_id: id }, header: { "Idempotency-Key": key } },
            body,
          }),
        )
      ).data,
    onSuccess: changed,
  });
}

export function useVoidSettlement() {
  const changed = useSettlementChanged();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, reason, key }: { id: string; reason: string; key: string }) =>
      (
        await call(
          api.POST("/api/v1/commission-settlements/{settlement_id}/void", {
            params: { path: { settlement_id: id }, header: { "Idempotency-Key": key } },
            body: { reason },
          }),
        )
      ).data,
    onSuccess: changed,
  });
}

/**
 * Liquidar a mano una solicitud desembolsada. `created` es `false` cuando la API devolvió
 * la liquidación vigente que ya existía (`200`).
 */
export function useSettleApplication() {
  const changed = useSettlementChanged();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ applicationId, key }: { applicationId: string; key: string }) => {
      const { data, response } = await call(
        api.POST("/api/v1/applications/{application_id}/commission-settlement", {
          params: { path: { application_id: applicationId }, header: { "Idempotency-Key": key } },
        }),
      );
      return { settlement: data, created: response.status === 201 };
    },
    onSuccess: ({ settlement }) => {
      changed(settlement);
      void queryClient.invalidateQueries({ queryKey: commissionKeys.active });
    },
  });
}

/**
 * Solicitudes desembolsadas para "Liquidar a mano", con búsqueda (código, nombre, cédula).
 * Liquida el administrador: recibe la página de `Application`, no la del broker (`oneOf`).
 */
export function useDisbursedApplications(search: string, enabled: boolean) {
  return useQuery({
    queryKey: ["applications", "disbursed", search],
    queryFn: async () =>
      (
        (
          await call(
            api.GET("/api/v1/applications", {
              params: {
                query: { status: DISBURSED, page_size: 20, ...(search ? { search } : {}) },
              },
            }),
          )
        ).data as Schemas["PaginatedApplicationList"]
      ).items,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Brokers activos para el filtro (pide `users.read`). */
export function useBrokers(enabled: boolean) {
  return useQuery({
    queryKey: ["users", "brokers", "active"],
    queryFn: async () => {
      const { data } = await call(
        api.GET("/api/v1/users", {
          params: { query: { role: BROKER_ROLE, status: "ACTIVE", page_size: MAX_PAGE_SIZE } },
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

/** Fecha (AAAA-MM-DD) de Bogotá de un instante. */
export function bogotaDate(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

/**
 * La liquidación de una solicitud, para la tarjeta "Comisión" del expediente
 * (`application_id`: su historial, la vigente y las anuladas). La vigente gana sobre una
 * anulada; si no hay vigente, la más reciente. `null`: no tiene.
 */
export function useApplicationSettlement(applicationId: string, enabled: boolean) {
  return useQuery({
    queryKey: commissionKeys.ofApplication(applicationId),
    queryFn: async (): Promise<CommissionSettlement | null> => {
      const { data } = await call(
        api.GET("/api/v1/commission-settlements", {
          params: { query: { application_id: applicationId, page_size: MAX_PAGE_SIZE } },
        }),
      );
      return data.items.find((s) => s.status === "ACTIVE") ?? data.items[0] ?? null;
    },
    enabled,
  });
}

// ---------- planes ----------

export function usePlans(params: PlanParams, enabled = true) {
  const query = plansQuery(params);
  return useQuery({
    queryKey: commissionKeys.plans(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/commission-plans", { params: { query } }))).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Productos bancarios para el plan (pide `banks.read`). */
export function useBankProducts(enabled: boolean) {
  return useQuery({
    queryKey: ["bank-products", "all"],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/bank-products", {
            params: { query: { ordering: "name", page_size: MAX_PAGE_SIZE } },
          }),
        )
      ).data.items,
    staleTime: 5 * 60_000,
    enabled,
  });
}

function usePlansChanged() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["commissions", "plans"] });
}

export function useCreatePlan() {
  const changed = usePlansChanged();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: PlanCreateRequest) =>
      (await call(api.POST("/api/v1/commission-plans", { body }))).data,
    onSuccess: changed,
  });
}

/** Editar un plan sin uso, con `If-Match` (la versión del plan). */
export function useUpdatePlan() {
  const changed = usePlansChanged();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({
      id,
      version,
      body,
    }: {
      id: string;
      version: number;
      body: PlanUpdateRequest;
    }) =>
      (
        await call(
          api.PATCH("/api/v1/commission-plans/{plan_id}", {
            params: { path: { plan_id: id }, header: { "If-Match": ifMatch(version) } },
            body,
          }),
        )
      ).data,
    onSuccess: changed,
  });
}

export function useClosePlan() {
  const changed = usePlansChanged();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ id, validUntil }: { id: string; validUntil: string }) =>
      (
        await call(
          api.POST("/api/v1/commission-plans/{plan_id}/close", {
            params: { path: { plan_id: id } },
            body: { valid_until: validUntil },
          }),
        )
      ).data,
    onSuccess: changed,
  });
}

// ---------- mis comisiones ----------

export function useMyCommissions(params: MyCommissionParams) {
  const query = myCommissionsQuery(params);
  return useQuery({
    queryKey: commissionKeys.mine(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/me/commissions", { params: { query } }))).data,
    placeholderData: keepPreviousData,
  });
}
