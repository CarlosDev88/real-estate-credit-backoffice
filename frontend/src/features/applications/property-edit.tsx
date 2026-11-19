"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Radio, Select } from "antd";
import { useEffect, useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/ui/form-field";
import { MoneyInput } from "@/components/ui/money";
import {
  CatalogSelect,
  EditPanel,
  LockedAlert,
  maxText,
  MunicipalitySelect,
  NOT_NEGATIVE,
  REQUIRED,
  useEditErrors,
} from "@/features/applications/dossier-kit";
import { useCurrentVersion, useSaveProperty } from "@/features/applications/dossier-queries";
import type { ApplicationDetail, Property } from "@/features/applications/workspace-queries";
import { useActiveProjects } from "@/features/clients/detail-queries";
import { useToast } from "@/providers/toast";

/** Única finalidad que admite proyecto (contrato de `PUT /property`). Código de la API. */
export const PURCHASE_NEW = "PURCHASE_NEW";

const schema = z.object({
  property_type_code: z.string().min(1, { error: REQUIRED }),
  condition_code: z.string().min(1, { error: REQUIRED }),
  city_code: z.string().min(1, { error: REQUIRED }),
  address: z
    .string()
    .trim()
    .max(255, { error: maxText(255) }),
  unit_reference: z
    .string()
    .trim()
    .max(100, { error: maxText(100) }),
  estimated_value_cop: z
    .number()
    .int()
    .min(0, { error: NOT_NEGATIVE })
    .nullable()
    .refine((v) => v !== null, { error: REQUIRED }),
  is_owned_by_applicant: z.boolean().nullable(),
  ownership_notes: z
    .string()
    .trim()
    .max(2000, { error: maxText(2000) }),
  project_id: z.string(),
});
type Values = z.input<typeof schema>;
type Output = z.output<typeof schema>;
const FIELDS = Object.keys(schema.shape) as (keyof Values)[];

function toValues(property: Property | null): Values {
  return {
    property_type_code: property?.property_type.code ?? "",
    condition_code: property?.condition.code ?? "",
    city_code: property?.city.code ?? "",
    address: property?.address ?? "",
    unit_reference: property?.unit_reference ?? "",
    estimated_value_cop: property?.estimated_value_cop ?? null,
    is_owned_by_applicant: property?.is_owned_by_applicant ?? null,
    ownership_notes: property?.ownership_notes ?? "",
    project_id: property?.project?.id ?? "",
  };
}

// El valor del radio: "sin respuesta" no puede ser `null` en Ant Design.
const OWNED = { yes: "yes", no: "no", unknown: "unknown" } as const;
const toOwned = (v: boolean | null) => (v === null ? OWNED.unknown : v ? OWNED.yes : OWNED.no);
const fromOwned = (v: string) => (v === OWNED.unknown ? null : v === OWNED.yes);

/**
 * Editar el inmueble (`PUT /applications/{id}/property`, reemplazo completo con
 * `If-Match`). Las reglas por finalidad las valida la API y sus errores van al campo;
 * el proyecto solo se ofrece en compra de vivienda nueva.
 */
export function PropertyEditPanel({
  detail,
  version,
  property,
  open,
  onClose,
}: {
  detail: ApplicationDetail;
  version: number;
  property: Property | null;
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const current = useCurrentVersion(detail.id, version);
  const save = useSaveProperty(detail.id, current);
  const withProject = detail.purpose?.code === PURCHASE_NEW;
  const projects = useActiveProjects(open && withProject);
  const form = useForm<Values, unknown, Output>({
    resolver: zodResolver(schema),
    defaultValues: toValues(property),
  });
  const { onError, locked, clearLocked } = useEditErrors<Values>(form.setError, FIELDS);
  const errors = form.formState.errors;

  useEffect(() => {
    if (open) {
      form.reset(toValues(property));
      clearLocked();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        property_type_code: values.property_type_code,
        condition_code: values.condition_code,
        city_code: values.city_code,
        address: values.address,
        unit_reference: values.unit_reference,
        estimated_value_cop: values.estimated_value_cop!,
        is_owned_by_applicant: values.is_owned_by_applicant,
        ownership_notes: values.ownership_notes,
        project_id: withProject && values.project_id ? values.project_id : null,
      },
      {
        onSuccess: () => {
          toast.success({ title: "Inmueble guardado" });
          onClose();
        },
        onError,
      },
    ),
  );

  const catalogField = (
    name: "property_type_code" | "condition_code",
    label: string,
    catalog: string,
    currentLabel: string | null,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} error={errors[name]?.message}>
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <CatalogSelect
              {...control}
              catalog={catalog}
              currentLabel={currentLabel}
              value={field.value}
              onChange={(v) => field.onChange(v ?? "")}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  const text = (name: "address" | "unit_reference", label: string, help?: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional="opcional"
      help={help}
      error={errors[name]?.message}
    >
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => <Input {...control} {...field} />}
        />
      )}
    </FormField>
  );

  return (
    <EditPanel
      open={open}
      onClose={onClose}
      eyebrow={detail.code}
      title={property ? "Editar inmueble" : "Registrar inmueble"}
      formId={`${ids}-form`}
      onSubmit={submit}
      saving={save.isPending}
    >
      <LockedAlert message={locked} />
      {withProject && (
        <FormField
          id={`${ids}-project`}
          label="Proyecto"
          optional="opcional"
          help="Solo proyectos activos."
          error={errors.project_id?.message}
        >
          {(control) => (
            <Controller
              control={form.control}
              name="project_id"
              render={({ field }) => (
                <Select
                  {...control}
                  value={field.value || undefined}
                  onChange={(v: string | undefined) => field.onChange(v ?? "")}
                  allowClear
                  placeholder="Sin proyecto"
                  showSearch={{ optionFilterProp: "label" }}
                  loading={projects.isPending}
                  options={[
                    ...(projects.data ?? []).map((p) => ({
                      value: p.id,
                      label: `${p.name} · ${p.partner.name}`,
                    })),
                    ...(property?.project &&
                    !(projects.data ?? []).some((p) => p.id === property.project?.id)
                      ? [{ value: property.project.id, label: property.project.name }]
                      : []),
                  ]}
                />
              )}
            />
          )}
        </FormField>
      )}
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        {catalogField(
          "property_type_code",
          "Tipo de inmueble",
          "property_type",
          property?.property_type.label ?? null,
        )}
        {catalogField(
          "condition_code",
          "Condición",
          "property_condition",
          property?.condition.label ?? null,
        )}
      </div>
      <FormField id={`${ids}-city`} label="Ciudad" error={errors.city_code?.message}>
        {(control) => (
          <Controller
            control={form.control}
            name="city_code"
            render={({ field }) => (
              <MunicipalitySelect
                {...control}
                currentLabel={property?.city.code === field.value ? property.city.label : null}
                value={field.value}
                onChange={(v) => field.onChange(v ?? "")}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        {text("address", "Dirección")}
        {text("unit_reference", "Unidad", "Por ejemplo, apartamento o casa.")}
      </div>
      <FormField
        id={`${ids}-value`}
        label="Valor comercial"
        error={errors.estimated_value_cop?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="estimated_value_cop"
            render={({ field }) => (
              <MoneyInput
                {...control}
                className="w-full"
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      <Controller
        control={form.control}
        name="is_owned_by_applicant"
        render={({ field }) => (
          <fieldset className="m-0 grid gap-2 border-0 p-0">
            <legend className="mb-1.5 p-0 text-sm font-medium">¿Es del titular?</legend>
            <Radio.Group
              value={toOwned(field.value)}
              onChange={(event) => field.onChange(fromOwned(String(event.target.value)))}
              options={[
                { value: OWNED.yes, label: "Sí" },
                { value: OWNED.no, label: "No" },
                { value: OWNED.unknown, label: "Sin respuesta" },
              ]}
            />
            {errors.is_owned_by_applicant?.message && (
              <p className="text-tone-danger-fg m-0 text-sm">
                {errors.is_owned_by_applicant.message}
              </p>
            )}
          </fieldset>
        )}
      />
      <FormField
        id={`${ids}-notes`}
        label="Notas de propiedad"
        optional="opcional"
        error={errors.ownership_notes?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="ownership_notes"
            render={({ field }) => (
              <Input.TextArea {...control} {...field} rows={3} maxLength={2000} />
            )}
          />
        )}
      </FormField>
    </EditPanel>
  );
}
