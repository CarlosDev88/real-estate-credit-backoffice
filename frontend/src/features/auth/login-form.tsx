"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input } from "antd";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { EyeIcon, LockIcon, MailIcon } from "@/components/ui/icons";
import { applyFieldErrors, isApiError, retryAfterMessage } from "@/lib/api/errors";
import type { LoginResponse } from "@/features/auth/queries";
import { useLogin } from "@/features/auth/queries";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { error: "Escribe tu correo." })
    .pipe(z.email({ error: "Escribe un correo válido." })),
  password: z.string().min(1, { error: "Escribe tu contraseña." }),
});

type LoginValues = z.infer<typeof schema>;
const FIELDS = ["email", "password"] as const;

interface FormError {
  title: string;
  description?: string;
  /** Credenciales inválidas: los dos campos quedan inválidos, sin decir cuál falló. */
  credentials?: boolean;
}

const ALERT_ID = "login-error";

/** Traduce el error del login al aviso del formulario (mockup `login.html`). */
function toFormError(error: unknown, leftover: string | null): FormError {
  if (!isApiError(error)) return { title: "Ocurrió un error inesperado. Inténtalo de nuevo." };
  if (error.code === "INVALID_CREDENTIALS") {
    return {
      title: error.message,
      description: "Revisa tus datos. Tras 5 intentos fallidos el acceso se bloquea 15 minutos.",
      credentials: true,
    };
  }
  if (error.status === 429) {
    return { title: error.message, description: retryAfterMessage(error.retryAfter) };
  }
  return { title: error.message, description: leftover ?? undefined };
}

export function LoginForm({ onSuccess }: { onSuccess: (data: LoginResponse) => void }) {
  const login = useLogin();
  const [formError, setFormError] = useState<FormError | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const submit = handleSubmit((values) => {
    setFormError(null);
    login.mutate(values, {
      onSuccess,
      onError: (error) => {
        const leftover = isApiError(error) ? applyFieldErrors(error, setError, FIELDS) : [];
        const extra = leftover.map((d) => d.message).join(" ") || null;
        setFormError(toFormError(error, extra));
      },
    });
  });

  const describedBy = (field: (typeof FIELDS)[number]) =>
    [errors[field] ? `${field}-error` : null, formError?.credentials ? ALERT_ID : null]
      .filter(Boolean)
      .join(" ") || undefined;
  const invalid = (field: (typeof FIELDS)[number]) => !!errors[field] || !!formError?.credentials;

  return (
    <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-5">
      {formError && (
        <Alert
          id={ALERT_ID}
          type="error"
          showIcon
          title={formError.title}
          description={formError.description}
        />
      )}

      <div className="grid gap-1.5">
        <label htmlFor="email" className="text-sm font-medium">
          Correo
        </label>
        <Controller
          control={control}
          name="email"
          render={({ field }) => (
            <Input
              {...field}
              id="email"
              type="email"
              size="large"
              autoComplete="username"
              placeholder="nombre@empresa.com"
              prefix={<MailIcon className="text-text-tertiary" />}
              status={invalid("email") ? "error" : undefined}
              aria-invalid={invalid("email")}
              aria-describedby={describedBy("email")}
            />
          )}
        />
        {errors.email && (
          <p id="email-error" className="text-tone-danger-fg m-0 text-sm">
            {errors.email.message}
          </p>
        )}
      </div>

      <div className="grid gap-1.5">
        <label htmlFor="password" className="text-sm font-medium">
          Contraseña
        </label>
        <Controller
          control={control}
          name="password"
          render={({ field }) => (
            <Input
              {...field}
              id="password"
              type={showPassword ? "text" : "password"}
              size="large"
              autoComplete="current-password"
              prefix={<LockIcon className="text-text-tertiary" />}
              suffix={
                <Button
                  type="text"
                  size="small"
                  icon={<EyeIcon />}
                  aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((v) => !v)}
                />
              }
              status={invalid("password") ? "error" : undefined}
              aria-invalid={invalid("password")}
              aria-describedby={describedBy("password")}
            />
          )}
        />
        {errors.password && (
          <p id="password-error" className="text-tone-danger-fg m-0 text-sm">
            {errors.password.message}
          </p>
        )}
      </div>

      <Button type="primary" htmlType="submit" size="large" block loading={login.isPending}>
        {login.isPending ? "Ingresando…" : "Ingresar"}
      </Button>
    </form>
  );
}
