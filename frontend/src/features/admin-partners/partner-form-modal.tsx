"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import {
  useCreatePartner,
  useUpdatePartner,
  type Partner,
  type PartnerDetail,
} from "@/features/admin-partners/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar una constructora (`POST`/`PATCH /partners`). Zod solo revisa el formato;
// el NIT duplicado (`DUPLICATE_TAX_ID`) lo dice la API y va a su campo.

const max = (n: number) => ({ error: `Máximo ${n} caracteres.` });
const schema = z.object({
  legal_name: z.string().trim().min(1, { error: "Escribe la razón social." }).max(180, max(180)),
  trade_name: z.string().trim().max(180, max(180)),
  tax_id: z.string().trim().min(1, { error: "Escribe el NIT." }).max(30, max(30)),
  contact_name: z.string().trim().max(150, max(150)),
  contact_email: z
    .string()
    .trim()
    .max(254, max(254))
    .refine((value) => value === "" || z.email().safeParse(value).success, {
      error: "Escribe un correo válido.",
    }),
  contact_phone: z.string().trim().max(25, max(25)),
});
type PartnerValues = z.infer<typeof schema>;
const FIELDS = [
  "legal_name",
  "trade_name",
  "tax_id",
  "contact_name",
  "contact_email",
  "contact_phone",
] as const;
const EDITABLE = FIELDS.filter((field) => field !== "tax_id");

const EMPTY: PartnerValues = {
  legal_name: "",
  trade_name: "",
  tax_id: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
};

interface PartnerFormModalProps {
  /** Sin constructora: crear. */
  partner?: PartnerDetail;
  onClose: () => void;
  /** Después de crearla: para abrir su panel. */
  onCreated?: (partner: Partner) => void;
}

export function PartnerFormModal({ partner, onClose, onCreated }: PartnerFormModalProps) {
  const ids = useId();
  const toast = useToast();
  const create = useCreatePartner();
  const update = useUpdatePartner(partner?.id ?? "");
  const initial: PartnerValues = partner
    ? {
        legal_name: partner.legal_name,
        trade_name: partner.trade_name,
        tax_id: partner.tax_id,
        contact_name: partner.contact_name,
        contact_email: partner.contact_email,
        contact_phone: partner.contact_phone,
      }
    : EMPTY;
  const { control, handleSubmit, setError, formState } = useForm<PartnerValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<PartnerValues>(setError, FIELDS);
  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === "DUPLICATE_TAX_ID") {
      setError("tax_id", { type: error.code, message: error.message });
      return;
    }
    onFieldError(error);
  };

  const submit = handleSubmit((values) => {
    if (!partner) {
      create.mutate(values, {
        onSuccess: (created) => {
          toast.success({ title: "Constructora creada" });
          onClose();
          onCreated?.(created);
        },
        onError,
      });
      return;
    }
    const body = Object.fromEntries(
      EDITABLE.filter((key) => values[key] !== initial[key]).map((key) => [key, values[key]]),
    );
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Datos guardados" });
        onClose();
      },
      onError,
    });
  });

  const field = (
    name: (typeof FIELDS)[number],
    label: string,
    options: { optional?: boolean; help?: string; type?: string; disabled?: boolean } = {},
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
          render={({ field: input }) => (
            <Input
              {...input}
              {...ctl}
              type={options.type ?? "text"}
              disabled={options.disabled}
              autoComplete="off"
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open
      title={partner ? "Editar constructora" : "Nueva constructora"}
      okText={partner ? "Guardar" : "Crear constructora"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={640}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {field("legal_name", "Razón social")}
        {field("trade_name", "Nombre comercial", { optional: true })}
      </div>
      {field("tax_id", "NIT", {
        disabled: !!partner,
        help: partner
          ? "El NIT identifica a la constructora y no se cambia."
          : "Con su dígito de verificación, por ejemplo 900123456-8.",
      })}
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {field("contact_name", "Contacto", { optional: true })}
        {field("contact_phone", "Teléfono del contacto", { optional: true, type: "tel" })}
      </div>
      {field("contact_email", "Correo del contacto", { optional: true, type: "email" })}
    </ActionModal>
  );
}
