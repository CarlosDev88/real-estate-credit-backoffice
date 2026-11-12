"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { applicationKeys } from "@/features/applications/queries";
import { workspaceKeys } from "@/features/applications/workspace-queries";
import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
export type DocumentSlot = Schemas["DocumentSlot"];
export type DocumentFile = Schemas["DocumentFile"];
export type ReviewRequest = Schemas["PatchedDocumentSlotReviewRequest"];

export const documentKeys = {
  slots: (applicationId: string) => [...workspaceKeys.all(applicationId), "slots"] as const,
  file: (fileId: string) => ["document-file", fileId] as const,
  scan: (fileId: string) => ["document-file", fileId, "scan"] as const,
  versions: (slotId: string) => ["document-slot", slotId, "versions"] as const,
};

/** Estado del análisis que todavía corre (API §19.1). Mientras tanto se vuelve a consultar. */
export const SCAN_PENDING = "PENDING";
/** Único análisis que deja ver y aprobar el archivo. */
export const SCAN_CLEAN = "CLEAN";
const SCAN_POLL_MS = 3000;

/** Slots vigentes de la solicitud (la API ya excluye los retirados; se filtran igual). */
export function useDocumentSlots(applicationId: string) {
  return useQuery({
    queryKey: documentKeys.slots(applicationId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/applications/{application_id}/document-slots", {
            params: { path: { application_id: applicationId }, query: { page_size: 100 } },
          }),
        )
      ).data.items.filter((slot) => !slot.is_retired),
  });
}

async function fetchFile(fileId: string) {
  return (
    await call(
      api.GET("/api/v1/document-files/{file_id}", { params: { path: { file_id: fileId } } }),
    )
  ).data;
}

/**
 * Detalle de la versión vigente de cada slot: tamaño, tipo y la última revisión (el
 * mensaje al comprador de un rechazo). La lista de slots no los trae (ver "Brechas").
 */
export function useCurrentFiles(slots: DocumentSlot[] | undefined) {
  const ids = (slots ?? []).flatMap((s) => (s.current_file ? [s.current_file.id] : []));
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: documentKeys.file(id),
      queryFn: () => fetchFile(id),
      staleTime: 60_000,
    })),
  });
  const files = new Map<string, DocumentFile>();
  ids.forEach((id, i) => {
    const data = results[i]?.data;
    if (data) files.set(id, data);
  });
  return files;
}

export function useDocumentFile(fileId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.file(fileId ?? ""),
    queryFn: () => fetchFile(fileId!),
    enabled: !!fileId,
  });
}

/** Análisis antivirus; mientras está `PENDING`, se consulta cada 3 s. */
export function useScanStatus(fileId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.scan(fileId ?? ""),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-files/{file_id}/scan-status", {
            params: { path: { file_id: fileId! } },
          }),
        )
      ).data,
    enabled: !!fileId,
    refetchInterval: (query) =>
      query.state.data?.scan_status === SCAN_PENDING ? SCAN_POLL_MS : false,
  });
}

export function useSlotVersions(slotId: string, enabled: boolean) {
  return useQuery({
    queryKey: documentKeys.versions(slotId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/document-slots/{slot_id}/versions", {
            params: { path: { slot_id: slotId }, query: { page_size: 50 } },
          }),
        )
      ).data.items,
    enabled,
  });
}

/**
 * URL prefirmada de un archivo. Se pide cada vez que se abre el visor y no va a la caché:
 * es una credencial de pocos minutos (API §19.1). Sus errores (`409`, `503`) se muestran
 * en línea, por eso maneja su propio error.
 */
export function useDownloadUrl() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (fileId: string) =>
      (
        await call(
          api.GET("/api/v1/document-files/{file_id}/download", {
            params: { path: { file_id: fileId } },
          }),
        )
      ).data,
  });
}

/** Aprobar, rechazar, exonerar o reabrir. Refresca slots, completitud, detalle y archivos. */
export function useReviewSlot(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ slotId, body }: { slotId: string; body: ReviewRequest }) =>
      (
        await call(
          api.PATCH("/api/v1/document-slots/{slot_id}/review", {
            params: { path: { slot_id: slotId } },
            body,
          }),
        )
      ).data,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: workspaceKeys.all(applicationId) }),
        queryClient.invalidateQueries({ queryKey: ["document-file"] }),
        queryClient.invalidateQueries({ queryKey: ["document-slot"] }),
        queryClient.invalidateQueries({ queryKey: applicationKeys.all }),
      ]),
  });
}
