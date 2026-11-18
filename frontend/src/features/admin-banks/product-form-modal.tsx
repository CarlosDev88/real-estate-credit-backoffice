"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input, InputNumber, Select } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { MoneyInput } from "@/components/ui/money";
import { useCatalog } from "@/features/admin-common/catalogs";
import { changedFields } from "@/features/admin-common/changes";
import { CODE_HELP, CODE_PATTERN } from "@/features/admin-banks/bank-form-modal";
import {
  useCreateProduct,
  useSetPurposes,
  useUpdateProduct,
  type BankProduct,
} from "@/features/admin-banks/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

export const PRODUCT_TYPE_CATALOG = "bank_product_type";
export const LOAN_PURPOSE_CATALOG = "loan_purpose";

// Crear o editar un producto (`POST`/`PATCH /bank-products`). Banco y código no se editan.
// Zod solo revisa el formato; que el mínimo no pase del máximo lo valida la API.

const MAX_COP = 1_000_000_000_000_000;
const amount = z.number().int().min(0).max(MAX_COP).nullable();
const months = z
  .number()
  .int({ error: "Meses enteros." })
  .min(1, { error: "Mínimo 1 mes." })
  .max(600, { error: "Máximo 600 meses." })
  .nullable();
const schema = z.object({
  code: z
    .string()
    .trim()
    .min(1, { error: "Escribe el código." })
    .max(50, { error: "Máximo 50 caracteres." })
    .regex(CODE_PATTERN, { error: "Usa mayúsculas, números y _, y empieza por una letra." }),
  name: z
    .string()
    .trim()
    .min(1, { error: "Escribe el nombre." })
    .max(180, { error: "Máximo 180 caracteres." }),
  product_type_code: z.string().min(1, { error: "Elige el tipo." }),
  min_amount_cop: amount,
  max_amount_cop: amount,
  min_term_months: months,
  max_term_months: months,
  valid_from: z.string(),
  valid_to: z.string(),
  purpose_codes: z.array(z.string()),
});
type ProductValues = z.infer<typeof schema>;
const FIELDS = [
  "code",
  "name",
  "product_type_code",
  "min_amount_cop",
  "max_amount_cop",
  "min_term_months",
  "max_term_months",
  "valid_from",
  "valid_to",
  "purpose_codes",
] as const;
const EDITABLE = [
  "name",
  "product_type_code",
  "min_amount_cop",
  "max_amount_cop",
  "min_term_months",
  "max_term_months",
  "valid_from",
  "valid_to",
] as const;

/** Casillas de finalidades (`loan_purpose`), dentro de un `fieldset`. */
export function PurposeCheckboxes({
  value,
  onChange,
  error,
  errorId,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  error?: string;
  errorId: string;
}) {
  const purposes = useCatalog(LOAN_PURPOSE_CATALOG);
  return (
    <fieldset
      className="m-0 grid gap-2 border-0 p-0"
      aria-describedby={error ? errorId : undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="mb-1.5 p-0 text-sm font-medium">Finalidades</legend>
      {purposes.isPending ? (
        <p role="status" className="text-text-tertiary m-0 text-sm">
          Cargando finalidades…
        </p>
      ) : (
        <div className="grid gap-2 min-[600px]:grid-cols-2">
          {purposes.items.map((purpose) => (
            <Checkbox
              key={purpose.code}
              checked={value.includes(purpose.code)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, purpose.code]
                    : value.filter((code) => code !== purpose.code),
                )
              }
            >
              {purpose.label}
            </Checkbox>
          ))}
        </div>
      )}
      {error && (
        <p id={errorId} className="text-tone-danger-fg m-0 text-sm">
          {error}
        </p>
      )}
    </fieldset>
  );
}

export function ProductFormModal({
  bankId,
  product,
  onClose,
  onCreated,
}: {
  /** Banco del producto nuevo. */
  bankId: string;
  product?: BankProduct;
  onClose: () => void;
  onCreated?: (product: BankProduct) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateProduct();
  const update = useUpdateProduct(product?.id ?? "");
  const types = useCatalog(PRODUCT_TYPE_CATALOG);
  const initial: ProductValues = {
    code: product?.code ?? "",
    name: product?.name ?? "",
    product_type_code: product?.product_type.code ?? "",
    min_amount_cop: product?.min_amount_cop ?? null,
    max_amount_cop: product?.max_amount_cop ?? null,
    min_term_months: product?.min_term_months ?? null,
    max_term_months: product?.max_term_months ?? null,
    valid_from: product?.valid_from ?? "",
    valid_to: product?.valid_to ?? "",
    purpose_codes: [],
  };
  const { control, handleSubmit, setError, formState } = useForm<ProductValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<ProductValues>(setError, FIELDS);
  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === "DUPLICATE_CODE") {
      setError("code", { type: error.code, message: error.message });
      return;
    }
    onFieldError(error);
  };

  const toBody = (values: ProductValues) => ({
    ...values,
    valid_from: values.valid_from || undefined,
    valid_to: values.valid_to || null,
  });

  const submit = handleSubmit((values) => {
    if (!product) {
      const { valid_from, ...rest } = toBody(values);
      create.mutate(
        { ...rest, bank_id: bankId, ...(valid_from ? { valid_from } : {}) },
        {
          onSuccess: (created) => {
            toast.success({ title: "Producto creado" });
            onClose();
            onCreated?.(created);
          },
          onError,
        },
      );
      return;
    }
    const body = changedFields(toBody(values), toBody(initial), EDITABLE);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Producto guardado" });
        onClose();
      },
      onError,
    });
  });

  const number = (name: "min_term_months" | "max_term_months", label: string) => (
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
          render={({ field }) => (
            <InputNumber<number>
              {...ctl}
              value={field.value}
              onChange={(v) => field.onChange(v ?? null)}
              min={1}
              max={600}
              precision={0}
              suffix="meses"
              className="w-full"
            />
          )}
        />
      )}
    </FormField>
  );

  const money = (name: "min_amount_cop" | "max_amount_cop", label: string) => (
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
          render={({ field }) => (
            <MoneyInput {...ctl} value={field.value} onChange={field.onChange} />
          )}
        />
      )}
    </FormField>
  );

  const date = (name: "valid_from" | "valid_to", label: string, help?: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional="opcional"
      help={help}
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
      title={product ? "Editar producto" : "Nuevo producto"}
      okText={product ? "Guardar" : "Crear producto"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={680}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-code`}
          label="Código"
          help={product ? "El código no se cambia." : CODE_HELP}
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
                  disabled={!!product}
                  autoComplete="off"
                  className="font-mono"
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-type`}
          label="Tipo de producto"
          error={formState.errors.product_type_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="product_type_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el tipo"
                  loading={types.isPending}
                  options={types.items.map((item) => ({ value: item.code, label: item.label }))}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      </div>
      <FormField id={`${ids}-name`} label="Nombre" error={formState.errors.name?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="name"
            render={({ field }) => <Input {...field} {...ctl} maxLength={180} />}
          />
        )}
      </FormField>
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        {money("min_amount_cop", "Monto mínimo")}
        {money("max_amount_cop", "Monto máximo")}
        {number("min_term_months", "Plazo mínimo")}
        {number("max_term_months", "Plazo máximo")}
        {date("valid_from", "Vigente desde", product ? undefined : "Sin fecha, desde hoy.")}
        {date("valid_to", "Vigente hasta", "Sin fecha, sin vencimiento.")}
      </div>
      {!product && (
        <Controller
          control={control}
          name="purpose_codes"
          render={({ field }) => (
            <PurposeCheckboxes
              value={field.value}
              onChange={field.onChange}
              error={formState.errors.purpose_codes?.message}
              errorId={`${ids}-purposes-error`}
            />
          )}
        />
      )}
    </ActionModal>
  );
}

/** `PUT /bank-products/{id}/purposes`: las finalidades que se desmarcan se desactivan. */
export function PurposesModal({ product, onClose }: { product: BankProduct; onClose: () => void }) {
  const ids = useId();
  const toast = useToast();
  const setPurposes = useSetPurposes(product.id);
  const { control, handleSubmit, setError, formState } = useForm<{ purpose_codes: string[] }>({
    defaultValues: { purpose_codes: product.purposes.map((p) => p.code ?? "").filter(Boolean) },
  });
  const onError = useFormErrorHandler<{ purpose_codes: string[] }>(setError, ["purpose_codes"]);

  const submit = handleSubmit((values) =>
    setPurposes.mutate(values.purpose_codes, {
      onSuccess: () => {
        toast.success({ title: "Finalidades guardadas" });
        onClose();
      },
      onError,
    }),
  );

  return (
    <ActionModal
      open
      title="Finalidades del producto"
      description="Para qué se puede usar el producto. Las que desmarques quedan desactivadas, no se borran."
      okText="Guardar finalidades"
      loading={setPurposes.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={600}
    >
      <Controller
        control={control}
        name="purpose_codes"
        render={({ field }) => (
          <PurposeCheckboxes
            value={field.value}
            onChange={field.onChange}
            error={formState.errors.purpose_codes?.message}
            errorId={`${ids}-error`}
          />
        )}
      />
    </ActionModal>
  );
}
