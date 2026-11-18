"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input, Select } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useBuyerCatalog, useBuyerWithdraw } from "@/features/buyer-portal/queries";
import { useToast } from "@/providers/toast";

/** Máximo de `comment` (contrato de `WithdrawalRequest`). */
const COMMENT_MAX = 2000;
export const WITHDRAWAL_CATALOG = "application_withdrawal_reason";

const schema = z.object({
  reason_code: z.string({ error: "Elige el motivo." }).min(1, { error: "Elige el motivo." }),
  comment: z.string().max(COMMENT_MAX, { error: `Máximo ${COMMENT_MAX} caracteres.` }),
  confirmed: z.boolean().refine((value) => value, {
    error: "Confirma que entiendes que tu solicitud se cerrará.",
  }),
});
type Values = z.input<typeof schema>;
const FIELDS = ["reason_code", "comment"] as const;

interface WithdrawModalProps {
  applicationId: string;
  version: number;
  open: boolean;
  onClose: () => void;
}

/** "Ya no quiero continuar con la solicitud": motivo, comentario y confirmación explícita. */
export function WithdrawModal({ applicationId, version, open, onClose }: WithdrawModalProps) {
  const id = useId();
  const reasons = useBuyerCatalog(WITHDRAWAL_CATALOG, null, open);
  const withdraw = useBuyerWithdraw(applicationId);
  const toast = useToast();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { reason_code: "", comment: "", confirmed: false },
  });
  const onApiError = useFormErrorHandler<Values>(form.setError, FIELDS);
  const { errors } = form.formState;

  const close = () => {
    form.reset();
    onClose();
  };

  const submit = form.handleSubmit((values) =>
    withdraw.mutate(
      {
        reason_code: values.reason_code,
        expected_version: version,
        comment: values.comment.trim(),
      },
      {
        onSuccess: () => {
          toast.success({ title: "Cerramos tu solicitud" });
          close();
        },
        onError: onApiError,
      },
    ),
  );

  return (
    <ActionModal
      open={open}
      title="¿Ya no quieres continuar?"
      okText="Cerrar mi solicitud"
      cancelText="Volver"
      danger
      loading={withdraw.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      {/* Texto de 14 px (el del portal), por eso no va en `description`. */}
      <p className="text-text-secondary m-0">
        Si cierras tu solicitud, tu asesor ya no podrá seguir con el trámite. Podrás consultarla,
        pero no hacer cambios.
      </p>
      <FormField id={`${id}-reason`} label="Motivo" error={errors.reason_code?.message}>
        {(control) => (
          <Controller
            control={form.control}
            name="reason_code"
            render={({ field }) => (
              <Select
                {...control}
                value={field.value || undefined}
                onChange={field.onChange}
                onBlur={field.onBlur}
                size="large"
                placeholder="Elige el motivo"
                loading={reasons.isPending}
                options={reasons.items.map((item) => ({ value: item.code, label: item.label }))}
              />
            )}
          />
        )}
      </FormField>
      <FormField
        id={`${id}-comment`}
        label="Comentario"
        optional="opcional"
        error={errors.comment?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="comment"
            render={({ field }) => (
              <Input.TextArea {...control} {...field} rows={3} maxLength={COMMENT_MAX} />
            )}
          />
        )}
      </FormField>
      <div className="grid gap-1.5">
        <Controller
          control={form.control}
          name="confirmed"
          render={({ field }) => (
            <Checkbox
              id={`${id}-confirm`}
              checked={field.value}
              onChange={(event) => field.onChange(event.target.checked)}
              aria-invalid={errors.confirmed ? true : undefined}
              aria-describedby={errors.confirmed ? `${id}-confirm-error` : undefined}
            >
              Entiendo que mi solicitud se cerrará
            </Checkbox>
          )}
        />
        {errors.confirmed && (
          <p id={`${id}-confirm-error`} className="text-tone-danger-fg m-0 text-sm">
            {errors.confirmed.message}
          </p>
        )}
      </div>
    </ActionModal>
  );
}
