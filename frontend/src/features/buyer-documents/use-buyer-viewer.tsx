"use client";

import { useCallback, useState } from "react";

import { DocumentViewer, type ViewerFile } from "@/components/ui/document-viewer";
import { useBuyerDownload } from "@/features/buyer-documents/documents-queries";
import { viewerKind } from "@/features/buyer-documents/slot-format";
import { isApiError } from "@/lib/api/errors";
import { formatBytes, formatDateTime } from "@/lib/format";

export interface ViewTarget {
  fileId: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
}

/**
 * Abre el `DocumentViewer` con la URL de `GET /buyer/document-files/{id}/download`, pedida
 * en el momento. Si no se puede (`409 FILE_NOT_CLEAN`, `503`…), el error queda para
 * mostrarlo en línea junto al archivo.
 */
export function useBuyerViewer() {
  const download = useBuyerDownload();
  const [file, setFile] = useState<(ViewerFile & { expiresAt: string }) | null>(null);
  const [failed, setFailed] = useState<{ fileId: string; message: string } | null>(null);

  const show = useCallback(
    (target: ViewTarget) => {
      setFailed(null);
      download.mutate(target.fileId, {
        onSuccess: ({ url, expires_at }) => {
          const size = formatBytes(target.sizeBytes);
          setFile({
            name: target.name,
            kind: viewerKind(target.mimeType),
            url,
            expiresAt: expires_at,
            ...(size ? { size } : {}),
          });
        },
        onError: (error) =>
          setFailed({
            fileId: target.fileId,
            message: isApiError(error) ? error.message : "No pudimos abrir el archivo.",
          }),
      });
    },
    [download],
  );

  const errorFor = (fileId: string | undefined) =>
    fileId && failed?.fileId === fileId ? failed.message : null;
  const loadingFor = (fileId: string | undefined) =>
    download.isPending && download.variables === fileId;

  const viewer = (
    <DocumentViewer
      open={file !== null}
      file={file}
      onClose={() => setFile(null)}
      note={
        file ? `El enlace de descarga vence ${formatDateTime(file.expiresAt) ?? "pronto"}.` : null
      }
    />
  );
  return { show, errorFor, loadingFor, viewer };
}
