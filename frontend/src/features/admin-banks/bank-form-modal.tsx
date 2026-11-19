"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { changedFields } from "@/features/admin-common/changes";
import {
  useCreateBank,
  useUpdateBank,
  type Bank,
  type BankDetail,
} from "@/features/admin-banks/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar un banco (`POST`/`PATCH /banks`). El código es estable: solo se escribe
// al crear. Zod solo revisa el formato (el del código lo pide el contrato).

const max = (n: number) => ({ error: `Máximo ${n} caracteres.` });
export const CODE_PATTERN = /^[A-Z][A-Z0-9_]{1,49}$/;
export const CODE_HELP = "Mayúsculas, números y _; empieza por letra. No se cambia después.";

const schema = z.object({
  code: z
    .string()
    .trim()
    .min(1, { error: "Escribe el código." })
    .max(50, max(50))
    .regex(CODE_PATTERN, { error: "Usa mayúsculas, números y _, y empieza por una letra." }),
  name: z.string().trim().min(1, { error: "Escribe el nombre." }).max(180, max(180)),
  short_name: z.string().trim().max(30, max(30)),
  tax_id: z.string().trim().max(30, max(30)),
  operational_notes: z.string().trim(),
});
type BankValues = z.infer<typeof schema>;
const FIELDS = ["code", "name", "short_name", "tax_id", "operational_notes"] as const;
const EDITABLE = ["name", "short_name", "tax_id", "operational_notes"] as const;

export function BankFormModal({
  bank,
  onClose,
  onCreated,
}: {
  bank?: BankDetail;
  onClose: () => void;
  onCreated?: (bank: Bank) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateBank();
  const update = useUpdateBank(bank?.id ?? "");
  const initial: BankValues = {
    code: bank?.code ?? "",
    name: bank?.name ?? "",
    short_name: bank?.short_name ?? "",
    tax_id: bank?.tax_id ?? "",
    operational_notes: bank?.operational_notes ?? "",
  };
  const { control, handleSubmit, setError, formState } = useForm<BankValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<BankValues>(setError, FIELDS);
  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === "DUPLICATE_CODE") {
      setError("code", { type: error.code, message: error.message });
      return;
    }
    onFieldError(error);
  };

  const submit = handleSubmit((values) => {
    if (!bank) {
      create.mutate(values, {
        onSuccess: (created) => {
          toast.success({ title: "Banco creado" });
          onClose();
          onCreated?.(created);
        },
        onError,
      });
      return;
    }
    const body = changedFields(values, initial, EDITABLE);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Datos guardados" });
        onClose();
      },
      onError,
    });
  });

  const text = (
    name: (typeof FIELDS)[number],
    label: string,
    options: { optional?: boolean; help?: string; disabled?: boolean; mono?: boolean } = {},
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={options.optional ? "opcional" : undefined}
      help={options.help}
      error={formState.errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Input
              {...field}
              {...ctl}
              disabled={options.disabled}
              autoComplete="off"
              className={options.mono ? "font-mono" : undefined}
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open
      title={bank ? "Editar banco" : "Nuevo banco"}
      okText={bank ? "Guardar" : "Crear banco"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={600}
    >
      {text("code", "Código", {
        disabled: !!bank,
        help: bank ? "El código es estable y no se cambia." : CODE_HELP,
        mono: true,
      })}
      <div className="grid items-start gap-4 min-[600px]:grid-cols-[2fr_1fr]">
        {text("name", "Nombre")}
        {text("short_name", "Nombre corto", { optional: true, help: "Para los listados." })}
      </div>
      {text("tax_id", "NIT", { optional: true })}
      <FormField
        id={`${ids}-notes`}
        label="Notas operativas"
        optional="opcional"
        help="Para el equipo: canales de radicación, contactos, tiempos."
        error={formState.errors.operational_notes?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="operational_notes"
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={3} />}
          />
        )}
      </FormField>
    </ActionModal>
  );
}
