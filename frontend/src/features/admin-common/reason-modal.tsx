"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input } from "antd";
import { useId } from "react";
import type { ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";

const REASON_MAX = 1000;

const schemaFor = (required: boolean) =>
  z.object({
    reason: required
      ? z
          .string()
          .trim()
          .min(1, { error: "Escribe el motivo." })
          .max(REASON_MAX, { error: `Máximo ${REASON_MAX} caracteres.` })
      : z
          .string()
          .trim()
          .max(REASON_MAX, { error: `Máximo ${REASON_MAX} caracteres.` }),
  });
type ReasonValues = { reason: string };
const FIELDS = ["reason"] as const;

export interface ReasonModalProps {
  title: string;
  description?: ReactNode;
  okText: string;
  /** El contrato exige el motivo (`ReasonRequest`) o lo deja opcional (`OptionalReasonRequest`). */
  reasonRequired: boolean;
  /** Acción destructiva (desactivar, rechazar, archivar): botón `danger`. */
  danger?: boolean;
  loading: boolean;
  /** Ejecuta la acción. Debe rechazar con el error de la API para llevarlo al campo o al toast. */
  onConfirm: (reason: string) => Promise<unknown>;
  onDone: () => void;
  onCancel: () => void;
}

/**
 * Confirmación de una acción con motivo (activar, desactivar, enviar, aprobar, rechazar,
 * archivar). Se monta al abrir y se desmonta al cerrar: el motivo arranca vacío.
 */
export function ReasonModal({
  title,
  description,
  okText,
  reasonRequired,
  danger = false,
  loading,
  onConfirm,
  onDone,
  onCancel,
}: ReasonModalProps) {
  const ids = useId();
  const { control, handleSubmit, setError, formState } = useForm<ReasonValues>({
    resolver: zodResolver(schemaFor(reasonRequired)),
    defaultValues: { reason: "" },
  });
  const onError = useFormErrorHandler<ReasonValues>(setError, FIELDS);

  const submit = handleSubmit(async (values) => {
    try {
      await onConfirm(values.reason);
      onDone();
    } catch (error) {
      onError(error);
    }
  });

  return (
    <ActionModal
      open
      title={title}
      description={description}
      okText={okText}
      danger={danger}
      loading={loading}
      onSubmit={submit}
      onCancel={onCancel}
    >
      <FormField
        id={`${ids}-reason`}
        label="Motivo"
        optional={reasonRequired ? undefined : "opcional"}
        error={formState.errors.reason?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="reason"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={REASON_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}
