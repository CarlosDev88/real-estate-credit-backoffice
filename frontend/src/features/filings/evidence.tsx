"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Button, Modal } from "antd";
import { useCallback, useState } from "react";

import { DocumentUploader, type UploadContext } from "@/components/ui/document-uploader";
import { DocumentViewer, type ViewerFile } from "@/components/ui/document-viewer";
import {
  evidencePath,
  responseKeys,
  useEvidenceDownload,
  type FilingResponse,
} from "@/features/filings/queries";
import { isApiError } from "@/lib/api/errors";
import { uploadFile } from "@/lib/api/upload";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Límites de la evidencia (API §20.2): PDF, JPG o PNG de hasta 10 MB. */
export const EVIDENCE_TYPES = ["application/pdf", "image/jpeg", "image/png"] as const;
export const EVIDENCE_MAX_BYTES = 10 * 1024 * 1024;

/**
 * Adjunta la evidencia de una respuesta (una sola vez). Se abre al registrar la respuesta,
 * como paso opcional, o después desde la respuesta si todavía no tiene.
 */
export function EvidenceModal({
  response,
  onClose,
}: {
  response: FilingResponse | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const upload = async (file: File, context: UploadContext) => {
    if (!response) return;
    await uploadFile({ path: evidencePath(response.id), file, ...context });
    await queryClient.invalidateQueries({ queryKey: responseKeys.list(response.filing_id) });
    toast.success({ title: "Evidencia adjunta", message: file.name });
    onClose();
  };

  return (
    <Modal
      open={!!response}
      title="Adjuntar evidencia"
      onCancel={onClose}
      footer={<Button onClick={onClose}>Ahora no</Button>}
      destroyOnHidden
    >
      <div className="grid gap-3 pt-2">
        <p className="text-text-secondary m-0 text-sm">
          Opcional: el correo, la carta o la captura con la respuesta del banco
          {response ? ` (${response.response_type_label.toLocaleLowerCase("es-CO")})` : ""}. Se
          adjunta una sola vez.
        </p>
        <DocumentUploader onUpload={upload} accept={EVIDENCE_TYPES} maxBytes={EVIDENCE_MAX_BYTES} />
      </div>
    </Modal>
  );
}

function viewerKind(mimeType: string): ViewerFile["kind"] {
  return mimeType.startsWith("image/") ? "image" : "pdf";
}

/** "Ver evidencia": pide la URL firmada cada vez y la abre en el visor de documentos. */
export function useEvidenceViewer() {
  const download = useEvidenceDownload();
  const [file, setFile] = useState<(ViewerFile & { expiresAt: string }) | null>(null);
  const [failed, setFailed] = useState<{ id: string; message: string } | null>(null);

  const show = useCallback(
    (response: FilingResponse) => {
      const evidence = response.evidence;
      if (!evidence) return;
      setFailed(null);
      download.mutate(response.id, {
        onSuccess: ({ url, expires_at }) => {
          const size = formatBytes(evidence.size_bytes);
          setFile({
            name: evidence.filename,
            kind: viewerKind(evidence.mime_type),
            url,
            expiresAt: expires_at,
            ...(size ? { size } : {}),
          });
        },
        onError: (error) =>
          setFailed({
            id: response.id,
            message: isApiError(error) ? error.message : "No se pudo abrir la evidencia.",
          }),
      });
    },
    [download],
  );

  const errorFor = (id: string) => (failed?.id === id ? failed.message : null);
  const loadingFor = (id: string) => download.isPending && download.variables === id;

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
