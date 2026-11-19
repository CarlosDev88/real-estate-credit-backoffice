"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, InputNumber } from "antd";
import { useEffect, useId } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/ui/form-field";
import { MoneyInput } from "@/components/ui/money";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import {
  CatalogSelect,
  EditPanel,
  LockedAlert,
  NOT_NEGATIVE,
  REQUIRED,
  useEditErrors,
} from "@/features/applications/dossier-kit";
import {
  useCurrentVersion,
  useEligibleProducts,
  useSaveFinancing,
  type EligibleBankProduct,
} from "@/features/applications/dossier-queries";
import type { ApplicationDetail, Financing } from "@/features/applications/workspace-queries";
import { formatCOP } from "@/lib/format";
import { useToast } from "@/providers/toast";

/**
 * Modalidades del catálogo `financing_mode` con reglas propias en `PUT /financing`
 * (códigos de la API): el crédito bancario lleva producto y monto; el externo, su monto
 * aprobado.
 */
export const BANK_CREDIT = "BANK_CREDIT";
export const EXTERNAL_CREDIT = "EXTERNAL_CREDIT";
/** Plazo máximo que admite el contrato (`term_months`). */
const TERM_MAX = 32767;
const money = z.number().int().min(0, { error: NOT_NEGATIVE });

const schema = z
  .object({
    financing_mode_code: z.string().min(1, { error: REQUIRED }),
    bank_product_id: z.string().nullable(),
    requested_amount_cop: money.nullable(),
    term_months: z
      .number()
      .int({ error: "Escribe un número entero de meses." })
      .min(1, { error: "Debe ser de al menos 1 mes." })
      .max(TERM_MAX)
      .nullable(),
    currency_mode_code: z.string().nullable(),
    amortization_mode_code: z.string().nullable(),
    own_resources_cop: money,
    uses_severance_funds: z.boolean(),
    severance_funds_cop: money,
    external_approved_amount_cop: money.nullable(),
  })
  .superRefine((v, ctx) => {
    if (v.financing_mode_code === BANK_CREDIT) {
      if (!v.bank_product_id) {
        ctx.addIssue({ code: "custom", path: ["bank_product_id"], message: "Elige el producto." });
      }
      if (v.requested_amount_cop === null) {
        ctx.addIssue({ code: "custom", path: ["requested_amount_cop"], message: REQUIRED });
      }
    }
    if (v.financing_mode_code === EXTERNAL_CREDIT && v.external_approved_amount_cop === null) {
      ctx.addIssue({ code: "custom", path: ["external_approved_amount_cop"], message: REQUIRED });
    }
  });
type Values = z.infer<typeof schema>;
const FIELDS = [
  "financing_mode_code",
  "bank_product_id",
  "requested_amount_cop",
  "term_months",
  "currency_mode_code",
  "amortization_mode_code",
  "own_resources_cop",
  "uses_severance_funds",
  "severance_funds_cop",
  "external_approved_amount_cop",
] as const;

function toValues(financing: Financing | null): Values {
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

/** "De $ X a $ Y", con lo que haya. */
function range(min: number | null, max: number | null, format: (v: number) => string) {
  if (min !== null && max !== null) return `De ${format(min)} a ${format(max)}`;
  if (min !== null) return `Desde ${format(min)}`;
  if (max !== null) return `Hasta ${format(max)}`;
  return null;
}
const cop = (v: number) => formatCOP(v) ?? String(v);
const months = (v: number) => `${v} ${v === 1 ? "mes" : "meses"}`;

/** Productos que admiten la finalidad, con la evaluación (no guardada) de cada uno. */
function ProductChoices({
  products,
  value,
  onChange,
  labelId,
}: {
  products: EligibleBankProduct[];
  value: string | null;
  onChange: (value: string) => void;
  labelId: string;
}) {
  return (
    <div role="radiogroup" aria-labelledby={labelId} className="grid gap-2">
      {products.map((product) => {
        const selected = value === product.id;
        const { eligible, blocking_count: blocking, warning_count: warnings } = product.evaluation;
        const facts = [
          range(product.min_amount_cop, product.max_amount_cop, cop),
          range(product.min_term_months, product.max_term_months, months),
        ].filter(Boolean);
        return (
          <label
            key={product.id}
            className={`grid cursor-pointer gap-1 rounded-md border p-3 ${
              selected ? "border-brand-primary bg-brand-subtle" : "border-border-default"
            } has-focus-visible:outline-focus-ring has-focus-visible:outline-2`}
          >
            <span className="flex items-start gap-3">
              <input
                type="radio"
                name="bank_product_id"
                value={product.id}
                checked={selected}
                onChange={() => onChange(product.id)}
                className="accent-brand-primary mt-1 size-4 flex-none"
              />
              <span className="min-w-0 flex-1">
                <span className="text-text-tertiary block text-xs">{product.bank.name}</span>
                <b className="block font-semibold">{product.name}</b>
                {facts.length > 0 && (
                  <span className="text-text-secondary block text-sm">{facts.join(" · ")}</span>
                )}
              </span>
              <ToneBadge tone={eligible ? "success" : "danger"}>
                {eligible
                  ? warnings
                    ? `Cumple · ${warnings} ${warnings === 1 ? "alerta" : "alertas"}`
                    : "Cumple"
                  : `${blocking} ${blocking === 1 ? "regla no cumple" : "reglas no cumplen"}`}
              </ToneBadge>
            </span>
          </label>
        );
      })}
    </div>
  );
}

/**
 * Editar la financiación (`PUT /applications/{id}/financing`, reemplazo completo con
 * `If-Match`). El producto se elige de `GET .../eligible-bank-products`; la evaluación de
 * cada uno es informativa (los rangos los verifica la evaluación bancaria).
 */
export function FinancingEditPanel({
  detail,
  version,
  financing,
  open,
  onClose,
}: {
  detail: ApplicationDetail;
  version: number;
  financing: Financing | null;
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const current = useCurrentVersion(detail.id, version);
  const save = useSaveFinancing(detail.id, current);
  const products = useEligibleProducts(detail.id, open);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(financing),
  });
  const { onError, locked, clearLocked } = useEditErrors<Values>(form.setError, FIELDS);
  const errors = form.formState.errors;
  const mode = useWatch({ control: form.control, name: "financing_mode_code" });
  const usesSeverance = useWatch({ control: form.control, name: "uses_severance_funds" });
  const bank = mode === BANK_CREDIT;
  const external = mode === EXTERNAL_CREDIT;

  useEffect(() => {
    if (open) {
      form.reset(toValues(financing));
      clearLocked();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        financing_mode_code: values.financing_mode_code,
        // Sin crédito bancario no va producto y el monto solicitado queda en 0 (contrato).
        bank_product_id: bank ? values.bank_product_id : null,
        requested_amount_cop: bank ? values.requested_amount_cop : null,
        term_months: values.term_months,
        currency_mode_code: values.currency_mode_code,
        amortization_mode_code: values.amortization_mode_code,
        own_resources_cop: values.own_resources_cop,
        uses_severance_funds: values.uses_severance_funds,
        severance_funds_cop: values.uses_severance_funds ? values.severance_funds_cop : 0,
        ...(external ? { external_approved_amount_cop: values.external_approved_amount_cop } : {}),
      },
      {
        onSuccess: () => {
          toast.success({ title: "Financiación guardada" });
          onClose();
        },
        onError,
      },
    ),
  );

  const moneyField = (
    name:
      | "requested_amount_cop"
      | "own_resources_cop"
      | "severance_funds_cop"
      | "external_approved_amount_cop",
    label: string,
    nullable = false,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} error={errors[name]?.message}>
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <MoneyInput
              {...control}
              className="w-full"
              value={field.value}
              onChange={(v) => field.onChange(nullable ? v : (v ?? 0))}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  const optionalSelect = (
    name: "currency_mode_code" | "amortization_mode_code",
    label: string,
    catalog: string,
    currentLabel: string | null,
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional="opcional"
      error={errors[name]?.message}
    >
      {(control) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <CatalogSelect
              {...control}
              catalog={catalog}
              allowClear
              currentLabel={currentLabel}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  let productBlock = null;
  if (bank) {
    const labelId = `${ids}-products-label`;
    productBlock = (
      <section aria-labelledby={labelId} className="grid gap-2">
        <h3 id={labelId} className="m-0 text-sm font-medium">
          Producto bancario
        </h3>
        {products.isPending ? (
          <LoadingState label="Cargando los productos" blocks={[64, 64]} />
        ) : products.isError ? (
          <ErrorState
            variant="inline"
            title="No pudimos cargar los productos."
            onRetry={() => void products.refetch()}
          />
        ) : products.data.length === 0 ? (
          <p className="text-text-secondary m-0 text-sm">
            No hay productos disponibles para la finalidad de la solicitud.
          </p>
        ) : (
          <Controller
            control={form.control}
            name="bank_product_id"
            render={({ field }) => (
              <ProductChoices
                products={products.data}
                value={field.value}
                onChange={field.onChange}
                labelId={labelId}
              />
            )}
          />
        )}
        {errors.bank_product_id?.message && (
          <p role="alert" className="text-tone-danger-fg m-0 text-sm">
            {errors.bank_product_id.message}
          </p>
        )}
      </section>
    );
  }

  return (
    <EditPanel
      open={open}
      onClose={onClose}
      eyebrow={detail.code}
      title={financing ? "Editar financiación" : "Registrar financiación"}
      formId={`${ids}-form`}
      onSubmit={submit}
      saving={save.isPending}
      width={600}
    >
      <LockedAlert message={locked} />
      <FormField id={`${ids}-mode`} label="Modalidad" error={errors.financing_mode_code?.message}>
        {(control) => (
          <Controller
            control={form.control}
            name="financing_mode_code"
            render={({ field }) => (
              <CatalogSelect
                {...control}
                catalog="financing_mode"
                currentLabel={financing?.financing_mode.label ?? null}
                value={field.value}
                onChange={(v) => field.onChange(v ?? "")}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      {productBlock}
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        {bank && moneyField("requested_amount_cop", "Monto solicitado", true)}
        {external &&
          moneyField("external_approved_amount_cop", "Monto aprobado por la otra entidad", true)}
        <FormField
          id={`${ids}-term`}
          label="Plazo en meses"
          optional="opcional"
          error={errors.term_months?.message}
        >
          {(control) => (
            <Controller
              control={form.control}
              name="term_months"
              render={({ field }) => (
                <InputNumber<number>
                  {...control}
                  className="w-full!"
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
        {optionalSelect(
          "currency_mode_code",
          "Moneda",
          "currency_mode",
          financing?.currency_mode?.label ?? null,
        )}
        {optionalSelect(
          "amortization_mode_code",
          "Amortización",
          "amortization_mode",
          financing?.amortization_mode?.label ?? null,
        )}
        {moneyField("own_resources_cop", "Recursos propios")}
      </div>
      <Controller
        control={form.control}
        name="uses_severance_funds"
        render={({ field }) => (
          <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
            Usa cesantías
          </Checkbox>
        )}
      />
      {usesSeverance && moneyField("severance_funds_cop", "Monto de cesantías")}
    </EditPanel>
  );
}
