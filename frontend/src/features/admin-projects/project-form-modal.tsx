"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Select } from "antd";
import { useId, useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import {
  cityOptionLabel,
  DEPARTMENT_CATALOG,
  useCatalog,
  useMunicipalities,
} from "@/features/admin-common/catalogs";
import { PartnerSelect } from "@/features/admin-common/partner-select";
import {
  useCreateProject,
  useUpdateProject,
  type ProjectDetail,
} from "@/features/admin-projects/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar un proyecto (`POST`/`PATCH /projects`). Zod solo revisa el formato. La
// constructora se elige al crear (asesor y administrador); para un usuario de constructora
// la API la toma de su membresía. Al editar no se cambia (el contrato no la recibe).

const max = (n: number) => ({ error: `Máximo ${n} caracteres.` });
const schema = (needsPartner: boolean) =>
  z.object({
    name: z.string().trim().min(1, { error: "Escribe el nombre." }).max(180, max(180)),
    code: z.string().trim().max(50, max(50)),
    partner_id: needsPartner ? z.string().min(1, { error: "Elige la constructora." }) : z.string(),
    city_code: z.string().min(1, { error: "Elige el municipio." }),
    address: z.string().trim().min(1, { error: "Escribe la dirección." }).max(255, max(255)),
    description: z.string().trim(),
    estimated_delivery_date: z.string(),
  });
type ProjectValues = z.infer<ReturnType<typeof schema>>;
const FIELDS = [
  "name",
  "code",
  "partner_id",
  "city_code",
  "address",
  "description",
  "estimated_delivery_date",
] as const;
const EDITABLE = FIELDS.filter((field) => field !== "partner_id");

/** Conflictos que se explican debajo de su campo. */
const FIELD_CONFLICTS: Record<string, (typeof FIELDS)[number]> = {
  DUPLICATE_PROJECT_NAME: "name",
  PARTNER_NOT_ACTIVE: "partner_id",
};

interface ProjectFormModalProps {
  project?: ProjectDetail;
  /** El usuario es de una constructora (`/auth/me` → `scope.partner_id`): no la elige. */
  partnerScoped: boolean;
  onClose: () => void;
  onCreated?: (project: ProjectDetail) => void;
}

export function ProjectFormModal({
  project,
  partnerScoped,
  onClose,
  onCreated,
}: ProjectFormModalProps) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateProject();
  const update = useUpdateProject(project?.id ?? "");
  const cities = useMunicipalities();
  const departments = useCatalog(DEPARTMENT_CATALOG);
  const cityOptions = useMemo(
    () =>
      cities.items.map((item) => ({
        value: item.code,
        label: cityOptionLabel(item, departments.items),
      })),
    [cities.items, departments.items],
  );
  const choosePartner = !project && !partnerScoped;

  const initial: ProjectValues = {
    name: project?.name ?? "",
    code: project?.code ?? "",
    partner_id: "",
    city_code: project?.city.code ?? "",
    address: project?.address ?? "",
    description: project?.description ?? "",
    estimated_delivery_date: project?.estimated_delivery_date ?? "",
  };
  const { control, handleSubmit, setError, formState } = useForm<ProjectValues>({
    resolver: zodResolver(schema(choosePartner)),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<ProjectValues>(setError, FIELDS);
  const onError = (error: unknown) => {
    const field = isApiError(error) ? FIELD_CONFLICTS[error.code] : undefined;
    if (field && isApiError(error) && (field !== "partner_id" || choosePartner)) {
      setError(field, { type: error.code, message: error.message });
      return;
    }
    onFieldError(error);
  };

  const toBody = (values: ProjectValues) => ({
    name: values.name,
    code: values.code || null,
    city_code: values.city_code,
    address: values.address,
    description: values.description,
    estimated_delivery_date: values.estimated_delivery_date || null,
  });

  const submit = handleSubmit((values) => {
    if (!project) {
      create.mutate(
        { ...toBody(values), ...(choosePartner ? { partner_id: values.partner_id } : {}) },
        {
          onSuccess: (created) => {
            toast.success({ title: "Proyecto creado", message: "Queda en borrador." });
            onClose();
            onCreated?.(created);
          },
          onError,
        },
      );
      return;
    }
    const body = toBody(values);
    const before = toBody(initial);
    const changed = Object.fromEntries(
      EDITABLE.filter(
        (key) => body[key as keyof typeof body] !== before[key as keyof typeof before],
      ).map((key) => [key, body[key as keyof typeof body]]),
    );
    if (Object.keys(changed).length === 0) {
      onClose();
      return;
    }
    update.mutate(changed, {
      onSuccess: () => {
        toast.success({ title: "Proyecto guardado" });
        onClose();
      },
      onError,
    });
  });

  const text = (
    name: "name" | "code" | "address",
    label: string,
    limit: number,
    optional?: boolean,
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={optional ? "opcional" : undefined}
      error={formState.errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => <Input {...field} {...ctl} maxLength={limit} autoComplete="off" />}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open
      title={project ? "Editar proyecto" : "Nuevo proyecto"}
      description={
        project ? undefined : "El proyecto nace en borrador; después se envía a validación."
      }
      okText={project ? "Guardar" : "Crear proyecto"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={680}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-[2fr_1fr]">
        {text("name", "Nombre", 180)}
        {text("code", "Código", 50, true)}
      </div>
      {choosePartner && (
        <FormField
          id={`${ids}-partner`}
          label="Constructora"
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
                  enabled
                />
              )}
            />
          )}
        </FormField>
      )}
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField id={`${ids}-city`} label="Municipio" error={formState.errors.city_code?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="city_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Busca el municipio"
                  showSearch={{ optionFilterProp: "label" }}
                  loading={cities.isPending}
                  options={cityOptions}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-delivery`}
          label="Entrega estimada"
          optional="opcional"
          error={formState.errors.estimated_delivery_date?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="estimated_delivery_date"
              render={({ field }) => <Input {...field} {...ctl} type="date" />}
            />
          )}
        </FormField>
      </div>
      {text("address", "Dirección", 255)}
      <FormField
        id={`${ids}-description`}
        label="Descripción"
        optional="opcional"
        error={formState.errors.description?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="description"
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={3} />}
          />
        )}
      </FormField>
    </ActionModal>
  );
}
