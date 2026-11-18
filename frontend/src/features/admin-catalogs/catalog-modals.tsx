"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { changedFields } from "@/features/admin-common/changes";
import {
  useCreateCatalog,
  useCreateCatalogItem,
  useUpdateCatalog,
  useUpdateCatalogItem,
  type Catalog,
  type CatalogItem,
} from "@/features/admin-catalogs/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar un catálogo y sus valores. Los códigos siguen el `pattern` del contrato
// (catálogo en minúsculas; valor en mayúsculas) y no se renombran después.

const CATALOG_CODE = /^[a-z][a-z0-9_]{1,49}$/;
const ITEM_CODE = /^[A-Z0-9][A-Z0-9_]{0,49}$/;

function duplicateTo<T extends string>(
  setError: (name: T, error: { type: string; message: string }) => void,
  field: T,
  fallback: (error: unknown) => void,
) {
  return (error: unknown) => {
    if (isApiError(error) && error.code === "DUPLICATE_CODE") {
      setError(field, { type: error.code, message: error.message });
      return;
    }
    fallback(error);
  };
}

// ---------- catálogo ----------

const catalogSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1, { error: "Escribe el código." })
    .max(50, { error: "Máximo 50 caracteres." })
    .regex(CATALOG_CODE, { error: "Usa minúsculas, números y _, y empieza por una letra." }),
  name: z
    .string()
    .trim()
    .min(1, { error: "Escribe el nombre." })
    .max(120, { error: "Máximo 120 caracteres." }),
  description: z.string().trim(),
  is_public: z.boolean(),
});
type CatalogValues = z.infer<typeof catalogSchema>;
const CATALOG_FIELDS = ["code", "name", "description", "is_public"] as const;

export function CatalogFormModal({
  catalog,
  onClose,
  onCreated,
}: {
  catalog?: Catalog;
  onClose: () => void;
  onCreated?: (catalog: Catalog) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateCatalog();
  const update = useUpdateCatalog(catalog?.id ?? "");
  const initial: CatalogValues = {
    code: catalog?.code ?? "",
    name: catalog?.name ?? "",
    description: catalog?.description ?? "",
    is_public: catalog?.is_public ?? false,
  };
  const { control, handleSubmit, setError, formState } = useForm<CatalogValues>({
    resolver: zodResolver(catalogSchema),
    defaultValues: initial,
  });
  const onError = duplicateTo<keyof CatalogValues>(
    setError,
    "code",
    useFormErrorHandler<CatalogValues>(setError, CATALOG_FIELDS),
  );

  const submit = handleSubmit((values) => {
    if (!catalog) {
      create.mutate(values, {
        onSuccess: (created) => {
          toast.success({ title: "Catálogo creado" });
          onClose();
          onCreated?.(created);
        },
        onError,
      });
      return;
    }
    const body = changedFields(values, initial, ["name", "description", "is_public"]);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Catálogo guardado" });
        onClose();
      },
      onError,
    });
  });

  return (
    <ActionModal
      open
      title={catalog ? "Editar catálogo" : "Nuevo catálogo"}
      okText={catalog ? "Guardar" : "Crear catálogo"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField
        id={`${ids}-code`}
        label="Código"
        help={catalog ? "El código no se cambia." : "Minúsculas, números y _ (p. ej. lead_origin)."}
        error={formState.errors.code?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="code"
            render={({ field }) => (
              <Input
                {...field}
                {...ctl}
                disabled={!!catalog}
                autoComplete="off"
                className="font-mono"
              />
            )}
          />
        )}
      </FormField>
      <FormField id={`${ids}-name`} label="Nombre" error={formState.errors.name?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="name"
            render={({ field }) => <Input {...field} {...ctl} maxLength={120} />}
          />
        )}
      </FormField>
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
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={2} />}
          />
        )}
      </FormField>
      <Controller
        control={control}
        name="is_public"
        render={({ field }) => (
          <Checkbox
            checked={field.value}
            onChange={(event) => field.onChange(event.target.checked)}
          >
            Público: se puede mostrar al comprador
          </Checkbox>
        )}
      />
    </ActionModal>
  );
}

// ---------- valor ----------

const itemSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1, { error: "Escribe el código." })
    .max(50, { error: "Máximo 50 caracteres." })
    .regex(ITEM_CODE, { error: "Usa mayúsculas, números y _." }),
  label: z
    .string()
    .trim()
    .min(1, { error: "Escribe la etiqueta." })
    .max(180, { error: "Máximo 180 caracteres." }),
  description: z.string().trim(),
  valid_from: z.string(),
  valid_to: z.string(),
});
type ItemValues = z.infer<typeof itemSchema>;
const ITEM_FIELDS = ["code", "label", "description", "valid_from", "valid_to"] as const;

export function ItemFormModal({
  catalogId,
  item,
  onClose,
}: {
  catalogId: string;
  item?: CatalogItem;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateCatalogItem(catalogId);
  const update = useUpdateCatalogItem(catalogId, item?.id ?? "");
  const initial: ItemValues = {
    code: item?.code ?? "",
    label: item?.label ?? "",
    description: item?.description ?? "",
    valid_from: item?.valid_from ?? "",
    valid_to: item?.valid_to ?? "",
  };
  const { control, handleSubmit, setError, formState } = useForm<ItemValues>({
    resolver: zodResolver(itemSchema),
    defaultValues: initial,
  });
  const onError = duplicateTo<keyof ItemValues>(
    setError,
    "code",
    useFormErrorHandler<ItemValues>(setError, ITEM_FIELDS),
  );
  const dates = (values: ItemValues) => ({
    valid_from: values.valid_from || null,
    valid_to: values.valid_to || null,
  });

  const submit = handleSubmit((values) => {
    if (!item) {
      create.mutate(
        {
          code: values.code,
          label: values.label,
          description: values.description,
          ...dates(values),
        },
        {
          onSuccess: () => {
            toast.success({ title: "Valor creado", message: "Queda al final del orden." });
            onClose();
          },
          onError,
        },
      );
      return;
    }
    const body = changedFields(
      { label: values.label, description: values.description, ...dates(values) },
      { label: initial.label, description: initial.description, ...dates(initial) },
      ["label", "description", "valid_from", "valid_to"],
    );
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Valor guardado" });
        onClose();
      },
      onError,
    });
  });

  const date = (name: "valid_from" | "valid_to", label: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional="opcional"
      error={formState.errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => <Input {...field} {...ctl} type="date" />}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open
      title={item ? `Editar ${item.label}` : "Nuevo valor"}
      okText={item ? "Guardar" : "Crear valor"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-[1fr_2fr]">
        <FormField
          id={`${ids}-code`}
          label="Código"
          help={item ? "No se renombra." : "Mayúsculas, números y _."}
          error={formState.errors.code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  {...ctl}
                  disabled={!!item}
                  autoComplete="off"
                  className="font-mono"
                />
              )}
            />
          )}
        </FormField>
        <FormField id={`${ids}-label`} label="Etiqueta" error={formState.errors.label?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="label"
              render={({ field }) => <Input {...field} {...ctl} maxLength={180} />}
            />
          )}
        </FormField>
      </div>
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
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={2} />}
          />
        )}
      </FormField>
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {date("valid_from", "Vigente desde")}
        {date("valid_to", "Vigente hasta")}
      </div>
    </ActionModal>
  );
}
