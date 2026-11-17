"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Modal, Select } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { FormField, useFormErrorHandler } from "@/features/applications/form-field";
import { bankLabel, useCatalog } from "@/features/applications/queries";
import type { ApplicationDetail } from "@/features/applications/workspace-queries";
import {
  defaultPastInput,
  fromLocalInput,
  isFutureInput,
  toLocalInput,
} from "@/features/filings/local-datetime";
import {
  useCreateFiling,
  useUpdateFiling,
  type Filing,
  type PackageJob,
} from "@/features/filings/queries";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Límites del backend (`filings/serializers.py`). */
export const REFERENCE_MAX = 100;
export const COMMENT_MAX = 2000;
/** Catálogo de los canales de entrega (API §20.1). */
const CHANNEL_CATALOG = "filing_channel";

const max = (limit: number) => z.string().max(limit, { error: `Máximo ${limit} caracteres.` });

/** Texto opcional: vacío no se envía. */
function optional<K extends string>(key: K, value: string): Partial<Record<K, string>> {
  const trimmed = value.trim();
  return trimmed ? ({ [key]: trimmed } as Record<K, string>) : {};
}

/** "Fondo Nacional del Ahorro · Crédito hipotecario". */
export function productLabel(product: Filing["bank_product"]): string {
  return `${bankLabel(product.bank)} · ${product.name}`;
}

/** Datos del paquete que se entrega: archivos, tamaño y cuándo se armó. */
export function packageSummary(job: PackageJob): string {
  const files = job.documents.filter((d) => d.file).length;
  return [
    files === 1 ? "1 documento" : `${files} documentos`,
    formatBytes(job.output?.size_bytes),
    job.completed_at ? `armado el ${formatDateTime(job.completed_at)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function ReadOnlyField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      <div className="bg-bg-subtle border-border-default rounded-md border px-3 py-1.5 text-sm">
        {children}
      </div>
    </div>
  );
}

// ---------- registrar radicación ----------

const createSchema = z.object({
  channel_code: z.string({ error: "Elige el canal." }).min(1, { error: "Elige el canal." }),
  external_reference: max(REFERENCE_MAX),
  filed_at: z
    .string()
    .min(1, { error: "Indica cuándo se entregó." })
    .refine((v) => fromLocalInput(v) !== null, { error: "Fecha y hora inválidas." })
    .refine((v) => !isFutureInput(v), { error: "La fecha de entrega no puede ser futura." }),
  comment: max(COMMENT_MAX),
});
type CreateValues = z.infer<typeof createSchema>;
const CREATE_FIELDS = ["channel_code", "external_reference", "filed_at", "comment"] as const;

interface RegisterProps {
  detail: ApplicationDetail;
  version: number;
  job: PackageJob | null;
  open: boolean;
  onClose: () => void;
  onFiled: () => void;
}

/**
 * Registro de la entrega manual al banco (API §20.1): producto de la financiación,
 * canal, referencia, fecha de entrega, comentario y el paquete que se usó.
 */
export function RegisterFilingModal({
  detail,
  version,
  job,
  open,
  onClose,
  onFiled,
}: RegisterProps) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateFiling(detail.id);
  const channels = useCatalog(CHANNEL_CATALOG);
  const product = detail.bank_product;
  const { control, handleSubmit, setError, reset, formState } = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      channel_code: "",
      external_reference: "",
      filed_at: defaultPastInput(),
      comment: "",
    },
  });
  const onError = useFormErrorHandler<CreateValues>(setError, CREATE_FIELDS);

  const close = () => {
    reset({
      channel_code: "",
      external_reference: "",
      filed_at: defaultPastInput(),
      comment: "",
    });
    onClose();
  };

  const submit = handleSubmit((values) => {
    if (!product || !job) return;
    create.mutate(
      {
        bank_product_id: product.id,
        package_job_id: job.id,
        channel_code: values.channel_code,
        filed_at: fromLocalInput(values.filed_at)!,
        ...optional("external_reference", values.external_reference),
        ...optional("comment", values.comment),
        expected_version: version,
      },
      {
        onSuccess: (filing) => {
          toast.success({
            title: "Radicación registrada",
            message: `La solicitud pasa a ${filing.application_status_label}.`,
          });
          close();
          onFiled();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={open}
      title="Registrar radicación"
      onCancel={close}
      okText="Registrar radicación"
      cancelText="Cancelar"
      onOk={() => void submit()}
      okButtonProps={{ disabled: !product || !job }}
      confirmLoading={create.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <p className="text-text-secondary m-0 text-sm">
          Registra la entrega después de enviar el paquete al banco. La solicitud pasa a radicada y
          los documentos entregados quedan bloqueados.
        </p>
        <ReadOnlyField label="Producto">
          {product ? productLabel(product) : "La solicitud no tiene producto financiero."}
        </ReadOnlyField>
        <ReadOnlyField label="Paquete entregado">
          {job ? (
            <>
              <span className="font-mono text-xs break-all">{job.output?.filename}</span>
              <span className="text-text-tertiary block text-xs">{packageSummary(job)}</span>
            </>
          ) : (
            "Prepara el paquete antes de radicar."
          )}
        </ReadOnlyField>
        <FormField
          id={`${ids}-channel`}
          label="Canal"
          error={formState.errors.channel_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="channel_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el canal de entrega"
                  options={channels.items.map((c) => ({ value: c.code, label: c.label }))}
                  loading={channels.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-reference`}
          label="Referencia del banco"
          optional="opcional"
          help="El número o código que dio el banco al recibirla."
          error={formState.errors.external_reference?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="external_reference"
              render={({ field }) => <Input {...field} {...ctl} maxLength={REFERENCE_MAX} />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-filed-at`}
          label="Fecha y hora de entrega"
          error={formState.errors.filed_at?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="filed_at"
              render={({ field }) => (
                <Input {...field} {...ctl} type="datetime-local" max={toLocalInput(new Date())} />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-comment`}
          label="Comentario"
          optional="opcional, interno"
          error={formState.errors.comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="comment"
              render={({ field }) => (
                <Input.TextArea {...field} {...ctl} rows={3} maxLength={COMMENT_MAX} />
              )}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

// ---------- corregir referencia o comentario ----------

const editSchema = z.object({
  external_reference: max(REFERENCE_MAX),
  comment: max(COMMENT_MAX),
});
type EditValues = z.infer<typeof editSchema>;
const EDIT_FIELDS = ["external_reference", "comment"] as const;

/** Vacío borra el valor: la API lo guarda como nulo (API §20.1). */
const orNull = (value: string) => value.trim() || null;

/** Corrige la referencia o el comentario (`PATCH /filings/{id}`), sin tocar lo demás. */
export function EditFilingModal({
  applicationId,
  filing,
  onClose,
}: {
  applicationId: string;
  filing: Filing | null;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const update = useUpdateFiling(applicationId);
  const { control, handleSubmit, setError, formState } = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    values: {
      external_reference: filing?.external_reference ?? "",
      comment: filing?.comment ?? "",
    },
  });
  const onError = useFormErrorHandler<EditValues>(setError, EDIT_FIELDS);

  const submit = handleSubmit((values) => {
    if (!filing) return;
    update.mutate(
      {
        filingId: filing.id,
        body: {
          external_reference: orNull(values.external_reference),
          comment: orNull(values.comment),
        },
      },
      {
        onSuccess: () => {
          toast.success({ title: "Radicación corregida" });
          onClose();
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={!!filing}
      title={filing ? `Corregir la radicación #${filing.sequence_number}` : undefined}
      onCancel={onClose}
      okText="Guardar"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={update.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <p className="text-text-secondary m-0 text-sm">
          Solo cambian la referencia y el comentario. Los documentos entregados y las respuestas del
          banco no cambian.
        </p>
        <FormField
          id={`${ids}-reference`}
          label="Referencia del banco"
          optional="vacía la borra"
          error={formState.errors.external_reference?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="external_reference"
              render={({ field }) => <Input {...field} {...ctl} maxLength={REFERENCE_MAX} />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-comment`}
          label="Comentario"
          optional="vacío lo borra"
          error={formState.errors.comment?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="comment"
              render={({ field }) => (
                <Input.TextArea {...field} {...ctl} rows={3} maxLength={COMMENT_MAX} />
              )}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}
