"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Modal, Select } from "antd";
import { useCallback, useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { DocumentViewer, type ViewerFile } from "@/components/ui/document-viewer";
import { FormField, useFormErrorHandler } from "@/features/applications/form-field";
import { useCatalog } from "@/features/applications/queries";
import {
  useDownloadUrl,
  useReviewSlot,
  type DocumentSlot,
} from "@/features/document-review/queries";
import { viewerKind } from "@/features/document-review/slot-rules";
import { isApiError } from "@/lib/api/errors";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

// ---------- visor ----------

export interface ViewTarget {
  fileId: string;
  name: string;
  mimeType?: string | null | undefined;
  sizeBytes?: number | null | undefined;
}

/**
 * Abre el `DocumentViewer` con una URL que se pide en el momento (nunca se guarda). Si
 * la descarga no está disponible (`409`, `503`…), el error queda para mostrarlo en línea
 * junto al archivo, sin romper la pantalla.
 */
export function useFileViewer() {
  const download = useDownloadUrl();
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
            message: isApiError(error) ? error.message : "No se pudo abrir el archivo.",
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

// ---------- exonerar ----------

const waiveSchema = z.object({
  reason_code: z.string().min(1, { error: "Elige el motivo." }),
  internal_comment: z.string(),
});
type WaiveValues = z.infer<typeof waiveSchema>;
const WAIVE_FIELDS = ["reason_code", "internal_comment"] as const;

interface SlotDialogProps {
  applicationId: string;
  slot: DocumentSlot | null;
  onClose: () => void;
}

export function WaiveModal({ applicationId, slot, onClose }: SlotDialogProps) {
  const ids = useId();
  const toast = useToast();
  const review = useReviewSlot(applicationId);
  const reasons = useCatalog("document_waiver_reason");
  const { control, handleSubmit, setError, reset, formState } = useForm<WaiveValues>({
    resolver: zodResolver(waiveSchema),
    defaultValues: { reason_code: "", internal_comment: "" },
  });
  const onError = useFormErrorHandler<WaiveValues>(setError, WAIVE_FIELDS);

  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit((values) => {
    if (!slot) return;
    review.mutate(
      {
        slotId: slot.id,
        body: {
          decision: "WAIVED",
          reason_code: values.reason_code,
          ...(values.internal_comment.trim()
            ? { internal_comment: values.internal_comment.trim() }
            : {}),
        },
      },
      {
        onSuccess: () => {
          toast.success({ title: `${slot.label}: exonerado` });
          close();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={slot !== null}
      title={slot ? `Exonerar · ${slot.label}` : undefined}
      onCancel={close}
      okText="Exonerar"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={review.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField
          id={`${ids}-reason`}
          label="Motivo"
          error={formState.errors.reason_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="reason_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige un motivo"
                  options={reasons.items.map((i) => ({ value: i.code, label: i.label }))}
                  loading={reasons.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-note`}
          label="Nota interna"
          optional="opcional, el comprador no la ve"
          error={formState.errors.internal_comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="internal_comment"
              render={({ field }) => <Input.TextArea {...field} {...ctl} rows={3} />}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

// ---------- reabrir ----------

const reopenSchema = z.object({
  internal_comment: z.string().trim().min(1, { error: "Explica por qué se reabre." }),
});
type ReopenValues = z.infer<typeof reopenSchema>;
const REOPEN_FIELDS = ["internal_comment"] as const;

export function ReopenModal({ applicationId, slot, onClose }: SlotDialogProps) {
  const ids = useId();
  const toast = useToast();
  const review = useReviewSlot(applicationId);
  const { control, handleSubmit, setError, reset, formState } = useForm<ReopenValues>({
    resolver: zodResolver(reopenSchema),
    defaultValues: { internal_comment: "" },
  });
  const onError = useFormErrorHandler<ReopenValues>(setError, REOPEN_FIELDS);

  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit((values) => {
    if (!slot) return;
    review.mutate(
      {
        slotId: slot.id,
        body: { decision: "REOPENED", internal_comment: values.internal_comment.trim() },
      },
      {
        onSuccess: () => {
          toast.success({ title: `${slot.label}: reabierto` });
          close();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={slot !== null}
      title={slot ? `Reabrir · ${slot.label}` : undefined}
      onCancel={close}
      okText="Reabrir"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={review.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <p className="text-text-secondary m-0 text-sm">
          Se deshace la exoneración: el documento vuelve a quedar pendiente o por revisar.
        </p>
        <FormField
          id={`${ids}-note`}
          label="Nota interna"
          help="El comprador no la ve."
          error={formState.errors.internal_comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="internal_comment"
              render={({ field }) => <Input.TextArea {...field} {...ctl} rows={3} />}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}
