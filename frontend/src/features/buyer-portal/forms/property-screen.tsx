"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Input, Radio } from "antd";
import { useEffect, useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/ui/form-field";
import { MoneyInput } from "@/components/ui/money";
import {
  CatalogSelect,
  CitySelect,
  FieldGrid,
  FormActions,
  FormCard,
  FormLoadError,
  FormLoading,
  FormScreen,
  NOT_NEGATIVE,
  REQUIRED,
  ReadOnlyField,
  maxText,
  useSaveErrors,
} from "@/features/buyer-portal/forms/form-kit";
import {
  useBuyerProperty,
  useSaveProperty,
  type BuyerProperty,
} from "@/features/buyer-portal/forms/form-queries";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { useToast } from "@/providers/toast";

const schema = z.object({
  property_type_code: z.string().min(1, { error: REQUIRED }),
  condition_code: z.string().min(1, { error: REQUIRED }),
  city_code: z.string().min(1, { error: REQUIRED }),
  address: z.string().max(255, { error: maxText(255) }),
  unit_reference: z.string().max(100, { error: maxText(100) }),
  estimated_value_cop: z
    .number()
    .int()
    .min(0, { error: NOT_NEGATIVE })
    .nullable()
    .refine((v) => v !== null, { error: REQUIRED }),
  /** "sí", "no" o sin respuesta (`null`). */
  is_owned_by_applicant: z.boolean().nullable(),
});
/** Lo que edita el formulario (el valor puede estar vacío) y lo que sale validado. */
type Values = z.input<typeof schema>;
type Output = z.output<typeof schema>;
const FIELDS = new Set(Object.keys(schema.shape));

function toValues(property: BuyerProperty | null): Values {
  return {
    property_type_code: property?.property_type.code ?? "",
    condition_code: property?.condition.code ?? "",
    city_code: property?.city.code ?? "",
    address: property?.address ?? "",
    unit_reference: property?.unit_reference ?? "",
    estimated_value_cop: property?.estimated_value_cop ?? null,
    is_owned_by_applicant: property?.is_owned_by_applicant ?? null,
  };
}

// El valor del radio: "sin respuesta" no puede ser `null` en Ant Design.
const OWNED = { yes: "yes", no: "no", unknown: "unknown" } as const;
const toOwned = (v: boolean | null) => (v === null ? OWNED.unknown : v ? OWNED.yes : OWNED.no);
const fromOwned = (v: string) => (v === OWNED.unknown ? null : v === OWNED.yes);

function PropertyForm({ property }: { property: BuyerProperty | null }) {
  const { applicationId } = usePortal();
  const id = useId();
  const save = useSaveProperty(applicationId);
  const toast = useToast();
  const form = useForm<Values, unknown, Output>({
    resolver: zodResolver(schema),
    defaultValues: toValues(property),
  });
  const onError = useSaveErrors(form.setError, (name) => FIELDS.has(name));
  const { errors } = form.formState;

  useEffect(() => form.reset(toValues(property)), [property, form]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        ...values,
        address: values.address.trim(),
        unit_reference: values.unit_reference.trim(),
      },
      { onSuccess: () => toast.success({ title: "Guardamos los datos del inmueble" }), onError },
    ),
  );

  const catalogField = (
    name: "property_type_code" | "condition_code",
    label: string,
    catalog: string,
  ) => (
    <FormField id={`${id}-${name}`} label={label} error={errors[name]?.message}>
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <CatalogSelect
              {...control}
              catalog={catalog}
              value={field.value}
              onChange={(v) => field.onChange(v ?? "")}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <form noValidate onSubmit={(event) => void submit(event)} className="grid gap-5">
      <FormCard>
        {property?.project && <ReadOnlyField label="Proyecto" value={property.project.name} />}
        <FieldGrid>
          {catalogField("property_type_code", "Tipo de inmueble", "property_type")}
          {catalogField("condition_code", "Condición", "property_condition")}
        </FieldGrid>
        <FormField id={`${id}-city`} label="Ciudad" error={errors.city_code?.message}>
          {(control) => (
            <Controller
              control={form.control}
              name="city_code"
              render={({ field }) => (
                <CitySelect
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
        <FieldGrid>
          <FormField
            id={`${id}-address`}
            label="Dirección"
            optional="opcional"
            error={errors.address?.message}
          >
            {(control) => (
              <Controller
                control={form.control}
                name="address"
                render={({ field }) => <Input {...control} {...field} size="large" />}
              />
            )}
          </FormField>
          <FormField
            id={`${id}-unit`}
            label="Unidad"
            optional="opcional"
            help="Por ejemplo, apartamento o casa."
            error={errors.unit_reference?.message}
          >
            {(control) => (
              <Controller
                control={form.control}
                name="unit_reference"
                render={({ field }) => <Input {...control} {...field} size="large" />}
              />
            )}
          </FormField>
          <FormField
            id={`${id}-value`}
            label="Valor estimado"
            error={errors.estimated_value_cop?.message}
          >
            {(control) => (
              <Controller
                control={form.control}
                name="estimated_value_cop"
                render={({ field }) => (
                  <MoneyInput
                    {...control}
                    size="large"
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                  />
                )}
              />
            )}
          </FormField>
        </FieldGrid>
        <Controller
          control={form.control}
          name="is_owned_by_applicant"
          render={({ field }) => (
            <fieldset className="m-0 grid gap-2 border-0 p-0">
              <legend className="mb-1.5 p-0 text-sm font-medium">¿Ya es tuyo?</legend>
              <Radio.Group
                value={toOwned(field.value)}
                onChange={(event) => field.onChange(fromOwned(String(event.target.value)))}
                options={[
                  { value: OWNED.yes, label: "Sí" },
                  { value: OWNED.no, label: "No" },
                  { value: OWNED.unknown, label: "Sin respuesta" },
                ]}
              />
            </fieldset>
          )}
        />
      </FormCard>
      <FormActions saving={save.isPending} />
    </form>
  );
}

/** `/portal/inmueble` (`GET`/`PUT /property`). */
export function PropertyScreen() {
  const { applicationId } = usePortal();
  const property = useBuyerProperty(applicationId);
  return (
    <FormScreen title="El inmueble" description="Los datos de la vivienda que vas a financiar.">
      {property.isPending && <FormLoading />}
      {property.isError && (
        <FormLoadError message={property.error.message} onRetry={() => void property.refetch()} />
      )}
      {property.isSuccess && <PropertyForm property={property.data} />}
    </FormScreen>
  );
}
