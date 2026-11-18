"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Select } from "antd";
import { useId } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useCreateInvitation, type Role } from "@/features/admin-users/queries";
import { PARTNER_ROLE } from "@/features/admin-users/status";
import { PartnerSelect } from "@/features/admin-users/user-modals";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

const EMAIL_MAX = 254;
const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { error: "Escribe el correo." })
    .max(EMAIL_MAX, { error: `Máximo ${EMAIL_MAX} caracteres.` })
    .pipe(z.email({ error: "Escribe un correo válido." })),
  role: z.string().min(1, { error: "Elige el rol." }),
  partner_id: z.string(),
});
type InviteValues = z.infer<typeof schema>;
const FIELDS = ["email", "role", "partner_id"] as const;

/** Conflictos del correo (`409`): se muestran debajo del campo, no en un toast. */
const EMAIL_CONFLICTS = new Set([
  "USER_ALREADY_EXISTS",
  "INVITATION_ALREADY_PENDING",
  "USER_ALREADY_IN_PARTNER",
]);

/**
 * `POST /invitations`: correo y rol; con el rol de constructora, también la constructora
 * (la API la exige para ese rol y no la permite para los demás).
 */
export function InviteModal({
  open,
  onClose,
  onInvited,
  roles,
  rolesLoading,
}: {
  open: boolean;
  onClose: () => void;
  /** Después de enviarla (el modal ya se cerró). */
  onInvited?: () => void;
  roles: readonly Role[] | undefined;
  rolesLoading: boolean;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateInvitation();
  const { control, handleSubmit, setError, formState } = useForm<InviteValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: "", partner_id: "" },
  });
  const onFieldError = useFormErrorHandler<InviteValues>(setError, FIELDS);
  const partnerRole = useWatch({ control, name: "role" }) === PARTNER_ROLE;

  const submit = handleSubmit((values) => {
    create.mutate(
      {
        email: values.email,
        role: values.role,
        ...(partnerRole && values.partner_id ? { partner_id: values.partner_id } : {}),
      },
      {
        onSuccess: (invitation) => {
          toast.success({
            title: "Invitación enviada",
            message: `Le llegó un enlace a ${invitation.email} para definir su contraseña.`,
          });
          onClose();
          onInvited?.();
        },
        onError: (error) => {
          if (isApiError(error) && EMAIL_CONFLICTS.has(error.code)) {
            setError("email", { type: error.code, message: error.message });
            return;
          }
          if (isApiError(error) && error.code === "PARTNER_NOT_ACTIVE") {
            setError("partner_id", { type: error.code, message: error.message });
            return;
          }
          onFieldError(error);
        },
      },
    );
  });

  const options = (roles ?? [])
    .filter((role) => role.is_active)
    .map((role) => ({ value: role.code, label: role.name }));

  return (
    <ActionModal
      open={open}
      title="Invitar usuario"
      description="Le enviamos un correo con un enlace de un solo uso para que defina su nombre y su contraseña."
      okText="Enviar invitación"
      loading={create.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField id={`${ids}-email`} label="Correo" error={formState.errors.email?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="email"
            render={({ field }) => (
              <Input
                {...field}
                {...ctl}
                type="email"
                autoComplete="off"
                maxLength={EMAIL_MAX}
                placeholder="nombre@empresa.com"
              />
            )}
          />
        )}
      </FormField>
      <FormField id={`${ids}-role`} label="Rol" error={formState.errors.role?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="role"
            render={({ field }) => (
              <Select
                {...ctl}
                value={field.value || undefined}
                onChange={field.onChange}
                placeholder="Elige el rol"
                loading={rolesLoading}
                options={options}
                virtual={false}
              />
            )}
          />
        )}
      </FormField>
      {partnerRole && (
        <FormField
          id={`${ids}-partner`}
          label="Constructora"
          help="El usuario entra como miembro de esta constructora."
          error={formState.errors.partner_id?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="partner_id"
              render={({ field }) => (
                <PartnerSelect
                  value={field.value}
                  onChange={field.onChange}
                  control={ctl}
                  enabled={open}
                />
              )}
            />
          )}
        </FormField>
      )}
    </ActionModal>
  );
}
