"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useForm, type Path } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField } from "@/components/ui/form-field";
import { useCatalog } from "@/features/applications/queries";
import {
  DUPLICATE_CLIENT_DOCUMENT,
  DUPLICATE_OPPORTUNITY,
  ProspectError,
  useCreateProspect,
} from "@/features/broker/queries";
import { optionsOf } from "@/features/clients/catalog-options";
import { compactPhone, makeClientSchema } from "@/features/clients/client-form";
import { useActiveProjects } from "@/features/clients/detail-queries";
import { DOCUMENT_TYPE_CATALOG } from "@/features/clients/queries";
import { applyFieldErrors, isApiError } from "@/lib/api/errors";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

/** Límite del contrato (`OpportunityCreateRequest.notes`). */
export const NOTES_MAX = 2000;

const prospectSchema = makeClientSchema()
  .omit({ birth_date: true, origin_type: true })
  .extend({
    project_id: z.string(),
    notes: z
      .string()
      .trim()
      .max(NOTES_MAX, { error: `Máximo ${NOTES_MAX} caracteres.` }),
  });
type ProspectValues = z.infer<typeof prospectSchema>;

const EMPTY: ProspectValues = {
  document_type_code: "",
  document_number: "",
  first_names: "",
  last_names: "",
  email: "",
  phone: "",
  project_id: "",
  notes: "",
};
const CLIENT_FIELDS = [
  "document_type_code",
  "document_number",
  "first_names",
  "last_names",
  "email",
  "phone",
] as const;
const OPPORTUNITY_FIELDS = ["project_id", "notes"] as const;

/**
 * "Nuevo prospecto" del broker: datos de contacto del cliente, el proyecto y una nota.
 * Crea el cliente y su oportunidad con origen broker; queda `NEW` hasta que se le asigne
 * un asesor.
 */
export function ProspectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ids = useId();
  const toast = useToast();
  const showError = useApiErrorToast();
  const create = useCreateProspect();
  const documentTypes = useCatalog(DOCUMENT_TYPE_CATALOG);
  const projects = useActiveProjects(open);
  // Si el cliente se creó y la oportunidad falló, el reintento no lo vuelve a crear.
  const [createdClient, setCreatedClient] = useState<string | null>(null);
  const { control, handleSubmit, setError, reset, formState } = useForm<ProspectValues>({
    resolver: zodResolver(prospectSchema),
    defaultValues: EMPTY,
  });
  const errors = formState.errors;

  const close = () => {
    reset(EMPTY);
    setCreatedClient(null);
    onClose();
  };

  const onError = (error: unknown) => {
    let cause = error;
    let fields: readonly Path<ProspectValues>[] = CLIENT_FIELDS;
    if (error instanceof ProspectError) {
      setCreatedClient(error.clientId);
      cause = error.reason;
      fields = OPPORTUNITY_FIELDS;
      if (isApiError(cause) && cause.code === DUPLICATE_OPPORTUNITY) {
        setError("project_id", { type: cause.code, message: cause.message });
        return;
      }
    } else if (isApiError(cause) && cause.code === DUPLICATE_CLIENT_DOCUMENT) {
      // Existe, pero el broker no lo ve: el mensaje de la API va al documento.
      setError("document_number", { type: cause.code, message: cause.message });
      return;
    }
    if (!isApiError(cause) || cause.details.length === 0) return showError(cause);
    const leftover = applyFieldErrors(cause, setError, fields);
    if (leftover.length) showError(cause, leftover);
  };

  const submit = handleSubmit((values) => {
    create.mutate(
      {
        clientId: createdClient,
        client: {
          document_type_code: values.document_type_code,
          document_number: values.document_number.trim(),
          first_names: values.first_names.trim(),
          last_names: values.last_names.trim(),
          ...(values.email.trim() ? { email: values.email.trim() } : {}),
          ...(values.phone.trim() ? { phone: compactPhone(values.phone.trim()) } : {}),
        },
        project_id: values.project_id || null,
        notes: values.notes.trim(),
      },
      {
        onSuccess: ({ existing }) => {
          toast.success({
            title: "Prospecto registrado",
            message: existing
              ? "El cliente ya existía: se le agregó la oportunidad."
              : "Queda nuevo hasta que se le asigne un asesor.",
          });
          close();
        },
        onError,
      },
    );
  });

  const text = (
    name: "document_number" | "first_names" | "last_names" | "email" | "phone",
    label: string,
    extra: { optional?: boolean; type?: string; help?: string } = {},
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={extra.optional ? "opcional" : undefined}
      help={extra.help}
      error={errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Input
              {...field}
              {...ctl}
              type={extra.type}
              // Con el cliente ya creado, sus datos no cambian en el reintento.
              disabled={!!createdClient}
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open={open}
      title="Nuevo prospecto"
      width={600}
      description="Registra el contacto del comprador. El equipo le asigna un asesor y lo ves aquí con su estado."
      okText={createdClient ? "Reintentar" : "Registrar prospecto"}
      loading={create.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-document-type`}
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
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el tipo"
                  options={optionsOf(documentTypes.items)}
                  loading={documentTypes.isPending}
                  disabled={!!createdClient}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        {text("document_number", "Número de documento")}
        {text("first_names", "Nombres")}
        {text("last_names", "Apellidos")}
        {text("email", "Correo", { optional: true, type: "email" })}
        {text("phone", "Celular", {
          optional: true,
          type: "tel",
          help: "Con indicativo, por ejemplo +573001234567.",
        })}
      </div>
      <FormField
        id={`${ids}-project`}
        label="Proyecto"
        optional="opcional"
        help="Solo proyectos activos."
        error={errors.project_id?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="project_id"
            render={({ field }) => (
              <Select
                {...ctl}
                value={field.value || undefined}
                onChange={(value: string | undefined) => field.onChange(value ?? "")}
                allowClear
                placeholder="Sin proyecto"
                showSearch={{ optionFilterProp: "label" }}
                options={(projects.data ?? []).map((project) => ({
                  value: project.id,
                  label: `${project.name} · ${project.partner.name}`,
                }))}
                loading={projects.isPending}
              />
            )}
          />
        )}
      </FormField>
      <FormField
        id={`${ids}-notes`}
        label="Nota para el asesor"
        optional="opcional"
        error={errors.notes?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="notes"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={NOTES_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}
