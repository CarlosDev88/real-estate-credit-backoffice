"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Input, Select } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { Controller, useForm, type FieldNamesMarkedBoolean } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/features/applications/form-field";
import { useCatalog } from "@/features/applications/queries";
import {
  clientHref,
  DOCUMENT_TYPE_CATALOG,
  DUPLICATE_CLIENT_DOCUMENT,
  ORIGIN_CATALOG,
  type ClientCreateRequest,
  type ClientDetail,
  type ClientUpdateRequest,
} from "@/features/clients/queries";
import { applyFieldErrors, isApiError } from "@/lib/api/errors";
import { TIME_ZONE } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";

// Límites del contrato (`ClientCreateRequest`). Las reglas de negocio (formato por tipo
// de documento, duplicados) las valida la API y su error vuelve al campo.
const NAME_MAX = 120;
const DOCUMENT_MAX = 40;
const EMAIL_MAX = 254;
const PHONE_MAX = 25;

/** E.164 después de quitar espacios, paréntesis y guiones (igual que la API). */
const E164 = /^\+[1-9]\d{6,14}$/;
const DOCUMENT_CHARS = /^[A-Za-z0-9 .-]*$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Fecha de hoy ("2026-11-17") en la zona horaria de la app. */
export function todayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE }).format(now);
}

export function compactPhone(value: string): string {
  return value.replace(/[\s()-]/g, "");
}

export function makeClientSchema(today: string = todayIso()) {
  return z.object({
    document_type_code: z.string().min(1, { error: "Elige el tipo de documento." }),
    document_number: z
      .string()
      .trim()
      .min(1, { error: "Escribe el número de documento." })
      .max(DOCUMENT_MAX, { error: `Máximo ${DOCUMENT_MAX} caracteres.` })
      .regex(DOCUMENT_CHARS, { error: "Usa solo letras, dígitos, puntos o guiones." }),
    first_names: z
      .string()
      .trim()
      .min(1, { error: "Escribe los nombres." })
      .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
    last_names: z
      .string()
      .trim()
      .min(1, { error: "Escribe los apellidos." })
      .max(NAME_MAX, { error: `Máximo ${NAME_MAX} caracteres.` }),
    email: z
      .string()
      .trim()
      .max(EMAIL_MAX, { error: `Máximo ${EMAIL_MAX} caracteres.` })
      .refine((v) => v === "" || z.email().safeParse(v).success, {
        error: "Escribe un correo válido, como nombre@dominio.com.",
      }),
    phone: z
      .string()
      .trim()
      .max(PHONE_MAX, { error: `Máximo ${PHONE_MAX} caracteres.` })
      .refine((v) => v === "" || E164.test(compactPhone(v)), {
        error: "Usa el formato internacional, por ejemplo +573001234567.",
      }),
    birth_date: z
      .string()
      .refine((v) => v === "" || (ISO_DATE.test(v) && !Number.isNaN(Date.parse(v))), {
        error: "Escribe una fecha válida.",
      })
      .refine((v) => v === "" || v < today, {
        error: "La fecha de nacimiento debe ser anterior a hoy.",
      }),
    origin_type: z.string(),
  });
}

type CatalogRef = { code: string; label: string };

export type ClientFormValues = z.infer<ReturnType<typeof makeClientSchema>>;
type FieldName = keyof ClientFormValues;

export const CLIENT_FIELDS = [
  "document_type_code",
  "document_number",
  "first_names",
  "last_names",
  "email",
  "phone",
  "birth_date",
  "origin_type",
] as const satisfies readonly FieldName[];

export const EMPTY_CLIENT: ClientFormValues = {
  document_type_code: "",
  document_number: "",
  first_names: "",
  last_names: "",
  email: "",
  phone: "",
  birth_date: "",
  origin_type: "",
};

/** Valores del formulario de edición a partir del detalle. */
export function valuesFromClient(client: ClientDetail): ClientFormValues {
  return {
    document_type_code: client.document_type.code,
    document_number: client.document_number,
    first_names: client.first_names,
    last_names: client.last_names,
    email: client.email,
    phone: client.phone,
    birth_date: client.birth_date ?? "",
    origin_type: client.origin?.code ?? "",
  };
}

/** Cuerpo de `POST /clients`: los opcionales vacíos no se mandan. */
export function toCreateBody(values: ClientFormValues): ClientCreateRequest {
  const body: ClientCreateRequest = {
    document_type_code: values.document_type_code,
    document_number: values.document_number,
    first_names: values.first_names,
    last_names: values.last_names,
  };
  if (values.email) body.email = values.email;
  if (values.phone) body.phone = compactPhone(values.phone);
  if (values.birth_date) body.birth_date = values.birth_date;
  if (values.origin_type) body.origin_type = values.origin_type;
  return body;
}

/**
 * Cuerpo de `PATCH /clients/{id}`: solo lo que cambió. Vaciar un opcional lo borra
 * (correo y teléfono `""`; fecha y origen `null`).
 */
export function toUpdateBody(
  values: ClientFormValues,
  dirty: Partial<FieldNamesMarkedBoolean<ClientFormValues>>,
): ClientUpdateRequest {
  const body: ClientUpdateRequest = {};
  if (dirty.document_type_code) body.document_type_code = values.document_type_code;
  if (dirty.document_number) body.document_number = values.document_number;
  if (dirty.first_names) body.first_names = values.first_names;
  if (dirty.last_names) body.last_names = values.last_names;
  if (dirty.email) body.email = values.email;
  if (dirty.phone) body.phone = compactPhone(values.phone);
  if (dirty.birth_date) body.birth_date = values.birth_date || null;
  if (dirty.origin_type) body.origin_type = values.origin_type || null;
  return body;
}

/** Id del cliente que ya tiene ese documento, si la API lo revela (`details[].resource_id`). */
export function existingClientId(error: unknown): string | null {
  if (!isApiError(error) || error.code !== DUPLICATE_CLIENT_DOCUMENT) return null;
  return error.details.find((d) => d.resource_id)?.resource_id ?? null;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="m-0 grid gap-4 border-0 p-0">
      <legend className="text-text-primary mb-3 p-0 text-base font-semibold">{title}</legend>
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">{children}</div>
    </fieldset>
  );
}

interface ClientFormProps {
  mode: "create" | "edit";
  initial: ClientFormValues;
  /**
   * Valores actuales con su etiqueta (edición): se ofrecen aunque ya no estén activos en
   * el catálogo o mientras el catálogo carga, para que el select no muestre el código.
   */
  current?: { document_type?: CatalogRef | null; origin?: CatalogRef | null };
  /** Destino de "Cancelar". */
  cancelHref: string;
  submitting: boolean;
  /** Recibe los valores válidos y los campos cambiados; devuelve la promesa de la escritura. */
  onSubmit: (
    values: ClientFormValues,
    dirty: Partial<FieldNamesMarkedBoolean<ClientFormValues>>,
  ) => Promise<unknown>;
}

/**
 * Formulario de cliente (REQ §6 vista 5). El front valida el formato; la API, el negocio.
 * Sus errores de campo van al campo y el documento duplicado enlaza al cliente existente.
 */
export function ClientForm({
  mode,
  initial,
  current,
  cancelHref,
  submitting,
  onSubmit,
}: ClientFormProps) {
  const ids = useId();
  const router = useRouter();
  const showError = useApiErrorToast();
  const documentTypes = useCatalog(DOCUMENT_TYPE_CATALOG);
  const origins = useCatalog(ORIGIN_CATALOG);
  const [existingId, setExistingId] = useState<string | null>(null);
  const [schema] = useState(() => makeClientSchema());
  const { control, handleSubmit, setError, formState } = useForm<ClientFormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const errors = formState.errors;
  const id = (field: FieldName) => `${ids}-${field}`;

  const handleError = (error: unknown) => {
    if (isApiError(error) && error.code === DUPLICATE_CLIENT_DOCUMENT) {
      setError("document_number", { type: error.code, message: error.message });
      setExistingId(existingClientId(error));
      return;
    }
    if (!isApiError(error) || error.details.length === 0) {
      showError(error);
      return;
    }
    const leftover = applyFieldErrors(error, setError, CLIENT_FIELDS);
    if (leftover.length) showError(error, leftover);
  };

  const submit = handleSubmit(async (values) => {
    setExistingId(null);
    try {
      await onSubmit(values, formState.dirtyFields);
    } catch (error) {
      handleError(error);
    }
  });

  const options = (items: CatalogRef[], extra: CatalogRef | null | undefined) => {
    const all = extra && !items.some((i) => i.code === extra.code) ? [...items, extra] : items;
    return all.map((item) => ({ value: item.code, label: item.label }));
  };

  const text = (
    field: Exclude<FieldName, "document_type_code" | "origin_type">,
    label: string,
    extra: { optional?: boolean; help?: string; type?: string; max?: number } = {},
  ) => (
    <FormField
      id={id(field)}
      label={label}
      optional={extra.optional ? "opcional" : undefined}
      help={extra.help}
      error={errors[field]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={field}
          render={({ field: f }) => (
            <Input
              {...f}
              {...ctl}
              type={extra.type}
              maxLength={extra.max}
              aria-required={extra.optional ? undefined : true}
              max={field === "birth_date" ? todayIso() : undefined}
              autoComplete="off"
            />
          )}
        />
      )}
    </FormField>
  );

  const nothingChanged = mode === "edit" && !formState.isDirty;

  return (
    <form
      noValidate
      onSubmit={(event) => void submit(event)}
      aria-label={mode === "create" ? "Nuevo cliente" : "Editar cliente"}
      className="bg-bg-surface border-border-default grid gap-6 rounded-lg border p-4 min-[861px]:p-6"
    >
      <Section title="Identificación">
        <FormField
          id={id("document_type_code")}
          label="Tipo de documento"
          error={errors.document_type_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="document_type_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  aria-required
                  value={field.value || undefined}
                  onChange={(value: string) => {
                    setExistingId(null);
                    field.onChange(value);
                  }}
                  onBlur={field.onBlur}
                  placeholder="Elige el tipo"
                  options={options(documentTypes.items, current?.document_type)}
                  loading={documentTypes.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <div className="grid content-start gap-1.5">
          {text("document_number", "Número de documento", { max: DOCUMENT_MAX })}
          {existingId && (
            <p className="m-0 text-sm">
              <Link href={clientHref(existingId)} className="text-text-link underline">
                Ver el cliente existente
              </Link>
            </p>
          )}
        </div>
      </Section>

      <Section title="Datos personales">
        {text("first_names", "Nombres", { max: NAME_MAX })}
        {text("last_names", "Apellidos", { max: NAME_MAX })}
        {text("birth_date", "Fecha de nacimiento", { optional: true, type: "date" })}
      </Section>

      <Section title="Contacto">
        {text("email", "Correo", { optional: true, type: "email", max: EMAIL_MAX })}
        {text("phone", "Teléfono", {
          optional: true,
          type: "tel",
          max: PHONE_MAX,
          help: "Con indicativo del país, por ejemplo +573001234567.",
        })}
      </Section>

      <Section title="Comercial">
        <FormField
          id={id("origin_type")}
          label="Origen"
          optional="opcional"
          help="Cómo llegó el cliente."
          error={errors.origin_type?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="origin_type"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={(value: string | undefined) => field.onChange(value ?? "")}
                  onBlur={field.onBlur}
                  allowClear
                  placeholder="Sin origen"
                  options={options(origins.items, current?.origin)}
                  loading={origins.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      </Section>

      <div className="border-border-default flex flex-wrap justify-end gap-2 border-t pt-4">
        <Button onClick={() => router.push(cancelHref)}>Cancelar</Button>
        <Button
          type="primary"
          htmlType="submit"
          loading={submitting}
          disabled={nothingChanged}
          title={nothingChanged ? "No hay cambios para guardar" : undefined}
        >
          {mode === "create" ? "Crear cliente" : "Guardar cambios"}
        </Button>
      </div>
    </form>
  );
}
