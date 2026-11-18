"use client";

// Ejemplos vivos de los patrones (src/stories/patrones/*.mdx). Usan los componentes de la
// librería y simulan la API: no llaman al backend.

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Button, Input, Segmented, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Card, DataList, Datum } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { FilterChips } from "@/components/ui/filter-chips";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { SearchIcon } from "@/components/ui/icons";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// ---------- formulario con validación y error de la API ----------

const clientSchema = z.object({
  full_name: z.string().trim().min(1, { error: "Escribe el nombre completo." }),
  email: z.email({ error: "Escribe un correo válido, por ejemplo nombre@dominio.co." }),
  document_number: z
    .string()
    .regex(/^\d{6,10}$/, { error: "El documento tiene de 6 a 10 dígitos, sin puntos." }),
});
type ClientValues = z.infer<typeof clientSchema>;
const CLIENT_FIELDS = ["full_name", "email", "document_number"] as const;

/** La "API" responde 422: un detalle con campo (va al campo) y otro sin campo (va al toast). */
function fakeCreateClient(values: ClientValues): Promise<void> {
  return new Promise((resolve, reject) =>
    setTimeout(() => {
      if (values.document_number === "1032445908") {
        reject(
          new ApiError(
            422,
            "VALIDATION_ERROR",
            "Revisa los datos del cliente.",
            [
              {
                field: "document_number",
                code: "DUPLICATE",
                message: "Ya existe un cliente con este documento.",
              },
              { field: null, code: "WARNING", message: "El correo no se pudo verificar." },
            ],
            "req-7f3a",
          ),
        );
      } else resolve();
    }, 600),
  );
}

export function FormPattern() {
  const ids = useId();
  const toast = useToast();
  const { control, handleSubmit, setError, formState, reset } = useForm<ClientValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: { full_name: "", email: "", document_number: "1032445908" },
  });
  const onError = useFormErrorHandler<ClientValues>(setError, CLIENT_FIELDS);
  const create = useMutation({
    mutationFn: fakeCreateClient,
    // El formulario maneja su propio error: sin el toast global de escritura.
    meta: { handlesErrors: true },
  });

  const submit = handleSubmit((values) =>
    create.mutate(values, {
      onSuccess: () => {
        toast.success({ title: "Cliente creado" });
        reset();
      },
      onError,
    }),
  );

  const field = (name: keyof ClientValues, label: string, help?: string) => (
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
          render={({ field: f }) => <Input {...f} {...ctl} />}
        />
      )}
    </FormField>
  );

  return (
    <Card title="Nuevo cliente">
      <form noValidate onSubmit={(e) => void submit(e)} className="grid max-w-md gap-4">
        {field("full_name", "Nombre completo")}
        {field("email", "Correo", "Le enviamos el enlace de acceso a este correo.")}
        {field("document_number", "Número de documento", "Prueba con 1032445908: ya existe.")}
        <div>
          <Button type="primary" htmlType="submit" loading={create.isPending}>
            Crear cliente
          </Button>
        </div>
      </form>
    </Card>
  );
}

// ---------- lista con filtros en la URL ----------

const ORIGINS = [
  { value: "", label: "todos" },
  { value: "FAIR", label: "Feria de vivienda" },
  { value: "WEB", label: "Página web" },
  { value: "BROKER", label: "Broker" },
];

/** Como `useListParams`: el estado vive en la URL; aquí se muestra la URL que quedaría. */
export function ListFiltersPattern() {
  const [search, setSearch] = useState("");
  const [origin, setOrigin] = useState("FAIR");
  const [page, setPage] = useState(2);
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  if (origin) query.set("origin", origin);
  if (page > 1) query.set("page", String(page));
  const originLabel = ORIGINS.find((o) => o.value === origin)?.label ?? "…";
  const clear = () => {
    setSearch("");
    setOrigin("");
    setPage(1);
  };

  return (
    <div className="bg-bg-surface border-border-default overflow-hidden rounded-lg border">
      <div className="border-border-default flex flex-wrap items-center gap-2 border-b p-3">
        <Input
          type="search"
          allowClear
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Nombre, documento o correo"
          aria-label="Buscar clientes por nombre, documento o correo"
          prefix={<SearchIcon className="text-text-tertiary" />}
          className="min-w-0 flex-[1_1_200px]"
        />
        <Select
          aria-label="Filtrar por origen"
          value={origin}
          onChange={(value: string) => {
            setOrigin(value);
            setPage(1);
          }}
          options={ORIGINS}
          labelRender={() => `Origen: ${originLabel}`}
          style={{ width: 220 }}
        />
        {(search || origin) && (
          <Button type="text" onClick={clear}>
            Limpiar
          </Button>
        )}
      </div>
      <FilterChips
        caption="En móvil, los filtros que no se ven van como chips:"
        chips={origin ? [{ key: "origin", label: "Origen", value: originLabel }] : []}
        onRemove={() => setOrigin("")}
      />
      <p className="text-text-secondary m-0 px-3 py-3 text-sm">
        URL: <code className="font-mono">/clientes{query.size ? `?${query}` : ""}</code>
      </p>
    </div>
  );
}

// ---------- estados vacío, cargando y error ----------

type ViewState = "cargando" | "error" | "vacio" | "datos";

export function StatesPattern() {
  const [state, setState] = useState<ViewState>("cargando");
  return (
    <div className="grid gap-3">
      <Segmented<ViewState>
        aria-label="Estado de la consulta"
        value={state}
        onChange={setState}
        options={[
          { value: "cargando", label: "Cargando" },
          { value: "error", label: "Error" },
          { value: "vacio", label: "Vacío" },
          { value: "datos", label: "Con datos" },
        ]}
      />
      {state === "cargando" && <LoadingState label="Cargando radicaciones" blocks={[128]} />}
      {state === "error" && (
        <ErrorState
          title="No pudimos cargar las radicaciones"
          message="No hay conexión con el servidor."
          onRetry={() => setState("cargando")}
        />
      )}
      {state === "vacio" && (
        <div className="bg-bg-surface border-border-default rounded-lg border">
          <EmptyState
            title="Todavía no hay radicaciones"
            description="La radicación se registra después de entregar el paquete al banco."
          />
        </div>
      )}
      {state === "datos" && (
        <Card title="Radicación #1">
          <DataList columns={3}>
            <Datum label="Canal">Correo electrónico</Datum>
            <Datum label="Referencia">
              <span className="font-mono">RAD-2026-00841</span>
            </Datum>
            <Datum label="Respuesta esperada">{null}</Datum>
          </DataList>
        </Card>
      )}
    </div>
  );
}
