"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Checkbox, Input, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { Card, DataList, Datum } from "@/components/ui/card";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useCatalog } from "@/features/applications/queries";
import { optionsOf } from "@/features/clients/catalog-options";
import { PlusIcon } from "@/components/ui/icons";
import {
  ADDRESS_TYPE_CATALOG,
  useClientAddresses,
  useCreateAddress,
  useMunicipalities,
  type Address,
  type AddressCreateRequest,
} from "@/features/clients/detail-queries";
import type { ClientDetail } from "@/features/clients/queries";
import { formatDate, formatDateOnly } from "@/lib/format";
import { useToast } from "@/providers/toast";

function ClientDataCard({ client }: { client: ClientDetail }) {
  return (
    <Card id="client-data" title="Datos del cliente">
      <DataList columns={3}>
        <Datum label="Nombres">{client.first_names}</Datum>
        <Datum label="Apellidos">{client.last_names}</Datum>
        <Datum label="Documento">
          {client.document_type.label} {client.document_number}
        </Datum>
        <Datum label="Fecha de nacimiento">{formatDateOnly(client.birth_date)}</Datum>
        <Datum label="Correo">{client.email}</Datum>
        <Datum label="Teléfono">{client.phone}</Datum>
        <Datum label="Origen">{client.origin?.label}</Datum>
        <Datum label="Creado">
          {formatDate(client.created_at)}
          {client.created_by && (
            <span className="text-text-tertiary"> · {client.created_by.name}</span>
          )}
        </Datum>
      </DataList>
    </Card>
  );
}

const LINE1_MAX = 255;
const LINE2_MAX = 120;
const POSTAL_MAX = 12;

const addressSchema = z.object({
  address_type_code: z.string().min(1, { error: "Elige el tipo de dirección." }),
  city_code: z.string().min(1, { error: "Elige el municipio." }),
  line1: z
    .string()
    .trim()
    .min(1, { error: "Escribe la dirección." })
    .max(LINE1_MAX, { error: `Máximo ${LINE1_MAX} caracteres.` }),
  line2: z
    .string()
    .trim()
    .max(LINE2_MAX, { error: `Máximo ${LINE2_MAX} caracteres.` }),
  postal_code: z
    .string()
    .trim()
    .max(POSTAL_MAX, { error: `Máximo ${POSTAL_MAX} caracteres.` }),
  is_primary: z.boolean(),
});
type AddressValues = z.infer<typeof addressSchema>;
const ADDRESS_FIELDS = [
  "address_type_code",
  "city_code",
  "line1",
  "line2",
  "postal_code",
  "is_primary",
] as const;
const ADDRESS_DEFAULTS: AddressValues = {
  address_type_code: "",
  city_code: "",
  line1: "",
  line2: "",
  postal_code: "",
  is_primary: false,
};

/** Cuerpo de `POST /clients/{id}/addresses`. La primera la marca la API como principal. */
export function toAddressBody(values: AddressValues, first: boolean): AddressCreateRequest {
  return {
    address_type_code: values.address_type_code,
    city_code: values.city_code,
    line1: values.line1,
    line2: values.line2,
    postal_code: values.postal_code,
    is_primary: !first && values.is_primary,
  };
}

function AddressModal({
  clientId,
  first,
  open,
  onClose,
}: {
  clientId: string;
  first: boolean;
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateAddress(clientId);
  const types = useCatalog(ADDRESS_TYPE_CATALOG);
  const cities = useMunicipalities(open);
  const { control, handleSubmit, setError, reset, formState } = useForm<AddressValues>({
    resolver: zodResolver(addressSchema),
    defaultValues: ADDRESS_DEFAULTS,
  });
  const onError = useFormErrorHandler<AddressValues>(setError, ADDRESS_FIELDS);
  const errors = formState.errors;

  const close = () => {
    reset(ADDRESS_DEFAULTS);
    onClose();
  };

  const submit = handleSubmit((values) => {
    create.mutate(toAddressBody(values, first), {
      onSuccess: () => {
        toast.success({ title: "Dirección agregada" });
        close();
      },
      onError,
    });
  });

  const text = (name: "line1" | "line2" | "postal_code", label: string, max: number) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={name === "line1" ? undefined : "opcional"}
      error={errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => <Input {...field} {...ctl} maxLength={max} />}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open={open}
      title="Agregar dirección"
      width={560}
      okText="Agregar dirección"
      loading={create.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-type`}
          label="Tipo de dirección"
          error={errors.address_type_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="address_type_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el tipo"
                  options={optionsOf(types.items)}
                  loading={types.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField id={`${ids}-city`} label="Municipio" error={errors.city_code?.message}>
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
                  options={optionsOf(cities.items)}
                  loading={cities.isPending}
                />
              )}
            />
          )}
        </FormField>
      </div>
      {text("line1", "Dirección", LINE1_MAX)}
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {text("line2", "Complemento", LINE2_MAX)}
        {text("postal_code", "Código postal", POSTAL_MAX)}
      </div>
      {first ? (
        <p className="text-text-secondary m-0 text-sm">
          Es la primera dirección del cliente: queda como principal.
        </p>
      ) : (
        <Controller
          control={control}
          name="is_primary"
          render={({ field }) => (
            <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
              Usar como dirección principal
            </Checkbox>
          )}
        />
      )}
    </ActionModal>
  );
}

function AddressItem({ address }: { address: Address }) {
  const extra = [address.line2, address.postal_code].filter(Boolean).join(" · ");
  return (
    <li className="border-border-default grid gap-0.5 border-b py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{address.line1}</span>
        {address.is_primary && (
          <span className="text-text-secondary border-border-default rounded-full border px-2 text-xs">
            Principal
          </span>
        )}
      </div>
      <span className="text-text-secondary text-sm">
        {address.address_type.label} · {address.city.label}
        {extra && ` · ${extra}`}
      </span>
    </li>
  );
}

function AddressesCard({ clientId, canEdit }: { clientId: string; canEdit: boolean }) {
  const query = useClientAddresses(clientId);
  const [open, setOpen] = useState(false);
  const items = query.data?.items ?? [];

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando direcciones" blocks={[40]} />;
  } else if (query.isError) {
    body = (
      <ErrorState
        title="No pudimos cargar las direcciones"
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else if (items.length === 0) {
    body = <p className="text-text-tertiary m-0 text-sm">Todavía no tiene direcciones.</p>;
  } else {
    body = (
      <ul className="m-0 list-none p-0">
        {items.map((address) => (
          <AddressItem key={address.id} address={address} />
        ))}
      </ul>
    );
  }

  return (
    <Card
      id="client-addresses"
      title="Direcciones"
      action={
        canEdit && query.isSuccess ? (
          <Button size="small" icon={<PlusIcon />} onClick={() => setOpen(true)}>
            Agregar dirección
          </Button>
        ) : undefined
      }
    >
      {body}
      {canEdit && (
        <AddressModal
          clientId={clientId}
          first={items.length === 0}
          open={open}
          onClose={() => setOpen(false)}
        />
      )}
    </Card>
  );
}

/** Pestaña Resumen: datos del cliente y sus direcciones. */
export function SummaryTab({ client, canEdit }: { client: ClientDetail; canEdit: boolean }) {
  return (
    <div className="grid max-w-[1100px] gap-4">
      <ClientDataCard client={client} />
      <AddressesCard clientId={client.id} canEdit={canEdit} />
    </div>
  );
}
