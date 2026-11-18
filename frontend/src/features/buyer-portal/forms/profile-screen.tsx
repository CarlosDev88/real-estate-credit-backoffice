"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Checkbox, Input } from "antd";
import { useEffect, useId } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Card } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import {
  CatalogSelect,
  CitySelect,
  DateInput,
  FieldGrid,
  FormActions,
  FormLoadError,
  FormLoading,
  FormScreen,
  REQUIRED,
  ReadOnlyField,
  maxText,
  useSaveErrors,
} from "@/features/buyer-portal/forms/form-kit";
import {
  useBuyerProfile,
  useSaveProfile,
  type BuyerAddress,
  type BuyerProfile,
} from "@/features/buyer-portal/forms/form-queries";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { useToast } from "@/providers/toast";

/** Límites del contrato (`PatchedBuyerProfileUpdateRequest`). */
const MAX_ADDRESSES = 10;

const addressSchema = z.object({
  id: z.string().optional(),
  address_type_code: z.string().min(1, { error: REQUIRED }),
  city_code: z.string().min(1, { error: REQUIRED }),
  line1: z
    .string()
    .trim()
    .min(1, { error: REQUIRED })
    .max(255, { error: maxText(255) }),
  line2: z.string().max(120, { error: maxText(120) }),
  postal_code: z.string().max(12, { error: maxText(12) }),
  is_primary: z.boolean(),
});

const schema = z.object({
  email: z.union([
    z.literal(""),
    z.email({ error: "Escribe un correo válido." }).max(254, { error: maxText(254) }),
  ]),
  phone: z.string().max(25, { error: maxText(25) }),
  birth_date: z.string().nullable(),
  addresses: z.array(addressSchema).max(MAX_ADDRESSES),
});
type Values = z.infer<typeof schema>;

const SIMPLE_FIELDS = new Set(["email", "phone", "birth_date", "addresses"]);
const isField = (name: string) =>
  SIMPLE_FIELDS.has(name) || /^addresses\.\d+\.[a-z_0-9]+$/.test(name);

function toValues(profile: BuyerProfile): Values {
  const addresses = profile.addresses as unknown as BuyerAddress[];
  return {
    email: profile.email ?? "",
    phone: profile.phone ?? "",
    birth_date: profile.birth_date,
    addresses: addresses.map((a) => ({
      id: a.id,
      address_type_code: a.address_type?.code ?? "",
      city_code: a.city?.code ?? "",
      line1: a.line1,
      line2: a.line2 ?? "",
      postal_code: a.postal_code ?? "",
      is_primary: a.is_primary,
    })),
  };
}

/** Etiqueta de la ciudad guardada de una dirección, si el código no cambió. */
function cityLabel(profile: BuyerProfile, addressId: string | undefined, code: string) {
  const saved = (profile.addresses as unknown as BuyerAddress[]).find((a) => a.id === addressId);
  return saved?.city?.code === code ? saved.city.label : null;
}

const EMPTY_ADDRESS: Values["addresses"][number] = {
  address_type_code: "",
  city_code: "",
  line1: "",
  line2: "",
  postal_code: "",
  is_primary: false,
};

function ProfileForm({ profile }: { profile: BuyerProfile }) {
  const { applicationId, readOnly } = usePortal();
  const id = useId();
  const save = useSaveProfile(applicationId);
  const toast = useToast();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(profile) });
  const addresses = useFieldArray({ control: form.control, name: "addresses", keyName: "key" });
  const onError = useSaveErrors(form.setError, isField);
  const { errors } = form.formState;

  // Datos nuevos del servidor (después de guardar o de "Recargar"): el formulario los toma.
  useEffect(() => form.reset(toValues(profile)), [profile, form]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        email: values.email.trim(),
        phone: values.phone.trim(),
        birth_date: values.birth_date || null,
        addresses: values.addresses.map(({ id: addressId, ...rest }) => ({
          ...(addressId ? { id: addressId } : {}),
          ...rest,
          line1: rest.line1.trim(),
        })),
      },
      { onSuccess: () => toast.success({ title: "Guardamos tus datos" }), onError },
    ),
  );

  return (
    <form noValidate onSubmit={(event) => void submit(event)} className="grid gap-5">
      <Card variant="portal" title="Identificación">
        <FieldGrid>
          <ReadOnlyField label="Nombres" value={profile.first_names} />
          <ReadOnlyField label="Apellidos" value={profile.last_names} />
          <ReadOnlyField
            label="Documento"
            value={`${profile.document_type.label} ${profile.document_number}`}
          />
        </FieldGrid>
        <p className="text-text-tertiary m-0 text-sm">
          Si algo de esto no es correcto, pídele a tu asesor que lo corrija.
        </p>
      </Card>

      <Card variant="portal" title="Contacto">
        <FieldGrid>
          <FormField id={`${id}-email`} label="Correo" error={errors.email?.message}>
            {(control) => (
              <Controller
                control={form.control}
                name="email"
                render={({ field }) => (
                  <Input {...control} {...field} type="email" size="large" autoComplete="email" />
                )}
              />
            )}
          </FormField>
          <FormField
            id={`${id}-phone`}
            label="Teléfono"
            help="Con el indicativo del país, por ejemplo +573001234567."
            error={errors.phone?.message}
          >
            {(control) => (
              <Controller
                control={form.control}
                name="phone"
                render={({ field }) => (
                  <Input {...control} {...field} type="tel" size="large" autoComplete="tel" />
                )}
              />
            )}
          </FormField>
          <FormField
            id={`${id}-birth`}
            label="Fecha de nacimiento"
            error={errors.birth_date?.message}
          >
            {(control) => (
              <Controller
                control={form.control}
                name="birth_date"
                render={({ field }) => (
                  <DateInput
                    {...control}
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                  />
                )}
              />
            )}
          </FormField>
        </FieldGrid>
      </Card>

      <Card
        variant="portal"
        title="Direcciones"
        action={
          !readOnly &&
          addresses.fields.length < MAX_ADDRESSES && (
            <Button
              size="large"
              onClick={() =>
                addresses.append({
                  ...EMPTY_ADDRESS,
                  is_primary: addresses.fields.length === 0,
                })
              }
            >
              Agregar dirección
            </Button>
          )
        }
      >
        {errors.addresses?.message && (
          <p role="alert" className="text-tone-danger-fg m-0 text-sm">
            {errors.addresses.message}
          </p>
        )}
        {addresses.fields.length === 0 && (
          <p className="text-text-secondary m-0">Todavía no tienes direcciones.</p>
        )}
        {addresses.fields.map((address, index) => {
          const fieldErrors = errors.addresses?.[index];
          const base = `${id}-address-${index}`;
          return (
            <fieldset
              key={address.key}
              className="border-border-default m-0 grid gap-4 rounded-lg border p-4"
            >
              <legend className="px-1 text-sm font-medium">Dirección {index + 1}</legend>
              <FieldGrid>
                <FormField
                  id={`${base}-type`}
                  label="Tipo"
                  error={fieldErrors?.address_type_code?.message}
                >
                  {(control) => (
                    <Controller
                      control={form.control}
                      name={`addresses.${index}.address_type_code`}
                      render={({ field }) => (
                        <CatalogSelect
                          {...control}
                          catalog="address_type"
                          value={field.value}
                          onChange={(v) => field.onChange(v ?? "")}
                          onBlur={field.onBlur}
                        />
                      )}
                    />
                  )}
                </FormField>
                <FormField
                  id={`${base}-city`}
                  label="Ciudad"
                  error={fieldErrors?.city_code?.message}
                >
                  {(control) => (
                    <Controller
                      control={form.control}
                      name={`addresses.${index}.city_code`}
                      render={({ field }) => (
                        <CitySelect
                          {...control}
                          currentLabel={cityLabel(profile, address.id, field.value)}
                          value={field.value}
                          onChange={(v) => field.onChange(v ?? "")}
                          onBlur={field.onBlur}
                        />
                      )}
                    />
                  )}
                </FormField>
                <FormField
                  id={`${base}-line1`}
                  label="Dirección"
                  error={fieldErrors?.line1?.message}
                >
                  {(control) => (
                    <Controller
                      control={form.control}
                      name={`addresses.${index}.line1`}
                      render={({ field }) => <Input {...control} {...field} size="large" />}
                    />
                  )}
                </FormField>
                <FormField
                  id={`${base}-line2`}
                  label="Complemento"
                  optional="opcional"
                  error={fieldErrors?.line2?.message}
                >
                  {(control) => (
                    <Controller
                      control={form.control}
                      name={`addresses.${index}.line2`}
                      render={({ field }) => <Input {...control} {...field} size="large" />}
                    />
                  )}
                </FormField>
                <FormField
                  id={`${base}-postal`}
                  label="Código postal"
                  optional="opcional"
                  error={fieldErrors?.postal_code?.message}
                >
                  {(control) => (
                    <Controller
                      control={form.control}
                      name={`addresses.${index}.postal_code`}
                      render={({ field }) => (
                        <Input {...control} {...field} size="large" inputMode="numeric" />
                      )}
                    />
                  )}
                </FormField>
              </FieldGrid>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Controller
                  control={form.control}
                  name={`addresses.${index}.is_primary`}
                  render={({ field }) => (
                    <Checkbox
                      checked={field.value}
                      onChange={(event) => {
                        // Solo una principal: marcar una desmarca las demás.
                        if (event.target.checked) {
                          form.getValues("addresses").forEach((_, i) =>
                            form.setValue(`addresses.${i}.is_primary`, i === index, {
                              shouldDirty: true,
                            }),
                          );
                        } else {
                          field.onChange(false);
                        }
                      }}
                    >
                      Dirección principal
                    </Checkbox>
                  )}
                />
                {!readOnly && (
                  <Button
                    size="large"
                    danger
                    type="text"
                    onClick={() => addresses.remove(index)}
                    aria-label={`Quitar la dirección ${index + 1}`}
                  >
                    Quitar
                  </Button>
                )}
              </div>
            </fieldset>
          );
        })}
      </Card>

      <FormActions saving={save.isPending} />
    </form>
  );
}

/** `/portal/datos`: datos personales del titular (`GET`/`PATCH /profile`). */
export function ProfileScreen() {
  const { applicationId } = usePortal();
  const profile = useBuyerProfile(applicationId);
  return (
    <FormScreen
      title="Tus datos personales"
      description="Revisa tus datos de contacto y tus direcciones."
    >
      {profile.isPending && <FormLoading />}
      {profile.isError && (
        <FormLoadError message={profile.error.message} onRetry={() => void profile.refetch()} />
      )}
      {profile.data && <ProfileForm profile={profile.data} />}
    </FormScreen>
  );
}
