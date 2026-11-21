"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input } from "antd";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/ui/form-field";
import { ASK_AGAIN, LoginLink, Notice } from "@/features/admin-users/accept-invitation-parts";
import { useAcceptInvitation, type AcceptedUser } from "@/features/admin-users/queries";
import { applyFieldErrors, isApiError, retryAfterMessage } from "@/lib/api/errors";

// Formulario de "Activa tu cuenta". Va en su propio módulo para que `/aceptar-invitacion`
// sin token (o con la invitación ya aceptada) no cargue Zod ni react-hook-form (PERF-08).

const NAME_MAX = 100;
const PASSWORD_MAX = 128;
const schema = z
  .object({
    first_name: z
      .string()
      .trim()
      .min(1, { error: "Escribe tu nombre." })
      .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
    last_name: z
      .string()
      .trim()
      .min(1, { error: "Escribe tu apellido." })
      .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
    password: z
      .string()
      .min(1, { error: "Escribe una contraseña." })
      .max(PASSWORD_MAX, { error: `Máximo ${PASSWORD_MAX} caracteres.` }),
    password_confirmation: z.string().min(1, { error: "Repite la contraseña." }),
  })
  .refine((values) => values.password === values.password_confirmation, {
    path: ["password_confirmation"],
    error: "Las contraseñas no coinciden.",
  });
type AcceptValues = z.infer<typeof schema>;
const FIELDS = ["first_name", "last_name", "password", "password_confirmation"] as const;

/** Errores que dejan la invitación inservible: se muestra su pantalla en lugar del formulario. */
const DEAD_ENDS: Record<string, { title: string; login?: boolean }> = {
  INVITATION_INVALID: { title: "Esta invitación ya no sirve" },
  USER_ALREADY_EXISTS: { title: "Ya tienes una cuenta", login: true },
  USER_ALREADY_IN_PARTNER: { title: "No pudimos activar tu cuenta" },
  PARTNER_NOT_ACTIVE: { title: "No pudimos activar tu cuenta" },
};

function PasswordInput(props: {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  name: string;
  control: object;
  autoComplete: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <Input.Password
      {...props.control}
      name={props.name}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
      onBlur={props.onBlur}
      size="large"
      maxLength={PASSWORD_MAX}
      autoComplete={props.autoComplete}
      visibilityToggle={{ visible, onVisibleChange: setVisible }}
    />
  );
}

export function AcceptForm({
  token,
  onAccepted,
}: {
  token: string;
  onAccepted: (user: AcceptedUser) => void;
}) {
  const ids = useId();
  const accept = useAcceptInvitation();
  const [alert, setAlert] = useState<{ title: string; description?: string } | null>(null);
  const [deadEnd, setDeadEnd] = useState<{
    title: string;
    message: string;
    login?: boolean;
  } | null>(null);
  const { control, handleSubmit, setError, formState } = useForm<AcceptValues>({
    resolver: zodResolver(schema),
    defaultValues: { first_name: "", last_name: "", password: "", password_confirmation: "" },
  });

  const submit = handleSubmit((values) => {
    setAlert(null);
    accept.mutate(
      { token, ...values },
      {
        onSuccess: onAccepted,
        onError: (error) => {
          if (!isApiError(error)) {
            setAlert({ title: "Ocurrió un error inesperado. Inténtalo de nuevo." });
            return;
          }
          const end = DEAD_ENDS[error.code];
          if (end) {
            setDeadEnd({ ...end, message: error.message });
            return;
          }
          if (error.status === 429) {
            setAlert({ title: error.message, description: retryAfterMessage(error.retryAfter) });
            return;
          }
          // La política de contraseñas y los demás errores de campo van debajo de su campo.
          const leftover = applyFieldErrors(error, setError, FIELDS);
          if (error.details.length === 0 || leftover.length > 0) {
            setAlert({
              title: error.message,
              description: leftover.map((d) => d.message).join(" ") || undefined,
            });
          }
        },
      },
    );
  });

  if (deadEnd) {
    return (
      <Notice title={deadEnd.title} role="alert">
        <p className="text-text-secondary m-0">{deadEnd.message}</p>
        {deadEnd.login ? <LoginLink /> : <p className="text-text-secondary m-0">{ASK_AGAIN}</p>}
      </Notice>
    );
  }

  const text = (name: "first_name" | "last_name", label: string, autoComplete: string) => (
    <FormField id={`${ids}-${name}`} label={label} error={formState.errors[name]?.message}>
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Input
              {...field}
              {...ctl}
              size="large"
              maxLength={NAME_MAX}
              autoComplete={autoComplete}
            />
          )}
        />
      )}
    </FormField>
  );

  const password = (name: "password" | "password_confirmation", label: string, help?: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      help={help}
      error={formState.errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <PasswordInput
              name={field.name}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              control={ctl}
              autoComplete="new-password"
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <h1 className="m-0 text-3xl font-semibold tracking-tight">Activa tu cuenta</h1>
        <p className="text-text-secondary m-0">
          Te invitaron al backoffice de Umbral. Escribe tu nombre y define tu contraseña.
        </p>
      </div>
      <form noValidate onSubmit={(event) => void submit(event)} className="grid gap-5">
        {alert && (
          <Alert type="error" showIcon title={alert.title} description={alert.description} />
        )}
        <div className="grid items-start gap-5 min-[600px]:grid-cols-2">
          {text("first_name", "Nombre", "given-name")}
          {text("last_name", "Apellido", "family-name")}
        </div>
        {password(
          "password",
          "Contraseña",
          "Si no cumple la política de seguridad, te decimos qué le falta.",
        )}
        {password("password_confirmation", "Repite la contraseña")}
        <Button type="primary" htmlType="submit" size="large" block loading={accept.isPending}>
          {accept.isPending ? "Activando…" : "Activar mi cuenta"}
        </Button>
      </form>
    </div>
  );
}
