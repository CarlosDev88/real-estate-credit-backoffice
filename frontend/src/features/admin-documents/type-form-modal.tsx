"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input, InputNumber, Radio } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { changedFields } from "@/features/admin-common/changes";
import {
  HOLDER_SCOPE_LABELS,
  HOLDER_SCOPES,
  MAX_SIZE_MB,
  MB,
  MIME_LABELS,
  MIME_TYPES,
  type HolderScope,
  type MimeType,
} from "@/features/admin-documents/labels";
import {
  useCreateDocumentType,
  useUpdateDocumentType,
  type DocumentType,
} from "@/features/admin-documents/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar un tipo documental (`POST`/`PATCH /document-types`). El código es estable.
// El tamaño se escribe en MB y viaja en bytes (`max_size_bytes`, máximo 10 MB).

export const TYPE_CODE_PATTERN = /^[A-Z][A-Z0-9_]{1,79}$/;

const schema = z
  .object({
    code: z
      .string()
      .trim()
      .min(1, { error: "Escribe el código." })
      .max(80, { error: "Máximo 80 caracteres." })
      .regex(TYPE_CODE_PATTERN, { error: "Usa mayúsculas, números y _, y empieza por una letra." }),
    name: z
      .string()
      .trim()
      .min(1, { error: "Escribe el nombre." })
      .max(180, { error: "Máximo 180 caracteres." }),
    description: z.string().trim(),
    allowed_mime_types: z.array(z.enum(MIME_TYPES)).min(1, { error: "Elige al menos un formato." }),
    max_size_mb: z
      .number()
      .positive({ error: "Debe ser mayor que 0." })
      .max(MAX_SIZE_MB, { error: `Máximo ${MAX_SIZE_MB} MB.` })
      .nullable(),
    default_validity_days: z
      .number()
      .int({ error: "Días enteros." })
      .min(1, { error: "Mínimo 1 día." })
      .max(3650, { error: "Máximo 3650 días." })
      .nullable(),
    is_repeatable: z.boolean(),
    holder_scope: z.enum(HOLDER_SCOPES),
  })
  .superRefine((values, ctx) => {
    if (values.max_size_mb === null) {
      ctx.addIssue({ code: "custom", path: ["max_size_mb"], message: "Escribe el tamaño máximo." });
    }
  });
type TypeValues = z.infer<typeof schema>;
const FIELDS = [
  "code",
  "name",
  "description",
  "allowed_mime_types",
  "max_size_mb",
  "default_validity_days",
  "is_repeatable",
  "holder_scope",
] as const;

function toValues(type: DocumentType | undefined): TypeValues {
  return {
    code: type?.code ?? "",
    name: type?.name ?? "",
    description: type?.description ?? "",
    allowed_mime_types: (type?.allowed_mime_types as MimeType[] | undefined) ?? ["application/pdf"],
    max_size_mb: type ? Math.round((type.max_size_bytes / MB) * 100) / 100 : 5,
    default_validity_days: type?.default_validity_days ?? null,
    is_repeatable: type?.is_repeatable ?? false,
    holder_scope: (type?.holder_scope as HolderScope | undefined) ?? "PARTICIPANT",
  };
}

const toBody = ({ code: _code, max_size_mb, ...rest }: TypeValues) => {
  void _code;
  return { ...rest, max_size_bytes: Math.round((max_size_mb ?? 0) * MB) };
};

export function TypeFormModal({
  type,
  onClose,
  onCreated,
}: {
  type?: DocumentType;
  onClose: () => void;
  onCreated?: (type: DocumentType) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateDocumentType();
  const update = useUpdateDocumentType(type?.id ?? "");
  const initial = toValues(type);
  const { control, handleSubmit, setError, formState } = useForm<TypeValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<TypeValues>(setError, FIELDS);
  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === "DUPLICATE_CODE") {
      setError("code", { type: error.code, message: error.message });
      return;
    }
    // `max_size_bytes` es el campo de la API; en el formulario va en MB.
    if (isApiError(error)) {
      const size = error.details.find((d) => d.field === "max_size_bytes");
      if (size) setError("max_size_mb", { type: size.code, message: size.message });
    }
    onFieldError(error);
  };

  const submit = handleSubmit((values) => {
    if (!type) {
      create.mutate(
        { ...toBody(values), code: values.code },
        {
          onSuccess: (created) => {
            toast.success({ title: "Tipo documental creado" });
            onClose();
            onCreated?.(created);
          },
          onError,
        },
      );
      return;
    }
    const body = changedFields(toBody(values), toBody(initial), [
      "name",
      "description",
      "allowed_mime_types",
      "max_size_bytes",
      "default_validity_days",
      "is_repeatable",
      "holder_scope",
    ]);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Tipo documental guardado" });
        onClose();
      },
      onError,
    });
  });

  const errors = formState.errors;

  return (
    <ActionModal
      open
      title={type ? "Editar tipo documental" : "Nuevo tipo documental"}
      okText={type ? "Guardar" : "Crear tipo"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={640}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-code`}
          label="Código"
          help={type ? "El código es estable y no se cambia." : "Mayúsculas, números y _."}
          error={errors.code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  {...ctl}
                  disabled={!!type}
                  autoComplete="off"
                  className="font-mono"
                />
              )}
            />
          )}
        </FormField>
        <FormField id={`${ids}-name`} label="Nombre" error={errors.name?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="name"
              render={({ field }) => <Input {...field} {...ctl} maxLength={180} />}
            />
          )}
        </FormField>
      </div>
      <FormField
        id={`${ids}-description`}
        label="Descripción"
        optional="opcional"
        help="Lo que ve quien carga el documento."
        error={errors.description?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={2} />}
          />
        )}
      </FormField>

      <Controller
        control={control}
        name="allowed_mime_types"
        render={({ field }) => (
          <fieldset
            className="m-0 grid gap-1.5 border-0 p-0"
            aria-describedby={errors.allowed_mime_types ? `${ids}-mime-error` : undefined}
            aria-invalid={errors.allowed_mime_types ? true : undefined}
          >
            <legend className="mb-1.5 p-0 text-sm font-medium">Formatos permitidos</legend>
            <div className="flex flex-wrap gap-4">
              {MIME_TYPES.map((mime) => (
                <Checkbox
                  key={mime}
                  checked={field.value.includes(mime)}
                  onChange={(event) =>
                    field.onChange(
                      event.target.checked
                        ? [...field.value, mime]
                        : field.value.filter((value) => value !== mime),
                    )
                  }
                >
                  {MIME_LABELS[mime]}
                </Checkbox>
              ))}
            </div>
            {errors.allowed_mime_types && (
              <p id={`${ids}-mime-error`} className="text-tone-danger-fg m-0 text-sm">
                {errors.allowed_mime_types.message}
              </p>
            )}
          </fieldset>
        )}
      />

      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-size`}
          label="Tamaño máximo por archivo"
          help={`Hasta ${MAX_SIZE_MB} MB.`}
          error={errors.max_size_mb?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="max_size_mb"
              render={({ field }) => (
                <InputNumber<number>
                  {...ctl}
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? null)}
                  min={0.1}
                  max={MAX_SIZE_MB}
                  step={0.5}
                  suffix="MB"
                  className="w-full"
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-validity`}
          label="Vigencia sugerida"
          optional="opcional"
          help="Días que vale el documento desde su fecha."
          error={errors.default_validity_days?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="default_validity_days"
              render={({ field }) => (
                <InputNumber<number>
                  {...ctl}
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? null)}
                  min={1}
                  max={3650}
                  precision={0}
                  suffix="días"
                  className="w-full"
                />
              )}
            />
          )}
        </FormField>
      </div>

      <Controller
        control={control}
        name="holder_scope"
        render={({ field }) => (
          <fieldset className="m-0 grid gap-1.5 border-0 p-0">
            <legend className="mb-1.5 p-0 text-sm font-medium">A quién se le pide</legend>
            <Radio.Group
              value={field.value}
              onChange={(event) => field.onChange(event.target.value)}
              options={HOLDER_SCOPES.map((scope) => ({
                value: scope,
                label: HOLDER_SCOPE_LABELS[scope],
              }))}
            />
            <p className="text-text-tertiary m-0 text-xs">
              Por participante: a cada uno al que aplique el requisito. Una vez por solicitud: el
              del inmueble o la legalización.
            </p>
          </fieldset>
        )}
      />
      <Controller
        control={control}
        name="is_repeatable"
        render={({ field }) => (
          <Checkbox
            checked={field.value}
            onChange={(event) => field.onChange(event.target.checked)}
          >
            Se puede cargar más de una vez (por ejemplo, un extracto por mes)
          </Checkbox>
        )}
      />
    </ActionModal>
  );
}
