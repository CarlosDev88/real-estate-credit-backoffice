"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input, InputNumber, Select } from "antd";
import { useEffect, useId, useMemo } from "react";
import { Controller, useForm, useWatch, type FieldErrors } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { MoneyInput } from "@/components/ui/money";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useCatalog, type MetadataItem } from "@/features/applications/queries";
import { useParticipants } from "@/features/applications/workspace-queries";
import { groupSlots } from "@/features/document-review/documents-tab";
import { useDocumentSlots, type DocumentSlot } from "@/features/document-review/queries";
import {
  defaultPastInput,
  fromLocalInput,
  isFutureInput,
  toLocalInput,
} from "@/features/filings/local-datetime";
import {
  useRecordResponse,
  type Filing,
  type FilingResponse,
  type FilingResponseCreateRequest,
} from "@/features/filings/queries";
import {
  responseForm,
  type ResponseField,
  type ResponseForm,
} from "@/features/filings/response-fields";
import { useToast } from "@/providers/toast";

const TYPE_CATALOG = "filing_response_type";
/** Motivo de cada documento observado: el mismo de un rechazo (API §20.2). */
const OBSERVATION_REASON_CATALOG = "document_rejection_reason";
/** Un slot exonerado no se puede observar. */
const WAIVED = "WAIVED";
/** Límites del backend (`filings/serializers.py`). */
const REFERENCE_MAX = 100;
const MESSAGE_MAX = 2000;
const INTERNAL_MAX = 4000;

const REQUIRED: Record<ResponseField, string> = {
  reason_code: "Elige el motivo.",
  public_message: "Escribe el mensaje para el comprador.",
  internal_comment: "Escribe la nota interna.",
  observations: "Elige al menos un documento observado.",
  approved_amount_cop: "Indica el monto aprobado.",
  approved_term_months: "Indica el plazo.",
  valid_until: "Indica la vigencia.",
  disbursed_amount_cop: "Indica el monto desembolsado.",
};

interface ObservationValue {
  document_slot_id: string;
  reason_code: string;
  message: string;
}

interface Values {
  response_type: string;
  received_at: string;
  external_reference: string;
  reason_code: string;
  public_message: string;
  internal_comment: string;
  approved_amount_cop: number | null;
  approved_term_months: number | null;
  valid_until: string;
  disbursed_amount_cop: number | null;
  observations: ObservationValue[];
}

const FIELDS = [
  "response_type",
  "received_at",
  "external_reference",
  "reason_code",
  "public_message",
  "internal_comment",
  "observations",
  "approved_amount_cop",
  "approved_term_months",
  "valid_until",
  "disbursed_amount_cop",
] as const;

const blank = (value: unknown) =>
  value === null ||
  value === undefined ||
  (typeof value === "string" && !value.trim()) ||
  (Array.isArray(value) && value.length === 0);

function makeSchema(filedAt: string, formOf: (type: string) => ResponseForm) {
  return z
    .object({
      response_type: z.string().min(1, { error: "Elige el tipo de respuesta." }),
      received_at: z.string().min(1, { error: "Indica cuándo respondió el banco." }),
      external_reference: z
        .string()
        .max(REFERENCE_MAX, { error: `Máximo ${REFERENCE_MAX} caracteres.` }),
      reason_code: z.string(),
      public_message: z.string().max(MESSAGE_MAX, { error: `Máximo ${MESSAGE_MAX} caracteres.` }),
      internal_comment: z
        .string()
        .max(INTERNAL_MAX, { error: `Máximo ${INTERNAL_MAX} caracteres.` }),
      approved_amount_cop: z.number().nullable(),
      approved_term_months: z.number().nullable(),
      valid_until: z.string(),
      disbursed_amount_cop: z.number().nullable(),
      observations: z.array(
        z.object({
          document_slot_id: z.string(),
          reason_code: z.string().min(1, { error: "Elige el motivo." }),
          message: z
            .string()
            .trim()
            .min(1, { error: "Escribe qué debe corregir el comprador." })
            .max(MESSAGE_MAX, { error: `Máximo ${MESSAGE_MAX} caracteres.` }),
        }),
      ),
    })
    .superRefine((values, ctx) => {
      const form = formOf(values.response_type);
      for (const field of form.required) {
        if (blank(values[field]))
          ctx.addIssue({ code: "custom", path: [field], message: REQUIRED[field] });
      }
      const at = fromLocalInput(values.received_at);
      if (values.received_at && at === null) {
        ctx.addIssue({ code: "custom", path: ["received_at"], message: "Fecha y hora inválidas." });
      } else if (values.received_at && isFutureInput(values.received_at)) {
        ctx.addIssue({
          code: "custom",
          path: ["received_at"],
          message: "La fecha no puede ser futura.",
        });
      } else if (at && Date.parse(at) < Date.parse(filedAt) - 60_000) {
        ctx.addIssue({
          code: "custom",
          path: ["received_at"],
          message: "La respuesta no puede ser anterior a la radicación.",
        });
      }
    });
}

/** Cuerpo del `POST`: solo los campos del tipo elegido y con valor. */
export function buildResponseBody(
  values: Values,
  version: number,
  correcting: FilingResponse | null,
  form: ResponseForm,
): FilingResponseCreateRequest {
  const has = (field: ResponseField) => form.fields.includes(field);
  const text = (value: string) => value.trim() || undefined;
  const body: FilingResponseCreateRequest = {
    response_type: values.response_type,
    received_at: fromLocalInput(values.received_at)!,
    expected_version: version,
  };
  const reference = text(values.external_reference);
  if (reference) body.external_reference = reference;
  if (has("reason_code") && values.reason_code) body.reason_code = values.reason_code;
  if (has("public_message") && text(values.public_message))
    body.public_message = text(values.public_message);
  if (has("internal_comment") && text(values.internal_comment))
    body.internal_comment = text(values.internal_comment);
  if (has("observations") && values.observations.length) {
    body.observations = values.observations.map((o) => ({ ...o, message: o.message.trim() }));
  }
  if (has("approved_amount_cop") && values.approved_amount_cop !== null)
    body.approved_amount_cop = values.approved_amount_cop;
  if (has("approved_term_months") && values.approved_term_months !== null)
    body.approved_term_months = values.approved_term_months;
  if (has("valid_until") && values.valid_until) body.valid_until = values.valid_until;
  if (has("disbursed_amount_cop") && values.disbursed_amount_cop !== null)
    body.disbursed_amount_cop = values.disbursed_amount_cop;
  if (correcting) body.corrects_response_id = correcting.id;
  return body;
}

const optionsOf = (items: MetadataItem[]) => items.map((i) => ({ value: i.code, label: i.label }));

/** Slots que se pueden observar: vigentes, con una versión cargada y no exonerados. */
export function observableSlots(slots: DocumentSlot[]): DocumentSlot[] {
  return slots.filter((s) => !s.is_retired && !!s.current_file && s.status !== WAIVED);
}

function ObservationPicker({
  applicationId,
  value,
  onChange,
  errors,
  reasons,
  idPrefix,
}: {
  applicationId: string;
  value: ObservationValue[];
  onChange: (value: ObservationValue[]) => void;
  errors: FieldErrors<Values>["observations"];
  reasons: MetadataItem[];
  idPrefix: string;
}) {
  const slots = useDocumentSlots(applicationId);
  const participants = useParticipants(applicationId);
  const groups = useMemo(
    () =>
      groupSlots(
        observableSlots(slots.data ?? []),
        participants.participants ?? [],
        participants.profiles,
      ),
    [slots.data, participants.participants, participants.profiles],
  );

  if (slots.isPending)
    return <p className="text-text-tertiary m-0 text-sm">Cargando documentos…</p>;
  if (groups.length === 0) {
    return (
      <p className="text-text-tertiary m-0 text-sm">No hay documentos cargados para observar.</p>
    );
  }

  const toggle = (slotId: string, checked: boolean) =>
    onChange(
      checked
        ? [...value, { document_slot_id: slotId, reason_code: "", message: "" }]
        : value.filter((o) => o.document_slot_id !== slotId),
    );
  const patch = (index: number, change: Partial<ObservationValue>) =>
    onChange(value.map((o, i) => (i === index ? { ...o, ...change } : o)));

  return (
    <div className="grid gap-4">
      {groups.map((group) => (
        <fieldset key={group.key} className="m-0 grid gap-2 border-0 p-0">
          <legend className="mb-1 p-0 text-sm font-semibold">
            {group.title}
            {group.note && <span className="text-text-tertiary font-normal"> · {group.note}</span>}
          </legend>
          {group.slots.map((slot) => {
            const index = value.findIndex((o) => o.document_slot_id === slot.id);
            const item = index >= 0 ? value[index] : undefined;
            const itemErrors = index >= 0 && Array.isArray(errors) ? errors[index] : undefined;
            const base = `${idPrefix}-obs-${slot.id}`;
            return (
              <div
                key={slot.id}
                className="border-border-default grid gap-2 rounded-md border px-3 py-2"
              >
                <Checkbox checked={!!item} onChange={(e) => toggle(slot.id, e.target.checked)}>
                  {slot.label}
                  <span className="text-text-tertiary text-xs">
                    {" "}
                    · {slot.current_file?.client_filename}
                  </span>
                </Checkbox>
                {item && (
                  <div className="grid gap-3 pl-6">
                    <FormField
                      id={`${base}-reason`}
                      label="Motivo"
                      error={itemErrors?.reason_code?.message}
                    >
                      {(ctl) => (
                        <Select
                          {...ctl}
                          aria-label={`Motivo de ${slot.label}`}
                          value={item.reason_code || undefined}
                          onChange={(code: string) => patch(index, { reason_code: code })}
                          placeholder="Elige un motivo"
                          options={optionsOf(reasons)}
                          virtual={false}
                        />
                      )}
                    </FormField>
                    <FormField
                      id={`${base}-message`}
                      label="Mensaje al comprador"
                      help="El comprador lo ve tal cual, junto al documento."
                      error={itemErrors?.message?.message}
                    >
                      {(ctl) => (
                        <Input.TextArea
                          {...ctl}
                          aria-label={`Mensaje al comprador sobre ${slot.label}`}
                          rows={2}
                          maxLength={MESSAGE_MAX}
                          value={item.message}
                          onChange={(e) => patch(index, { message: e.target.value })}
                        />
                      )}
                    </FormField>
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}

interface Props {
  applicationId: string;
  filing: Filing;
  version: number;
  open: boolean;
  /** Corrección de esta respuesta (`corrects_response_id`): el tipo queda fijo. */
  correcting: FilingResponse | null;
  onClose: () => void;
  onRecorded: (response: FilingResponse) => void;
}

const defaults = (type = ""): Values => ({
  response_type: type,
  received_at: defaultPastInput(),
  external_reference: "",
  reason_code: "",
  public_message: "",
  internal_comment: "",
  approved_amount_cop: null,
  approved_term_months: null,
  valid_until: "",
  disbursed_amount_cop: null,
  observations: [],
});

/**
 * "Registrar respuesta" del banco (API §20.2). Pide solo los campos del tipo elegido
 * (`metadata` del catálogo `filing_response_type`); la API valida lo demás y sus errores de
 * campo van al campo.
 */
export function RecordResponseModal({
  applicationId,
  filing,
  version,
  open,
  correcting,
  onClose,
  onRecorded,
}: Props) {
  const ids = useId();
  const toast = useToast();
  const record = useRecordResponse(applicationId, filing.id);
  const types = useCatalog(TYPE_CATALOG);
  const observationReasons = useCatalog(OBSERVATION_REASON_CATALOG);
  // Los campos de cada tipo salen del `metadata` del catálogo (API), no de una tabla local.
  const typeItems = types.items;
  const schema = useMemo(
    () => makeSchema(filing.filed_at, (code) => responseForm(code, typeItems)),
    [filing.filed_at, typeItems],
  );
  // Sin `values`: con él, react-hook-form reinicia el formulario cada vez que cambian, y la
  // hora por omisión cambia con el minuto (se borraba lo que el asesor ya había llenado).
  // El formulario se reinicia solo al abrir el modal, con la hora de ese momento.
  const correctingType = correcting?.response_type;
  const { control, handleSubmit, setError, reset, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: defaults(correctingType),
  });
  useEffect(() => {
    if (open) reset(defaults(correctingType));
  }, [open, correctingType, reset]);
  const onError = useFormErrorHandler<Values>(setError, FIELDS);
  const type = useWatch({ control, name: "response_type" });
  const form = responseForm(type, types.items);
  const shows = (field: ResponseField) => form.fields.includes(field);
  const optional = (field: ResponseField) =>
    form.required.includes(field) ? undefined : "opcional";
  const reasons = useCatalog(form.reasonCatalog ?? "");
  const errors = formState.errors;

  const close = () => {
    reset(defaults(correcting?.response_type));
    onClose();
  };

  const submit = handleSubmit((values) => {
    record.mutate(
      buildResponseBody(
        values,
        version,
        correcting,
        responseForm(values.response_type, types.items),
      ),
      {
        onSuccess: (response) => {
          toast.success({
            title: correcting ? "Respuesta corregida" : "Respuesta registrada",
            message: response.response_type_label,
          });
          close();
          onRecorded(response);
        },
        onError,
      },
    );
  });

  const title = correcting
    ? `Corregir la respuesta: ${correcting.response_type_label}`
    : `Registrar respuesta de la radicación #${filing.sequence_number}`;

  return (
    <ActionModal
      open={open}
      title={title}
      width={640}
      description={
        correcting
          ? "La corrección reemplaza los datos de la última respuesta y no cambia ningún estado."
          : undefined
      }
      okText={correcting ? "Guardar corrección" : "Registrar respuesta"}
      loading={record.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-type`}
          label="Tipo de respuesta"
          error={errors.response_type?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="response_type"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  disabled={!!correcting}
                  placeholder="Elige el tipo"
                  options={optionsOf(types.items)}
                  loading={types.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-received`}
          label="Fecha y hora de la respuesta"
          error={errors.received_at?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="received_at"
              render={({ field }) => (
                <Input {...field} {...ctl} type="datetime-local" max={toLocalInput(new Date())} />
              )}
            />
          )}
        </FormField>
      </div>

      {type && (
        <>
          <FormField
            id={`${ids}-reference`}
            label="Referencia del banco"
            optional="opcional"
            error={errors.external_reference?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="external_reference"
                render={({ field }) => <Input {...field} {...ctl} maxLength={REFERENCE_MAX} />}
              />
            )}
          </FormField>

          {shows("reason_code") && (
            <FormField id={`${ids}-reason`} label="Motivo" error={errors.reason_code?.message}>
              {(ctl) => (
                <Controller
                  control={control}
                  name="reason_code"
                  render={({ field }) => (
                    <Select
                      {...ctl}
                      value={field.value || undefined}
                      onChange={field.onChange}
                      placeholder="Elige el motivo"
                      options={optionsOf(reasons.items)}
                      loading={reasons.isPending}
                      virtual={false}
                    />
                  )}
                />
              )}
            </FormField>
          )}

          {(shows("approved_amount_cop") ||
            shows("approved_term_months") ||
            shows("valid_until")) && (
            <div className="grid gap-4 min-[600px]:grid-cols-3">
              {shows("approved_amount_cop") && (
                <FormField
                  id={`${ids}-approved`}
                  label="Monto aprobado"
                  optional={optional("approved_amount_cop")}
                  error={errors.approved_amount_cop?.message}
                >
                  {(ctl) => (
                    <Controller
                      control={control}
                      name="approved_amount_cop"
                      render={({ field }) => (
                        <MoneyInput
                          {...ctl}
                          value={field.value}
                          onChange={field.onChange}
                          className="w-full"
                        />
                      )}
                    />
                  )}
                </FormField>
              )}
              {shows("approved_term_months") && (
                <FormField
                  id={`${ids}-term`}
                  label="Plazo en meses"
                  optional={optional("approved_term_months")}
                  error={errors.approved_term_months?.message}
                >
                  {(ctl) => (
                    <Controller
                      control={control}
                      name="approved_term_months"
                      render={({ field }) => (
                        <InputNumber<number>
                          {...ctl}
                          value={field.value}
                          onChange={(v) => field.onChange(v ?? null)}
                          min={1}
                          precision={0}
                          className="w-full"
                        />
                      )}
                    />
                  )}
                </FormField>
              )}
              {shows("valid_until") && (
                <FormField
                  id={`${ids}-valid`}
                  label="Vigencia"
                  optional={optional("valid_until")}
                  error={errors.valid_until?.message}
                >
                  {(ctl) => (
                    <Controller
                      control={control}
                      name="valid_until"
                      render={({ field }) => <Input {...field} {...ctl} type="date" />}
                    />
                  )}
                </FormField>
              )}
            </div>
          )}

          {shows("disbursed_amount_cop") && (
            <FormField
              id={`${ids}-disbursed`}
              label="Monto desembolsado"
              optional={optional("disbursed_amount_cop")}
              error={errors.disbursed_amount_cop?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name="disbursed_amount_cop"
                  render={({ field }) => (
                    <MoneyInput
                      {...ctl}
                      value={field.value}
                      onChange={field.onChange}
                      className="w-full"
                    />
                  )}
                />
              )}
            </FormField>
          )}

          {shows("observations") && (
            <div className="grid gap-2">
              <span className="text-sm font-medium">Documentos observados</span>
              <p className="text-text-tertiary m-0 text-xs">
                Cada documento elegido se rechaza con su motivo y el comprador lo ve para
                corregirlo.
              </p>
              <Controller
                control={control}
                name="observations"
                render={({ field }) => (
                  <ObservationPicker
                    applicationId={applicationId}
                    value={field.value}
                    onChange={field.onChange}
                    errors={errors.observations}
                    reasons={observationReasons.items}
                    idPrefix={ids}
                  />
                )}
              />
              {(errors.observations?.message || errors.observations?.root?.message) && (
                <p role="alert" className="text-tone-danger-fg m-0 text-sm">
                  {errors.observations?.message ?? errors.observations?.root?.message}
                </p>
              )}
            </div>
          )}

          {shows("public_message") && (
            <FormField
              id={`${ids}-public`}
              label="Mensaje al comprador"
              optional={optional("public_message")}
              help="El comprador lo ve en su portal."
              error={errors.public_message?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name="public_message"
                  render={({ field }) => (
                    <Input.TextArea {...field} {...ctl} rows={2} maxLength={MESSAGE_MAX} />
                  )}
                />
              )}
            </FormField>
          )}

          {shows("internal_comment") && (
            <FormField
              id={`${ids}-internal`}
              label="Nota interna"
              optional={optional("internal_comment")}
              help="El texto del banco o tu nota. No la ven el comprador ni el broker."
              error={errors.internal_comment?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name="internal_comment"
                  render={({ field }) => (
                    <Input.TextArea {...field} {...ctl} rows={3} maxLength={INTERNAL_MAX} />
                  )}
                />
              )}
            </FormField>
          )}
        </>
      )}
    </ActionModal>
  );
}
