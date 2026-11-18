"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Radio, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useAddMember, useMemberCandidates } from "@/features/admin-partners/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

/**
 * Rol de constructora: el contrato lo nombra (`POST /partners/{id}/members` invita con ese
 * rol). Aquí solo filtra los usuarios que se pueden agregar.
 */
const PARTNER_ROLE = "CONSTRUCTION_PARTNER";

type Mode = "email" | "user";

const schema = z
  .object({
    mode: z.enum(["email", "user"]),
    email: z.string().trim().max(254, { error: "Máximo 254 caracteres." }),
    user_id: z.string(),
    job_title: z.string().trim().max(120, { error: "Máximo 120 caracteres." }),
    started_at: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.mode === "email") {
      if (!values.email)
        ctx.addIssue({ code: "custom", path: ["email"], message: "Escribe el correo." });
      else if (!z.email().safeParse(values.email).success)
        ctx.addIssue({ code: "custom", path: ["email"], message: "Escribe un correo válido." });
    } else if (!values.user_id) {
      ctx.addIssue({ code: "custom", path: ["user_id"], message: "Elige el usuario." });
    }
  });
type MemberValues = z.infer<typeof schema>;
const FIELDS = ["email", "user_id", "job_title", "started_at"] as const;

/** Conflictos (`409`/`422`) que se explican debajo del campo de la persona. */
const PERSON_CONFLICTS = new Set([
  "USER_ALREADY_IN_PARTNER",
  "USER_ALREADY_EXISTS",
  "INVITATION_ALREADY_PENDING",
  "USER_NOT_ELIGIBLE",
]);

/**
 * Agregar un miembro: invitar por correo (le llega una invitación de constructora) o, con
 * `users.read`, agregar un usuario de constructora que ya existe, con cargo y fecha.
 */
export function MemberModal({
  partnerId,
  partnerLabel,
  canPickUsers,
  onClose,
}: {
  partnerId: string;
  partnerLabel: string;
  /** `users.read`: puede buscar usuarios existentes. */
  canPickUsers: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const add = useAddMember(partnerId);
  const [search, setSearch] = useState("");
  const { control, handleSubmit, setError, formState } = useForm<MemberValues>({
    resolver: zodResolver(schema),
    defaultValues: { mode: "email", email: "", user_id: "", job_title: "", started_at: "" },
  });
  const mode = useWatch({ control, name: "mode" }) as Mode;
  const candidates = useMemberCandidates(PARTNER_ROLE, search, canPickUsers && mode === "user");
  const onFieldError = useFormErrorHandler<MemberValues>(setError, FIELDS);

  const submit = handleSubmit((values) => {
    const body =
      values.mode === "email"
        ? { email: values.email, job_title: "" }
        : {
            user_id: values.user_id,
            job_title: values.job_title,
            started_at: values.started_at || null,
          };
    add.mutate(body, {
      onSuccess: ({ invited }) => {
        toast.success(
          invited
            ? {
                title: "Invitación enviada",
                message: `Cuando ${values.email} la acepte, queda como miembro de ${partnerLabel}.`,
              }
            : { title: "Miembro agregado" },
        );
        onClose();
      },
      onError: (error) => {
        if (isApiError(error) && PERSON_CONFLICTS.has(error.code)) {
          setError(values.mode === "email" ? "email" : "user_id", {
            type: error.code,
            message: error.message,
          });
          return;
        }
        onFieldError(error);
      },
    });
  });

  return (
    <ActionModal
      open
      title="Agregar miembro"
      description={`Las personas de ${partnerLabel} ven y editan los proyectos de su constructora.`}
      okText={mode === "email" ? "Enviar invitación" : "Agregar miembro"}
      loading={add.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      {canPickUsers && (
        <Controller
          control={control}
          name="mode"
          render={({ field }) => (
            <Radio.Group
              value={field.value}
              onChange={(event) => field.onChange(event.target.value)}
              aria-label="Cómo agregar al miembro"
              options={[
                { value: "email", label: "Invitar por correo" },
                { value: "user", label: "Agregar un usuario existente" },
              ]}
            />
          )}
        />
      )}

      {mode === "email" ? (
        <FormField
          id={`${ids}-email`}
          label="Correo"
          help="Le llega un enlace para definir su contraseña; entra con el rol de constructora."
          error={formState.errors.email?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="email"
              render={({ field }) => (
                <Input {...field} {...ctl} type="email" autoComplete="off" maxLength={254} />
              )}
            />
          )}
        </FormField>
      ) : (
        <>
          <FormField
            id={`${ids}-user`}
            label="Usuario"
            help="Usuarios activos con el rol de constructora."
            error={formState.errors.user_id?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="user_id"
                render={({ field }) => (
                  <Select
                    {...ctl}
                    value={field.value || undefined}
                    onChange={field.onChange}
                    placeholder="Busca por nombre o correo"
                    showSearch={{ filterOption: false, onSearch: setSearch }}
                    loading={candidates.isFetching}
                    notFoundContent={candidates.isPending ? "Cargando…" : "No hay usuarios"}
                    options={(candidates.data ?? []).map((user) => ({
                      value: user.id,
                      label: user.name ? `${user.name} · ${user.email}` : user.email,
                    }))}
                  />
                )}
              />
            )}
          </FormField>
          <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
            <FormField
              id={`${ids}-job`}
              label="Cargo"
              optional="opcional"
              error={formState.errors.job_title?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name="job_title"
                  render={({ field }) => <Input {...field} {...ctl} maxLength={120} />}
                />
              )}
            </FormField>
            <FormField
              id={`${ids}-start`}
              label="Desde"
              optional="opcional"
              help="Sin fecha, desde hoy."
              error={formState.errors.started_at?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name="started_at"
                  render={({ field }) => <Input {...field} {...ctl} type="date" />}
                />
              )}
            </FormField>
          </div>
        </>
      )}
    </ActionModal>
  );
}
