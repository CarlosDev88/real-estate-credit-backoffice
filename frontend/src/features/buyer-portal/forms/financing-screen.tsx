"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, InputNumber } from "antd";
import { useEffect, useId } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/ui/form-field";
import { MoneyInput } from "@/components/ui/money";
import { TONE_CLASS } from "@/components/ui/status-badge";
import {
  CatalogSelect,
  FieldGrid,
  FormActions,
  FormCard,
  FormLoadError,
  FormLoading,
  FormScreen,
  NOT_NEGATIVE,
  REQUIRED,
  useSaveErrors,
} from "@/features/buyer-portal/forms/form-kit";
import {
  useBuyerFinancing,
  useEligibleProducts,
  useSaveFinancing,
  type BuyerFinancing,
  type EligibleProduct,
} from "@/features/buyer-portal/forms/form-queries";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { formatCOP } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Plazo máximo que admite el contrato (`term_months`). */
const TERM_MAX = 32767;
const optionalMoney = z.number().int().min(0, { error: NOT_NEGATIVE }).nullable();

const schema = z.object({
  financing_mode_code: z.string().min(1, { error: REQUIRED }),
  bank_product_id: z.string().nullable(),
  requested_amount_cop: optionalMoney,
  term_months: z
    .number()
    .int({ error: "Escribe un número entero de meses." })
    .min(1, { error: "Debe ser de al menos 1 mes." })
    .max(TERM_MAX)
    .nullable(),
  currency_mode_code: z.string().nullable(),
  amortization_mode_code: z.string().nullable(),
  own_resources_cop: z.number().int().min(0, { error: NOT_NEGATIVE }),
  uses_severance_funds: z.boolean(),
  severance_funds_cop: z.number().int().min(0, { error: NOT_NEGATIVE }),
  external_approved_amount_cop: optionalMoney,
});
type Values = z.infer<typeof schema>;
const FIELDS = new Set(Object.keys(schema.shape));

function toValues(financing: BuyerFinancing | null): Values {
  return {
    financing_mode_code: financing?.financing_mode.code ?? "",
    bank_product_id: financing?.bank_product?.id ?? null,
    requested_amount_cop: financing?.requested_amount_cop ?? null,
    term_months: financing?.term_months ?? null,
    currency_mode_code: financing?.currency_mode?.code ?? null,
    amortization_mode_code: financing?.amortization_mode?.code ?? null,
    own_resources_cop: financing?.own_resources_cop ?? 0,
    uses_severance_funds: financing?.uses_severance_funds ?? false,
    severance_funds_cop: financing?.severance_funds_cop ?? 0,
    external_approved_amount_cop: financing?.external_approved_amount_cop ?? null,
  };
}

/** "Desde $ X hasta $ Y", con lo que haya. */
function range(
  min: number | null,
  max: number | null,
  format: (v: number) => string,
): string | null {
  if (min !== null && max !== null) return `De ${format(min)} a ${format(max)}`;
  if (min !== null) return `Desde ${format(min)}`;
  if (max !== null) return `Hasta ${format(max)}`;
  return null;
}
const cop = (v: number) => formatCOP(v) ?? String(v);
const months = (v: number) => `${v} ${v === 1 ? "mes" : "meses"}`;

function ProductCards({
  products,
  value,
  onChange,
  labelId,
}: {
  products: EligibleProduct[];
  value: string | null;
  onChange: (value: string) => void;
  labelId: string;
}) {
  const { readOnly } = usePortal();
  return (
    <div role="radiogroup" aria-labelledby={labelId} className="grid gap-3 min-[900px]:grid-cols-2">
      {products.map((product) => {
        const selected = value === product.id;
        const disabled = readOnly || !product.eligible;
        const amount = range(product.min_amount_cop, product.max_amount_cop, cop);
        const term = range(product.min_term_months, product.max_term_months, months);
        return (
          <label
            key={product.id}
            className={`grid gap-1 rounded-xl border p-4 ${
              selected
                ? "border-brand-primary bg-brand-subtle"
                : "border-border-default bg-bg-surface"
            } ${disabled ? "cursor-not-allowed opacity-75" : "cursor-pointer"} has-focus-visible:outline-focus-ring has-focus-visible:outline-2`}
          >
            <span className="flex items-start gap-3">
              <input
                type="radio"
                name="bank_product_id"
                value={product.id}
                checked={selected}
                disabled={disabled}
                onChange={() => onChange(product.id)}
                className="accent-brand-primary mt-1 size-4 flex-none"
              />
              <span className="min-w-0 flex-1">
                <span className="text-text-tertiary block text-sm">{product.bank.name}</span>
                <b className="text-md block font-semibold">{product.name}</b>
              </span>
            </span>
            {(amount || term) && (
              <span className="text-text-secondary pl-7 text-sm">
                {[amount, term].filter(Boolean).join(" · ")}
              </span>
            )}
            <span className="pl-7">
              <span
                className={`inline-flex rounded-full border px-2 text-xs font-medium ${
                  product.eligible ? TONE_CLASS.success : TONE_CLASS.neutral
                }`}
              >
                {product.eligible ? "Disponible" : "No disponible para tu caso"}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}

function FinancingForm({
  financing,
  products,
}: {
  financing: BuyerFinancing | null;
  products: EligibleProduct[];
}) {
  const { applicationId } = usePortal();
  const id = useId();
  const save = useSaveFinancing(applicationId);
  const toast = useToast();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(financing),
  });
  const onError = useSaveErrors(form.setError, (name) => FIELDS.has(name));
  const { errors } = form.formState;
  const usesSeverance = useWatch({ control: form.control, name: "uses_severance_funds" });

  useEffect(() => form.reset(toValues(financing)), [financing, form]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        ...values,
        // El monto de cesantías solo cuenta si las usa.
        severance_funds_cop: values.uses_severance_funds ? values.severance_funds_cop : 0,
      },
      { onSuccess: () => toast.success({ title: "Guardamos tu financiación" }), onError },
    ),
  );

  const optionalSelect = (
    name: "currency_mode_code" | "amortization_mode_code",
    label: string,
    catalog: string,
  ) => (
    <FormField id={`${id}-${name}`} label={label} optional="opcional" error={errors[name]?.message}>
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <CatalogSelect
              {...control}
              catalog={catalog}
              allowClear
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  const moneyField = (
    name:
      | "requested_amount_cop"
      | "own_resources_cop"
      | "severance_funds_cop"
      | "external_approved_amount_cop",
    label: string,
    options: { optional?: boolean; nullable?: boolean; help?: string } = {},
  ) => (
    <FormField
      id={`${id}-${name}`}
      label={label}
      optional={options.optional ? "opcional" : undefined}
      help={options.help}
      error={errors[name]?.message}
    >
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <MoneyInput
              {...control}
              size="large"
              value={field.value}
              onChange={(v) => field.onChange(options.nullable ? v : (v ?? 0))}
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
        <FormField id={`${id}-mode`} label="Modalidad" error={errors.financing_mode_code?.message}>
          {(control) => (
            <Controller
              control={form.control}
              name="financing_mode_code"
              render={({ field }) => (
                <CatalogSelect
                  {...control}
                  catalog="financing_mode"
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? "")}
                  onBlur={field.onBlur}
                />
              )}
            />
          )}
        </FormField>
      </FormCard>

      <FormCard title="Productos disponibles" id={`${id}-products`}>
        {products.length === 0 ? (
          <p className="text-text-secondary m-0">
            No hay productos para la finalidad de tu crédito.
          </p>
        ) : (
          <Controller
            control={form.control}
            name="bank_product_id"
            render={({ field }) => (
              <ProductCards
                products={products}
                value={field.value}
                onChange={field.onChange}
                labelId={`${id}-products-title`}
              />
            )}
          />
        )}
        {errors.bank_product_id?.message && (
          <p role="alert" className="text-tone-danger-fg m-0 text-sm">
            {errors.bank_product_id.message}
          </p>
        )}
      </FormCard>

      <FormCard title="Montos y plazo">
        <FieldGrid>
          {moneyField("requested_amount_cop", "Monto solicitado", { nullable: true })}
          <FormField id={`${id}-term`} label="Plazo en meses" error={errors.term_months?.message}>
            {(control) => (
              <Controller
                control={form.control}
                name="term_months"
                render={({ field }) => (
                  <InputNumber<number>
                    {...control}
                    className="w-full!"
                    size="large"
                    min={1}
                    max={TERM_MAX}
                    precision={0}
                    inputMode="numeric"
                    value={field.value}
                    onChange={(v) => field.onChange(v ?? null)}
                    onBlur={field.onBlur}
                  />
                )}
              />
            )}
          </FormField>
          {optionalSelect("currency_mode_code", "Moneda", "currency_mode")}
          {optionalSelect("amortization_mode_code", "Amortización", "amortization_mode")}
          {moneyField("own_resources_cop", "Recursos propios")}
          {moneyField("external_approved_amount_cop", "Monto aprobado por otra entidad", {
            optional: true,
            nullable: true,
          })}
        </FieldGrid>
        <Controller
          control={form.control}
          name="uses_severance_funds"
          render={({ field }) => (
            <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
              ¿Usarás tus cesantías?
            </Checkbox>
          )}
        />
        {usesSeverance && (
          <div className="min-[900px]:w-1/2 min-[900px]:pr-2">
            {moneyField("severance_funds_cop", "Monto de cesantías")}
          </div>
        )}
      </FormCard>

      <FormActions saving={save.isPending} />
    </form>
  );
}

/** `/portal/financiacion` (`GET`/`PUT /financing` y los productos elegibles). */
export function FinancingScreen() {
  const { applicationId } = usePortal();
  const financing = useBuyerFinancing(applicationId);
  const products = useEligibleProducts(applicationId);
  const error = financing.error ?? products.error;
  return (
    <FormScreen title="Financiación" description="Cómo quieres financiar tu vivienda.">
      {(financing.isPending || products.isPending) && !error && <FormLoading />}
      {error && (
        <FormLoadError
          message={error.message}
          onRetry={() => {
            void financing.refetch();
            void products.refetch();
          }}
        />
      )}
      {financing.isSuccess && products.isSuccess && (
        <FinancingForm financing={financing.data} products={products.data} />
      )}
    </FormScreen>
  );
}
