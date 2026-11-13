"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Collapse, Drawer, Input, Radio, Select } from "antd";
import { useCallback, useId, useMemo, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { RelativeTime } from "@/components/ui/relative-time";
import { TONE_CLASS } from "@/components/ui/status-badge";
import { toneFor } from "@design/status-tones";
import { FormField, useFormErrorHandler } from "@/features/applications/form-field";
import { useCatalog } from "@/features/applications/queries";
import {
  useDocumentFile,
  useReviewSlot,
  useScanStatus,
  useSlotVersions,
  type DocumentFile,
  type DocumentSlot,
} from "@/features/document-review/queries";
import type { useFileViewer } from "@/features/document-review/slot-dialogs";
import {
  SCAN_FAILED_TEXT,
  SCAN_PENDING_TEXT,
  validityText,
} from "@/features/document-review/slot-rules";
import { formatBytes, formatDateOnly, formatDateTime } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useToast } from "@/providers/toast";
import { SCAN_CLEAN, SCAN_PENDING } from "@/features/document-review/queries";

type Viewer = ReturnType<typeof useFileViewer>;

const APPROVE = "APPROVED";
const REJECT = "REJECTED";

/** Hoy en Bogotá, "AAAA-MM-DD": tope de la fecha del documento (no puede ser futura). */
function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());
}

function ScanBadge({ scanStatus }: { scanStatus: string }) {
  const tone = toneFor("fileScan", scanStatus);
  // Mientras la API no traiga la etiqueta del análisis (ver "Brechas"), el texto es el
  // aviso que pide la spec; un archivo limpio dice que no se encontraron amenazas.
  const text =
    scanStatus === SCAN_CLEAN
      ? "Sin amenazas"
      : scanStatus === SCAN_PENDING
        ? SCAN_PENDING_TEXT
        : SCAN_FAILED_TEXT;
  return (
    <span
      data-tone={tone}
      className={`inline-flex min-h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      <span aria-hidden="true" className="size-1.5 flex-none rounded-full bg-current" />
      {text}
    </span>
  );
}

function buildSchema(requiresDate: boolean) {
  return z
    .object({
      decision: z.enum([APPROVE, REJECT]),
      document_date: z.string(),
      reason_code: z.string(),
      buyer_comment: z.string(),
      internal_comment: z.string(),
    })
    .superRefine((v, ctx) => {
      if (v.decision === APPROVE && requiresDate && !v.document_date) {
        ctx.addIssue({
          code: "custom",
          path: ["document_date"],
          message: "Escribe la fecha del documento.",
        });
      }
      if (v.decision === APPROVE && v.document_date && v.document_date > todayIso()) {
        ctx.addIssue({
          code: "custom",
          path: ["document_date"],
          message: "La fecha no puede ser futura.",
        });
      }
      if (v.decision === REJECT && !v.reason_code) {
        ctx.addIssue({ code: "custom", path: ["reason_code"], message: "Elige el motivo." });
      }
      if (v.decision === REJECT && !v.buyer_comment.trim()) {
        ctx.addIssue({
          code: "custom",
          path: ["buyer_comment"],
          message: "Explícale al comprador qué debe corregir.",
        });
      }
    });
}
type ReviewValues = z.infer<ReturnType<typeof buildSchema>>;
const REVIEW_FIELDS = [
  "document_date",
  "reason_code",
  "buyer_comment",
  "internal_comment",
] as const;

type Review = ReturnType<typeof useReviewSlot>;
type Decision = typeof APPROVE | typeof REJECT;

interface DecisionFormProps {
  review: Review;
  slot: DocumentSlot;
  file: DocumentFile;
  formId: string;
  onDecision: (decision: Decision) => void;
  onDone: () => void;
}

function DecisionForm({ review, slot, file, formId, onDecision, onDone }: DecisionFormProps) {
  const ids = useId();
  const toast = useToast();
  const reasons = useCatalog("document_rejection_reason");
  const requiresDate = slot.validity_days !== null;
  const schema = useMemo(() => buildSchema(requiresDate), [requiresDate]);
  const { control, handleSubmit, setError, formState } = useForm<ReviewValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      decision: APPROVE,
      document_date: file.document_date ?? "",
      reason_code: "",
      buyer_comment: "",
      internal_comment: "",
    },
  });
  const onError = useFormErrorHandler<ReviewValues>(setError, REVIEW_FIELDS);
  const decision = useWatch({ control, name: "decision" });

  const submit = handleSubmit((values) => {
    const note = values.internal_comment.trim();
    const body =
      values.decision === APPROVE
        ? {
            decision: APPROVE,
            document_file_id: file.id,
            ...(values.document_date ? { document_date: values.document_date } : {}),
            ...(note ? { internal_comment: note } : {}),
          }
        : {
            decision: REJECT,
            document_file_id: file.id,
            reason_code: values.reason_code,
            buyer_comment: values.buyer_comment.trim(),
            ...(note ? { internal_comment: note } : {}),
          };
    review.mutate(
      { slotId: slot.id, body: body as Parameters<typeof review.mutate>[0]["body"] },
      {
        onSuccess: () => {
          if (values.decision === APPROVE) toast.success({ title: `${slot.label}: aprobado` });
          else
            toast.warning({
              title: `${slot.label}: rechazado`,
              message: "El comprador ve el motivo y tu mensaje en su portal.",
            });
          onDone();
        },
        onError,
      },
    );
  });

  return (
    <form id={formId} noValidate onSubmit={(e) => void submit(e)} className="grid gap-5">
      {requiresDate && (
        <FormField
          id={`${ids}-date`}
          label="Fecha del documento"
          help={validityText(slot) ?? undefined}
          error={formState.errors.document_date?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="document_date"
              render={({ field }) => (
                <Input {...field} {...ctl} type="date" max={todayIso()} className="max-w-[220px]" />
              )}
            />
          )}
        </FormField>
      )}

      <fieldset className="m-0 grid gap-2 border-0 p-0">
        <legend className="mb-2 p-0 text-sm font-semibold">Decisión</legend>
        <Controller
          control={control}
          name="decision"
          render={({ field }) => (
            <Radio.Group
              value={field.value}
              onChange={(e) => {
                field.onChange(e.target.value);
                onDecision(e.target.value as Decision);
              }}
              optionType="button"
              className="grid! grid-cols-2"
              options={[
                { value: APPROVE, label: "Aprobar" },
                { value: REJECT, label: "Rechazar" },
              ]}
            />
          )}
        />
      </fieldset>

      {decision === REJECT && (
        <div className="grid gap-4">
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
            id={`${ids}-buyer`}
            label="Mensaje para el comprador"
            help="Lo verá en su portal."
            error={formState.errors.buyer_comment?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="buyer_comment"
                render={({ field }) => (
                  <Input.TextArea
                    {...field}
                    {...ctl}
                    rows={3}
                    placeholder="Explícale qué debe corregir."
                  />
                )}
              />
            )}
          </FormField>
        </div>
      )}

      <FormField
        id={`${ids}-internal`}
        label="Nota interna"
        optional="opcional, el comprador no la ve"
        error={formState.errors.internal_comment?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="internal_comment"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={2} placeholder="Solo para el equipo." />
            )}
          />
        )}
      </FormField>
    </form>
  );
}

function Versions({
  slot,
  viewer,
  canView,
}: {
  slot: DocumentSlot;
  viewer: Viewer;
  canView: boolean;
}) {
  const versions = useSlotVersions(slot.id, true);
  const previous = (versions.data ?? []).filter((v) => !v.is_current);
  if (versions.isPending) return <p className="text-text-tertiary m-0 text-sm">Cargando…</p>;
  if (previous.length === 0) {
    return <p className="text-text-tertiary m-0 text-sm">No hay versiones anteriores.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-2 p-0">
      {previous.map((version) => {
        const last = version.reviews[0];
        const error = viewer.errorFor(version.id);
        return (
          <li key={version.id} className="grid gap-1 text-sm">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1">
                <b className="font-medium">Versión {version.version_number}</b> ·{" "}
                {version.client_filename} · {formatDateTime(version.created_at)}
                {last?.buyer_comment && (
                  <span className="text-text-tertiary block text-xs">
                    Mensaje al comprador: {last.buyer_comment}
                  </span>
                )}
              </span>
              {canView && version.file.scan_status === SCAN_CLEAN && (
                <Button
                  size="small"
                  loading={viewer.loadingFor(version.id)}
                  onClick={() =>
                    viewer.show({
                      fileId: version.id,
                      name: version.client_filename,
                      mimeType: version.file.detected_mime_type,
                      sizeBytes: version.file.size_bytes,
                    })
                  }
                >
                  Ver<span className="sr-only"> versión {version.version_number}</span>
                </Button>
              )}
            </div>
            {error && (
              <p role="alert" className="text-tone-danger-fg m-0 text-xs">
                {error}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface ReviewDrawerProps {
  applicationId: string;
  slot: DocumentSlot | null;
  /** "Sofía Herrera" (o "Solicitud"), encima del nombre del documento. */
  holder: string;
  next: DocumentSlot | null;
  onNext: (slot: DocumentSlot) => void;
  onClose: () => void;
  viewer: Viewer;
  can: { review: boolean; download: boolean };
}

/**
 * Panel de revisión (mockup `solicitud.html`): drawer a la derecha, pantalla completa en
 * móvil. Atrapa el foco y Escape lo cierra (Ant Design `Drawer`).
 */
export function ReviewDrawer({
  applicationId,
  slot,
  holder,
  next,
  onNext,
  onClose,
  viewer,
  can,
}: ReviewDrawerProps) {
  const mobile = useMediaQuery("(max-width: 860px)");
  const formId = useId();
  const fileId = slot?.current_file?.id;
  const file = useDocumentFile(fileId);
  const scan = useScanStatus(fileId);
  const scanStatus = scan.data?.scan_status ?? slot?.current_file?.scan_status ?? null;
  const clean = scanStatus === SCAN_CLEAN;
  const canDecide = can.review && clean && !!file.data && slot?.status !== "WAIVED";
  const viewError = viewer.errorFor(fileId);
  const review = useReviewSlot(applicationId);
  // Decisión elegida en el formulario de esta versión (por defecto, aprobar).
  const [choice, setChoice] = useState<{ fileId: string; decision: Decision } | null>(null);
  const rejecting = choice !== null && choice.fileId === fileId && choice.decision === REJECT;

  const done = () => (next ? onNext(next) : onClose());

  // Al abrir o pasar al siguiente, el foco va al título del documento: se anuncia y queda
  // dentro del panel, sin depender de que termine la animación de apertura.
  // El panel se monta en un portal: el título se enfoca al llegar al DOM (ref de callback),
  // y otra vez al cambiar de documento.
  const slotId = slot?.id;
  const titleRef = useCallback(
    (el: HTMLHeadingElement | null) => {
      if (el && slotId) el.focus();
    },
    [slotId],
  );

  return (
    <Drawer
      open={slot !== null}
      onClose={onClose}
      placement="right"
      size={mobile ? "100%" : 520}
      closable={{ "aria-label": "Cerrar" }}
      destroyOnHidden
      title={
        slot && (
          <div>
            <div className="text-text-tertiary text-sm font-normal">{holder}</div>
            <h2 ref={titleRef} tabIndex={-1} className="m-0 text-lg font-semibold outline-none">
              {slot.label}
            </h2>
          </div>
        )
      }
      footer={
        slot && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={onClose}>Cancelar</Button>
            {next && <Button onClick={() => onNext(next)}>Siguiente</Button>}
            {canDecide && (
              <Button
                type="primary"
                danger={rejecting}
                htmlType="submit"
                form={formId}
                loading={review.isPending}
              >
                {rejecting ? "Rechazar documento" : "Aprobar documento"}
              </Button>
            )}
          </div>
        )
      }
    >
      {slot && (
        <div className="grid content-start gap-5">
          {!slot.current_file ? (
            <p className="text-text-tertiary m-0 text-sm">
              Este documento todavía no tiene archivo.
            </p>
          ) : (
            <>
              <div className="grid gap-2">
                <dl className="m-0 grid grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-x-4 gap-y-2 text-sm">
                  <dt className="text-text-tertiary">Archivo</dt>
                  <dd className="m-0 font-medium break-all">{slot.current_file.client_filename}</dd>
                  <dt className="text-text-tertiary">Tamaño</dt>
                  <dd className="m-0 font-medium">
                    {formatBytes(file.data?.file.size_bytes) ?? "—"}
                  </dd>
                  <dt className="text-text-tertiary">Cargado</dt>
                  <dd className="m-0 font-medium">
                    <RelativeTime value={slot.current_file.created_at} />
                    {file.data?.uploaded_by_buyer_session_id && " · por el comprador"}
                  </dd>
                  <dt className="text-text-tertiary">Análisis antivirus</dt>
                  <dd className="m-0">{scanStatus && <ScanBadge scanStatus={scanStatus} />}</dd>
                  {slot.current_file.document_date && (
                    <>
                      <dt className="text-text-tertiary">Fecha del documento</dt>
                      <dd className="m-0 font-medium">
                        {formatDateOnly(slot.current_file.document_date)}
                      </dd>
                    </>
                  )}
                  {validityText(slot) && (
                    <>
                      <dt className="text-text-tertiary">Vigencia</dt>
                      <dd className="m-0 font-medium">{validityText(slot)}</dd>
                    </>
                  )}
                </dl>
                {can.download && clean && (
                  <div>
                    <Button
                      loading={viewer.loadingFor(fileId)}
                      onClick={() =>
                        viewer.show({
                          fileId: slot.current_file!.id,
                          name: slot.current_file!.client_filename,
                          mimeType: file.data?.file.detected_mime_type,
                          sizeBytes: file.data?.file.size_bytes,
                        })
                      }
                    >
                      Abrir en el visor
                    </Button>
                  </div>
                )}
                {viewError && <Alert type="error" showIcon title={viewError} />}
              </div>

              {canDecide && file.data && (
                <DecisionForm
                  key={file.data.id}
                  review={review}
                  onDecision={(decision) => setChoice({ fileId: file.data!.id, decision })}
                  slot={slot}
                  file={file.data}
                  formId={formId}
                  onDone={done}
                />
              )}
            </>
          )}

          <Collapse
            size="small"
            items={[
              {
                key: "versions",
                label: "Versiones anteriores",
                children: <Versions slot={slot} viewer={viewer} canView={can.download} />,
              },
            ]}
          />
        </div>
      )}
    </Drawer>
  );
}
