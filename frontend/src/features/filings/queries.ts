"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { applicationKeys } from "@/features/applications/queries";
import { workspaceKeys } from "@/features/applications/workspace-queries";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type Filing = Schemas["Filing"];
export type FilingCreateRequest = Schemas["FilingCreateRequest"];
export type FilingUpdateRequest = Schemas["PatchedFilingUpdateRequest"];
export type FilingSnapshot = Schemas["FilingDocumentSnapshot"];
export type PackageJob = Schemas["DocumentPackageJob"];

/** La API pagina de a 100 como máximo; una solicitud no llega a tantas radicaciones. */
const PAGE_SIZE = 100;
/** Mientras el paquete no termina, se consulta cada 3 s (spec, parte 1). */
export const PACKAGE_POLL_MS = 3000;
/** Estados del trabajo que todavía no terminan (API §19.2). */
const PACKAGE_RUNNING = new Set(["PENDING", "RUNNING"]);
export const PACKAGE_COMPLETED = "COMPLETED";

export function isPackageRunning(job: PackageJob | undefined): boolean {
  return !!job && PACKAGE_RUNNING.has(job.status);
}

export const filingKeys = {
  /** Cuelgan del expediente: se invalidan con todo lo demás de la solicitud. */
  list: (applicationId: string) => [...workspaceKeys.all(applicationId), "filings"] as const,
  snapshots: (filingId: string) => ["filing", filingId, "snapshots"] as const,
  packageJob: (jobId: string) => ["document-package-job", jobId] as const,
  packageJobs: (applicationId: string) =>
    [...workspaceKeys.all(applicationId), "document-package-jobs"] as const,
};

/** Paquetes que se muestran en la pestaña (los más recientes). */
export const PACKAGES_PAGE_SIZE = 10;

/**
 * Paquetes pedidos para la solicitud, del más nuevo al más antiguo (`filings.prepare`).
 * Mientras alguno se arma, la lista se vuelve a pedir cada 3 s.
 */
export function usePackageJobs(applicationId: string, enabled: boolean) {
  return useQuery({
    queryKey: filingKeys.packageJobs(applicationId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/document-package-jobs", {
            params: {
              path: { application_id: applicationId },
              query: { page_size: PACKAGES_PAGE_SIZE },
            },
          }),
        )
      ).data,
    enabled,
    refetchInterval: (query) =>
      query.state.data?.items.some((job) => isPackageRunning(job)) ? PACKAGE_POLL_MS : false,
  });
}

/** Radicaciones de la solicitud, la más reciente primero (API §20.1). */
export function useFilings(applicationId: string, enabled = true) {
  return useQuery({
    queryKey: filingKeys.list(applicationId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/filings", {
            params: { path: { application_id: applicationId }, query: { page_size: PAGE_SIZE } },
          }),
        )
      ).data,
    enabled,
  });
}

/** Versiones exactas que se entregaron al banco; se piden al desplegar la lista. */
export function useFilingSnapshots(filingId: string, enabled: boolean) {
  return useQuery({
    queryKey: filingKeys.snapshots(filingId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/filings/{filing_id}/document-snapshots", {
            params: { path: { filing_id: filingId }, query: { page_size: PAGE_SIZE } },
          }),
        )
      ).data,
    enabled,
  });
}

/** Estado del paquete; mientras está pendiente o en proceso, se consulta cada 3 s. */
export function usePackageJob(jobId: string | null) {
  return useQuery({
    queryKey: filingKeys.packageJob(jobId ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-package-jobs/{job_id}", {
            params: { path: { job_id: jobId! } },
          }),
        )
      ).data,
    enabled: !!jobId,
    refetchInterval: (query) => (isPackageRunning(query.state.data) ? PACKAGE_POLL_MS : false),
  });
}

/**
 * Pide el paquete (`POST`, sin cuerpo). Si ya hay uno vivo con la misma huella, la API
 * responde ese (`200`). Sus errores (`422 APPLICATION_NOT_READY`, `409`) se muestran en
 * el panel, por eso maneja su propio error.
 */
export function useRequestPackage(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (key: string) =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/document-package-jobs", {
            params: {
              path: { application_id: applicationId },
              header: { "Idempotency-Key": key },
            },
          }),
        )
      ).data,
    onSuccess: (job) => {
      queryClient.setQueryData(filingKeys.packageJob(job.id), job);
      // Sin esperar la lista: el panel sigue con el paquete apenas responde el `POST`.
      void queryClient.invalidateQueries({ queryKey: filingKeys.packageJobs(applicationId) });
    },
  });
}

/**
 * URL firmada del ZIP. Se pide cada vez y no se guarda: es una credencial de pocos
 * minutos. Los errores (`409 PACKAGE_EXPIRED`, `429`, `503`) se muestran en el panel.
 */
export function usePackageDownload() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (jobId: string) =>
      (
        await call(
          api.GET("/api/v1/document-package-jobs/{job_id}/download", {
            params: { path: { job_id: jobId } },
          }),
        )
      ).data,
  });
}

/** Lo que cambia al radicar: estado, etapas, completitud, radicaciones e historial. */
function useInvalidateApplication(applicationId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all(applicationId) }),
      queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
    ]);
}

/** Registra la radicación con `expected_version`. Los errores los maneja el formulario. */
export function useCreateFiling(applicationId: string) {
  const invalidate = useInvalidateApplication(applicationId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: FilingCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/applications/{application_id}/filings", {
            params: { path: { application_id: applicationId } },
            body,
          }),
        )
      ).data,
    // Sin esperar la recarga: con la solicitud en `FILED` el panel "Entregar al banco" (y su
    // modal) se desmonta, y los callbacks de `mutate` (toast, limpiar el paquete) no correrían.
    onSuccess: () => {
      void invalidate();
    },
  });
}

/** Corrige referencia o comentario. No cambia la versión de la solicitud (API §20.1). */
export function useUpdateFiling(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ filingId, body }: { filingId: string; body: FilingUpdateRequest }) =>
      (
        await call(
          api.PATCH("/api/v1/filings/{filing_id}", {
            params: { path: { filing_id: filingId } },
            body,
          }),
        )
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: filingKeys.list(applicationId) }),
  });
}

// ---------- respuestas del banco (parte 2) ----------

export type FilingResponse = Schemas["FilingResponse"];
export type FilingResponseCreateRequest = Schemas["FilingResponseCreateRequest"];
export type ObservationInput = Schemas["ObservationInputRequest"];

/** Evidencia que todavía se analiza: mientras tanto, la línea de tiempo se vuelve a leer. */
export const EVIDENCE_SCAN_PENDING = "PENDING";
export const EVIDENCE_SCAN_CLEAN = "CLEAN";

export const responseKeys = {
  list: (filingId: string) => ["filing", filingId, "responses"] as const,
};

/** Respuestas de una radicación, en orden cronológico (incluidas las correcciones). */
export function useFilingResponses(filingId: string | undefined) {
  return useQuery({
    queryKey: responseKeys.list(filingId ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/filings/{filing_id}/responses", {
            params: { path: { filing_id: filingId! }, query: { page_size: PAGE_SIZE } },
          }),
        )
      ).data.items,
    enabled: !!filingId,
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.evidence?.scan_status === EVIDENCE_SCAN_PENDING)
        ? PACKAGE_POLL_MS
        : false,
  });
}

/**
 * Una respuesta cambia el estado de la solicitud y, si es una devolución, rechaza las
 * versiones observadas: se refresca todo el expediente (estado, etapas, documentos,
 * radicaciones e historial).
 */
function useInvalidateAfterResponse(applicationId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: workspaceKeys.all(applicationId) }),
      queryClient.invalidateQueries({ queryKey: ["filing"] }),
      queryClient.invalidateQueries({ queryKey: ["document-file"] }),
      queryClient.invalidateQueries({ queryKey: ["document-slot"] }),
      queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
    ]);
}

/** Registra una respuesta del banco con `expected_version`. Los errores los maneja el formulario. */
export function useRecordResponse(applicationId: string, filingId: string) {
  const invalidate = useInvalidateAfterResponse(applicationId);
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: FilingResponseCreateRequest) =>
      (
        await call(
          api.POST("/api/v1/filings/{filing_id}/responses", {
            params: { path: { filing_id: filingId } },
            body,
          }),
        )
      ).data,
    onSuccess: invalidate,
  });
}

/** Ruta de la carga de evidencia, para `uploadFile` (multipart, con progreso). */
export const evidencePath = (responseId: string) =>
  `/api/v1/filing-responses/${responseId}/evidence`;

/** URL firmada de la evidencia: se pide cada vez y no va a la caché. */
export function useEvidenceDownload() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (responseId: string) =>
      (
        await call(
          api.GET("/api/v1/filing-responses/{response_id}/evidence/download", {
            params: { path: { response_id: responseId } },
          }),
        )
      ).data,
  });
}
