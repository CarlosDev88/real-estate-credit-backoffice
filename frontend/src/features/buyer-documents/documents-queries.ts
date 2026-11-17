"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { buyerKeys, type BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { api, call } from "@/lib/api/client";
import { ApiError, isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { uploadFile } from "@/lib/api/upload";

export type BuyerDocumentVersion = components["schemas"]["BuyerDocumentVersion"];

export const documentKeys = {
  versions: (id: string, slotId: string) => ["buyer", id, "versions", slotId] as const,
};

/** Versiones de un documento, de la más reciente a la primera. Se piden al abrirlas. */
export function useSlotVersions(applicationId: string, slotId: string, enabled: boolean) {
  return useQuery({
    queryKey: documentKeys.versions(applicationId, slotId),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/buyer/document-slots/{slot_id}/versions", {
            params: { path: { slot_id: slotId }, query: { page_size: 100 } },
          }),
        )
      ).data.items,
    enabled,
  });
}

/**
 * URL prefirmada de un archivo del comprador. Se pide cada vez que se abre el visor y
 * no se guarda: es una credencial de pocos minutos. Sus errores se muestran en línea.
 */
export function useBuyerDownload() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (fileId: string) =>
      (
        await call(
          api.GET("/api/v1/buyer/document-files/{file_id}/download", {
            params: { path: { file_id: fileId } },
          }),
        )
      ).data,
  });
}

export interface UploadInput {
  slotId: string;
  file: File;
  documentDate?: string | null;
  onProgress: (percent: number) => void;
  signal: AbortSignal;
}

/**
 * Carga con `uploadFile` (progreso y cancelar). Un `413` del servidor web llega sin el
 * formato de la API: se le da un mensaje propio para que no quede el genérico.
 */
export async function uploadSlotFile({
  slotId,
  file,
  documentDate,
  onProgress,
  signal,
}: UploadInput) {
  try {
    return await uploadFile<BuyerDocumentSlot>({
      path: `/api/v1/buyer/document-slots/${slotId}/uploads`,
      file,
      fields: documentDate ? { document_date: documentDate } : undefined,
      onProgress,
      signal,
    });
  } catch (error) {
    if (isApiError(error) && error.status === 413 && error.code === "HTTP_413") {
      throw new ApiError(
        413,
        "PAYLOAD_TOO_LARGE",
        "El archivo es demasiado grande para subirlo.",
        [],
        error.requestId,
      );
    }
    throw error;
  }
}

/** Después de una carga: slots, detalle (progreso) y versiones se vuelven a pedir. */
export function useAfterUpload(applicationId: string) {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({
      queryKey: buyerKeys.all,
      predicate: (query) => query.queryKey[1] === applicationId && query.queryKey[2] !== "version",
    });
}
