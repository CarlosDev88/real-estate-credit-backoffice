"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { compact } from "@/features/admin-common/list-params";
import type { ParticipantRole } from "@/features/admin-documents/labels";
import { GENERAL, type DocumentsParams } from "@/features/admin-documents/list-params";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type DocumentType = Schemas["DocumentType"];
export type DocumentTypePage = Schemas["PaginatedDocumentTypeList"];
export type DocumentTypeCreateRequest = Schemas["DocumentTypeCreateRequest"];
export type DocumentTypeUpdateRequest = Schemas["PatchedDocumentTypeUpdateRequest"];
export type Requirement = Schemas["DocumentRequirement"];
export type RequirementPage = Schemas["PaginatedDocumentRequirementList"];
export type RequirementCreateRequest = Schemas["DocumentRequirementCreateRequest"];
export type RequirementUpdateRequest = Schemas["PatchedDocumentRequirementUpdateRequest"];
export type PreviewRequest = Schemas["ChecklistPreviewRequestRequest"];
export type PreviewResponse = Schemas["ChecklistPreviewResponse"];
export type BankProductOption = Schemas["BankProduct"];

export const documentKeys = {
  all: ["admin-documents"] as const,
  types: ["admin-documents", "types"] as const,
  typeList: (query: object) => ["admin-documents", "types", "list", query] as const,
  type: (id: string) => ["admin-documents", "types", "detail", id] as const,
  typeOptions: ["admin-documents", "types", "options"] as const,
  requirements: ["admin-documents", "requirements"] as const,
  requirementList: (query: object) => ["admin-documents", "requirements", "list", query] as const,
  requirement: (id: string) => ["admin-documents", "requirements", "detail", id] as const,
  products: ["admin-documents", "products"] as const,
};

const MAX_PAGE_SIZE = 100;

// ---------- tipos ----------

export function useDocumentTypes(params: DocumentsParams, enabled: boolean) {
  const query = {
    search: params.search,
    is_active: params.active === "" ? undefined : params.active === "true",
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: documentKeys.typeList(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/document-types", { params: { query: compact(query) } })))
        .data as DocumentTypePage,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Todos los tipos (hasta 100), para los selectores de requisitos. */
export function useDocumentTypeOptions(enabled = true) {
  return useQuery({
    queryKey: documentKeys.typeOptions,
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-types", {
            params: { query: { ordering: "name", page_size: MAX_PAGE_SIZE } },
          }),
        )
      ).data.items as DocumentType[],
    staleTime: 60_000,
    enabled,
  });
}

export function useDocumentType(id: string) {
  return useQuery({
    queryKey: documentKeys.type(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-types/{document_type_id}", {
            params: { path: { document_type_id: id } },
          }),
        )
      ).data as DocumentType,
    enabled: id !== "",
  });
}

function useSaveType() {
  const queryClient = useQueryClient();
  return (type: DocumentType) => {
    queryClient.setQueryData(documentKeys.type(type.id), type);
    // Los requisitos muestran el nombre y el estado del tipo.
    return queryClient.invalidateQueries({ queryKey: documentKeys.all });
  };
}

export function useCreateDocumentType() {
  const save = useSaveType();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: DocumentTypeCreateRequest) =>
      (await call(api.POST("/api/v1/document-types", { body }))).data as DocumentType,
    onSuccess: save,
  });
}

export function useUpdateDocumentType(id: string) {
  const save = useSaveType();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: DocumentTypeUpdateRequest) =>
      (
        await call(
          api.PATCH("/api/v1/document-types/{document_type_id}", {
            params: { path: { document_type_id: id } },
            body,
          }),
        )
      ).data as DocumentType,
    onSuccess: save,
  });
}

export function useSetDocumentTypeActive(id: string) {
  const save = useSaveType();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ active, reason }: { active: boolean; reason: string }) => {
      const options = {
        params: { path: { document_type_id: id } },
        body: reason ? { reason } : {},
      };
      return (
        active
          ? (await call(api.POST("/api/v1/document-types/{document_type_id}/activate", options)))
              .data
          : (await call(api.POST("/api/v1/document-types/{document_type_id}/deactivate", options)))
              .data
      ) as DocumentType;
    },
    onSuccess: save,
  });
}

// ---------- productos (selectores) ----------

/** Productos bancarios (hasta 100) para elegir el alcance de un requisito o la vista previa. */
export function useProductOptions(enabled = true) {
  return useQuery({
    queryKey: documentKeys.products,
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/bank-products", { params: { query: { page_size: MAX_PAGE_SIZE } } }),
        )
      ).data.items as BankProductOption[],
    staleTime: 60_000,
    enabled,
  });
}

export const productOptionLabel = (product: {
  name: string;
  bank: { name: string; short_name: string };
}) => `${product.bank.short_name || product.bank.name} · ${product.name}`;

// ---------- requisitos ----------

export function useRequirements(params: DocumentsParams, enabled: boolean) {
  const query = {
    status: (params.status || undefined) as "ACTIVE" | "DRAFT" | "INACTIVE" | undefined,
    bank_product_id: params.product && params.product !== GENERAL ? params.product : undefined,
    general: params.product === GENERAL ? true : undefined,
    document_type_id: params.doc_type,
    purpose: params.purpose,
    participant_role: (params.role || undefined) as ParticipantRole | undefined,
    ordering: params.ordering,
    page: params.page,
    page_size: params.page_size,
  };
  return useQuery({
    queryKey: documentKeys.requirementList(query),
    queryFn: async () =>
      (await call(api.GET("/api/v1/document-requirements", { params: { query: compact(query) } })))
        .data as RequirementPage,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useRequirement(id: string) {
  return useQuery({
    queryKey: documentKeys.requirement(id),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-requirements/{requirement_id}", {
            params: { path: { requirement_id: id } },
          }),
        )
      ).data as Requirement,
    enabled: id !== "",
  });
}

function useSaveRequirement() {
  const queryClient = useQueryClient();
  return (requirement: Requirement) => {
    queryClient.setQueryData(documentKeys.requirement(requirement.id), requirement);
    return queryClient.invalidateQueries({ queryKey: documentKeys.requirements });
  };
}

export function useCreateRequirement() {
  const save = useSaveRequirement();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: RequirementCreateRequest) =>
      (await call(api.POST("/api/v1/document-requirements", { body }))).data as Requirement,
    onSuccess: save,
  });
}

/** Un borrador se edita (`200`); una versión publicada crea un borrador nuevo (`201`). */
export function useUpdateRequirement(id: string) {
  const save = useSaveRequirement();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: RequirementUpdateRequest) => {
      const result = await call(
        api.PATCH("/api/v1/document-requirements/{requirement_id}", {
          params: { path: { requirement_id: id } },
          body,
        }),
      );
      return {
        requirement: result.data as Requirement,
        newVersion: result.response.status === 201,
      };
    },
    onSuccess: ({ requirement }) => save(requirement),
  });
}

export function useSetRequirementActive(id: string) {
  const save = useSaveRequirement();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (active: boolean) => {
      const options = { params: { path: { requirement_id: id } } };
      return (
        active
          ? (
              await call(
                api.POST("/api/v1/document-requirements/{requirement_id}/activate", options),
              )
            ).data
          : (
              await call(
                api.POST("/api/v1/document-requirements/{requirement_id}/deactivate", options),
              )
            ).data
      ) as Requirement;
    },
    onSuccess: save,
  });
}

/** `POST /document-requirements/preview`: qué checklist saldría para un caso. */
export function usePreviewChecklist() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: PreviewRequest) =>
      (await call(api.POST("/api/v1/document-requirements/preview", { body })))
        .data as PreviewResponse,
  });
}
