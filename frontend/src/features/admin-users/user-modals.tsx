"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input } from "antd";
import { useId } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { PartnerSelect } from "@/features/admin-common/partner-select";
import {
  useReplaceRoles,
  useRoles,
  useSetUserActive,
  useUpdateUser,
  type User,
} from "@/features/admin-users/queries";
import { PARTNER_ROLE } from "@/features/admin-users/status";
import { useToast } from "@/providers/toast";

// Modales del panel de un usuario: editar sus datos, cambiar sus roles y activarlo o
// desactivarlo. Zod solo revisa el formato; las reglas (roles que no se combinan, la
// constructora obligatoria) las decide la API y su error va al campo.

interface UserModalProps {
  user: User;
  open: boolean;
  onClose: () => void;
}

// ---------- editar ----------

const NAME_MAX = 100;
const PHONE_MAX = 25;
const editSchema = z.object({
  first_name: z
    .string()
    .trim()
    .min(1, { error: "Escribe el nombre." })
    .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
  last_name: z
    .string()
    .trim()
    .min(1, { error: "Escribe el apellido." })
    .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
  phone: z
    .string()
    .trim()
    .max(PHONE_MAX, { error: `Máximo ${PHONE_MAX} caracteres.` }),
});
type EditValues = z.infer<typeof editSchema>;
const EDIT_FIELDS = ["first_name", "last_name", "phone"] as const;

/** `PATCH /users/{id}`: nombre, apellido y teléfono (el correo no se edita). */
export function EditUserModal({ user, open, onClose }: UserModalProps) {
  const ids = useId();
  const toast = useToast();
  const update = useUpdateUser(user.id);
  const initial: EditValues = {
    first_name: user.first_name,
    last_name: user.last_name,
    phone: user.phone,
  };
  const { control, handleSubmit, setError, formState } = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: initial,
  });
  const onError = useFormErrorHandler<EditValues>(setError, EDIT_FIELDS);

  const submit = handleSubmit((values) => {
    // Solo los campos que cambiaron.
    const body = Object.fromEntries(
      EDIT_FIELDS.filter((key) => values[key] !== initial[key]).map((key) => [key, values[key]]),
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

  const text = (name: (typeof EDIT_FIELDS)[number], label: string, max: number, opt?: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={opt}
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
              maxLength={max}
              type={name === "phone" ? "tel" : "text"}
              autoComplete={
                name === "phone" ? "off" : name === "first_name" ? "given-name" : "family-name"
              }
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open={open}
      title="Editar usuario"
      description={`El correo (${user.email}) identifica al usuario y no se cambia.`}
      okText="Guardar"
      loading={update.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {text("first_name", "Nombre", NAME_MAX)}
        {text("last_name", "Apellido", NAME_MAX)}
      </div>
      {text("phone", "Teléfono", PHONE_MAX, "opcional")}
    </ActionModal>
  );
}

// ---------- roles ----------

const rolesSchema = z.object({
  role_codes: z.array(z.string()).min(1, { error: "Elige al menos un rol." }),
  partner_id: z.string(),
});
type RolesValues = z.infer<typeof rolesSchema>;
const ROLES_FIELDS = ["role_codes", "partner_id"] as const;

/**
 * `PUT /users/{id}/roles`: reemplaza los roles. Si queda con el rol de constructora y aún
 * no es miembro de ninguna, se elige la constructora (la API crea la membresía).
 */
export function RolesModal({ user, open, onClose }: UserModalProps) {
  const ids = useId();
  const toast = useToast();
  const roles = useRoles(open);
  const replace = useReplaceRoles(user.id);
  const { control, handleSubmit, setError, formState } = useForm<RolesValues>({
    resolver: zodResolver(rolesSchema),
    defaultValues: { role_codes: user.roles, partner_id: "" },
  });
  const onError = useFormErrorHandler<RolesValues>(setError, ROLES_FIELDS);
  const selected = useWatch({ control, name: "role_codes" });
  const needsPartner = selected.includes(PARTNER_ROLE) && !user.partner;

  // Los roles inactivos solo se ven si el usuario ya los tiene.
  const options = (roles.data ?? []).filter(
    (role) => role.is_active || user.roles.includes(role.code),
  );

  const submit = handleSubmit((values) => {
    replace.mutate(
      {
        role_codes: values.role_codes,
        ...(needsPartner && values.partner_id ? { partner_id: values.partner_id } : {}),
      },
      {
        onSuccess: () => {
          toast.success({ title: "Roles actualizados" });
          onClose();
        },
        onError,
      },
    );
  });

  const rolesError = formState.errors.role_codes?.message;
  const errorId = `${ids}-roles-error`;

  return (
    <ActionModal
      open={open}
      title="Cambiar roles"
      description={`Los permisos de ${user.name || user.email} salen de sus roles. El cambio aplica en su próxima acción.`}
      okText="Guardar roles"
      loading={replace.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={560}
    >
      <fieldset
        className="m-0 grid gap-2 border-0 p-0"
        aria-describedby={rolesError ? errorId : undefined}
        aria-invalid={rolesError ? true : undefined}
      >
        <legend className="mb-1.5 p-0 text-sm font-medium">Roles</legend>
        {roles.isPending ? (
          <p role="status" className="text-text-tertiary m-0 text-sm">
            Cargando roles…
          </p>
        ) : roles.isError ? (
          <p role="alert" className="text-tone-danger-fg m-0 text-sm">
            No pudimos cargar los roles. {roles.error.message}
          </p>
        ) : (
          <Controller
            control={control}
            name="role_codes"
            render={({ field }) => (
              <div className="grid gap-2">
                {options.map((role) => (
                  <Checkbox
                    key={role.code}
                    checked={field.value.includes(role.code)}
                    onChange={(event) =>
                      field.onChange(
                        event.target.checked
                          ? [...field.value, role.code]
                          : field.value.filter((code) => code !== role.code),
                      )
                    }
                  >
                    <span className="font-medium">{role.name}</span>
                    {role.description && (
                      <span className="text-text-tertiary block text-xs">{role.description}</span>
                    )}
                  </Checkbox>
                ))}
              </div>
            )}
          />
        )}
        {rolesError && (
          <p id={errorId} className="text-tone-danger-fg m-0 text-sm">
            {rolesError}
          </p>
        )}
      </fieldset>

      {needsPartner && (
        <FormField
          id={`${ids}-partner`}
          label="Constructora"
          help="El usuario queda como miembro de esta constructora."
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

// ---------- activar o desactivar ----------

const REASON_MAX = 1000;
const statusSchema = (required: boolean) =>
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
type StatusValues = { reason: string };
const STATUS_FIELDS = ["reason"] as const;

/**
 * Activar (motivo opcional) o desactivar (motivo obligatorio, acción destructiva: cierra
 * sus sesiones y revoca sus invitaciones pendientes).
 */
export function StatusModal({
  user,
  open,
  onClose,
  activate,
}: UserModalProps & { activate: boolean }) {
  const ids = useId();
  const toast = useToast();
  const setActive = useSetUserActive(user.id);
  const { control, handleSubmit, setError, formState } = useForm<StatusValues>({
    resolver: zodResolver(statusSchema(!activate)),
    defaultValues: { reason: "" },
  });
  const onError = useFormErrorHandler<StatusValues>(setError, STATUS_FIELDS);
  const who = user.name || user.email;

  const submit = handleSubmit((values) => {
    setActive.mutate(
      { active: activate, reason: values.reason },
      {
        onSuccess: () => {
          toast.success({ title: activate ? "Usuario activado" : "Usuario desactivado" });
          onClose();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={open}
      title={activate ? "Activar usuario" : "Desactivar usuario"}
      description={
        activate
          ? `${who} podrá volver a ingresar con su contraseña.`
          : `${who} pierde el acceso de inmediato: se cierran sus sesiones y se revocan sus invitaciones pendientes.`
      }
      okText={activate ? "Activar" : "Desactivar"}
      danger={!activate}
      loading={setActive.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField
        id={`${ids}-reason`}
        label="Motivo"
        optional={activate ? "opcional" : undefined}
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
