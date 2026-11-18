"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ActiveStatusCode } from "@/features/admin-common/active-status";
import { compact } from "@/features/admin-common/list-params";
import type { Severity } from "@/features/admin-banks/labels";
import type { BanksParams, RulesParams } from "@/features/admin-banks/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Bank = Schemas["Bank"];
export type BankDetail = Schemas["BankDetail"];
export type BankPage = Schemas["PaginatedBankList"];
export type BankCreateRequest = Schemas["BankCreateRequest"];
export type BankUpdateRequest = Schemas["PatchedBankUpdateRequest"];
export type BankProduct = Schemas["BankProduct"];
export type BankProductCreateRequest = Schemas["BankProductCreateRequest"];
export type BankProductUpdateRequest = Schemas["PatchedBankProductUpdateRequest"];
export type Rule = Schemas["BankPolicyRule"];
export type RulePage = Schemas["PaginatedBankPolicyRuleList"];
export type RuleCreateRequest = Schemas["BankPolicyRuleCreateRequest"];
export type RuleUpdateRequest = Schemas["PatchedBankPolicyRuleUpdateRequest"];
export type RuleTestRequest = Schemas["RuleTestRequestRequest"];
export type RuleTestResponse = Schemas["RuleTestResponse"];

export const bankKeys = {
  all: ["admin-banks"] as const,
  lists: ["admin-banks", "list"] as const,
  list: (query: object) => ["admin-banks", "list", query] as const,
  detail: (id: string) => ["admin-banks", "detail", id] as const,
  product: (id: string) => ["admin-banks", "product", id] as const,
  rules: ["admin-banks", "rules"] as const,
  ruleList: (query: object) => ["admin-banks", "rules", "list", query] as const,
  rule: (id: string) => ["admin-banks", "rules", "detail", id] as const,
  versions: (id: string) => ["admin-banks", "rules", "versions", id] as const,
};

/** Nombre para listados: el corto si lo tiene (contrato: `short_name` vacío → `name`). */
export const bankLabel = (bank: { name: string; short_name: string }) =>
  bank.short_name || bank.name;

// ---------- bancos ----------

export function useBanksList(params: BanksParams) {
  const query = {
    search: params.search,
    status: (params.status || undefined) as ActiveStatusCode | undefined,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: bankKeys.list(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/banks", { params: { query: compact(query) } })))
        .data as BankPage,
    placeholderData: keepPreviousData,
  });
}

/** `GET /banks/{id}`: datos y el resumen de sus productos. */
export function useBank(id: string) {
  return useQuery({
    queryKey: bankKeys.detail(id),
    queryFn: async () =>
      (await call(api.GET("/api/v1/banks/{bank_id}", { params: { path: { bank_id: id } } })))
        .data as BankDetail,
    enabled: id !== "",
  });
}

function useRefreshBanks() {
  const queryClient = useQueryClient();
  // Los bancos activos también llenan filtros de otras vistas (solicitudes).
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: bankKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["banks"] }),
    ]);
}

export function useCreateBank() {
  const refresh = useRefreshBanks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BankCreateRequest) =>
      (await call(api.POST("/api/v1/banks", { body }))).data as Bank,
    onSuccess: refresh,
  });
}

export function useUpdateBank(id: string) {
  const refresh = useRefreshBanks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BankUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/banks/{bank_id}", { params: { path: { bank_id: id } }, body }),
        )
      ).data as BankDetail,
    onSuccess: refresh,
  });
}

/** `POST /banks/{id}/activate` o `/deactivate` (motivo opcional en los dos). */
export function useSetBankActive(id: string) {
  const refresh = useRefreshBanks();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ active, reason }: { active: boolean; reason: string }) => {
      const options = { params: { path: { bank_id: id } }, body: reason ? { reason } : {} };
      return active
        ? (await call(api.POST("/api/v1/banks/{bank_id}/activate", options))).data
        : (await call(api.POST("/api/v1/banks/{bank_id}/deactivate", options))).data;
    },
    onSuccess: refresh,
  });
}

// ---------- productos ----------

export function useProduct(id: string) {
  return useQuery({
    queryKey: bankKeys.product(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/bank-products/{product_id}", {
            params: { path: { product_id: id } },
          }),
        )
      ).data as BankProduct,
    enabled: id !== "",
  });
}

function useSaveProduct() {
  const queryClient = useQueryClient();
  const refresh = useRefreshBanks();
  return (product: BankProduct) => {
    queryClient.setQueryData(bankKeys.product(product.id), product);
    return refresh();
  };
}

export function useCreateProduct() {
  const save = useSaveProduct();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BankProductCreateRequest) =>
      (await call(api.POST("/api/v1/bank-products", { body }))).data as BankProduct,
    onSuccess: save,
  });
}

export function useUpdateProduct(id: string) {
  const save = useSaveProduct();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: BankProductUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/bank-products/{product_id}", {
            params: { path: { product_id: id } },
            body,
          }),
        )
      ).data as BankProduct,
    onSuccess: save,
  });
}

export function useSetProductActive(id: string) {
  const save = useSaveProduct();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ active, reason }: { active: boolean; reason: string }) => {
      const options = { params: { path: { product_id: id } }, body: reason ? { reason } : {} };
      return (
        active
          ? (await call(api.POST("/api/v1/bank-products/{product_id}/activate", options))).data
          : (await call(api.POST("/api/v1/bank-products/{product_id}/deactivate", options))).data
      ) as BankProduct;
    },
    onSuccess: save,
  });
}

/** `PUT /bank-products/{id}/purposes`: las que salen de la lista se desactivan. */
export function useSetPurposes(id: string) {
  const save = useSaveProduct();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (purpose_codes: string[]) =>
      (
        await call(
          api.PUT("/api/v1/bank-products/{product_id}/purposes", {
            params: { path: { product_id: id } },
            body: { purpose_codes },
          }),
        )
      ).data as BankProduct,
    onSuccess: save,
  });
}

// ---------- reglas ----------

/** `GET /bank-policy-rules` de un producto, con los filtros de la URL. */
export function useRulesList(productId: string, params: RulesParams) {
  const query = {
    bank_product_id: productId,
    search: params.search,
    status: (params.status || undefined) as "ACTIVE" | "DRAFT" | "INACTIVE" | undefined,
    severity: (params.severity || undefined) as Severity | undefined,
    purpose: params.purpose,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: bankKeys.ruleList(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/bank-policy-rules", { params: { query: compact(query) } })))
        .data as RulePage,
    placeholderData: keepPreviousData,
  });
}

export function useRule(id: string) {
  return useQuery({
    queryKey: bankKeys.rule(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/bank-policy-rules/{rule_id}", { params: { path: { rule_id: id } } }),
        )
      ).data as Rule,
    enabled: id !== "",
  });
}

/** `GET /bank-policy-rules/{id}/versions`: todas las versiones del mismo código. */
export function useRuleVersions(id: string) {
  return useQuery({
    queryKey: bankKeys.versions(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/bank-policy-rules/{rule_id}/versions", {
            params: { path: { rule_id: id }, query: { page_size: 100 } },
          }),
        )
      ).data.items as Rule[],
    enabled: id !== "",
  });
}

function useRefreshRules() {
  const queryClient = useQueryClient();
  return (rule: Rule) => {
    queryClient.setQueryData(bankKeys.rule(rule.id), rule);
    return queryClient.invalidateQueries({ queryKey: bankKeys.rules });
  };
}

export function useCreateRule() {
  const refresh = useRefreshRules();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: RuleCreateRequest) =>
      (await call(api.POST("/api/v1/bank-policy-rules", { body }))).data as Rule,
    onSuccess: refresh,
  });
}

/**
 * `PATCH /bank-policy-rules/{id}`: un borrador se edita (`200`); una versión publicada no
 * cambia y nace un borrador nuevo (`201`, `newVersion: true`).
 */
export function useUpdateRule(id: string) {
  const refresh = useRefreshRules();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: RuleUpdateRequest) => {
      const result = await call(
        api.PATCH("/api/v1/bank-policy-rules/{rule_id}", {
          params: { path: { rule_id: id } },
          body,
        }),
      );
      return { rule: result.data as Rule, newVersion: result.response.status === 201 };
    },
    onSuccess: ({ rule }) => refresh(rule),
  });
}

/** Publicar (`activate`: la versión activa anterior pasa a inactiva) o desactivar. */
export function useSetRuleActive(id: string) {
  const refresh = useRefreshRules();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (active: boolean) => {
      const options = { params: { path: { rule_id: id } } };
      return (
        active
          ? (await call(api.POST("/api/v1/bank-policy-rules/{rule_id}/activate", options))).data
          : (await call(api.POST("/api/v1/bank-policy-rules/{rule_id}/deactivate", options))).data
      ) as Rule;
    },
    onSuccess: refresh,
  });
}

/** `POST /bank-policy-rules/{id}/test`: evalúa casos sin tocar solicitudes ni la regla. */
export function useTestRule(id: string) {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: RuleTestRequest) =>
      (
        await call(
          api.POST("/api/v1/bank-policy-rules/{rule_id}/test", {
            params: { path: { rule_id: id } },
            body,
          }),
        )
      ).data as RuleTestResponse,
  });
}
