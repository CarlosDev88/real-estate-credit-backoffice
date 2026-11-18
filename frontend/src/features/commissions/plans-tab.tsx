"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Input, Select } from "antd";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { Card, DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { ListPagination } from "@/components/ui/list-pagination";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import { bankLabel } from "@/features/dashboard/queries";
import { formatPct, validityLabel } from "@/features/commissions/commission-badges";
import { PAGE_SIZES, type PlanParams } from "@/features/commissions/commissions-params";
import {
  bogotaDate,
  useBankProducts,
  useClosePlan,
  useCreatePlan,
  usePlans,
  useUpdatePlan,
  type BankProduct,
  type CommissionPlan,
  type PlanCreateRequest,
  type PlanUpdateRequest,
} from "@/features/commissions/queries";
import { useToast } from "@/providers/toast";

export const NOTES_MAX = 255;

/** Vigencia del plan hoy (Bogotá): presentación a partir de las fechas de la API. */
export function planPhase(plan: CommissionPlan, today: string): "scheduled" | "current" | "closed" {
  if (plan.valid_from > today) return "scheduled";
  if (plan.valid_until && plan.valid_until <= today) return "closed";
  return "current";
}

const PHASE: Record<
  ReturnType<typeof planPhase>,
  { tone: "success" | "info" | "neutral"; label: string }
> = {
  current: { tone: "success", label: "Vigente" },
  scheduled: { tone: "info", label: "Programado" },
  closed: { tone: "neutral", label: "Cerrado" },
};

function PlanBadges({ plan, today }: { plan: CommissionPlan; today: string }) {
  const phase = PHASE[planPhase(plan, today)];
  return (
    <span className="flex flex-wrap gap-1.5">
      <ToneBadge tone={phase.tone}>{phase.label}</ToneBadge>
      {plan.in_use && <ToneBadge tone="accent">En uso</ToneBadge>}
    </span>
  );
}

const productLabel = (p: { name: string; bank: { name: string; short_name: string } }) =>
  `${bankLabel(p.bank)} · ${p.name}`;

/** Se puede adelantar el fin: sin fin, o con un fin que todavía no llegó. */
const closable = (plan: CommissionPlan, today: string) =>
  !plan.valid_until || plan.valid_until > today;

// ---------- formulario ----------

/** Decimal como lo pide el contrato (hasta 4 enteros y 4 decimales); acepta coma. */
const DECIMAL = /^\d{1,4}(?:[.,]\d{1,4})?$/;
const toDecimal = (v: string) => v.trim().replace(",", ".");

const decimalField = (label: string) =>
  z
    .string()
    .trim()
    .min(1, { error: `Indica ${label}.` })
    .regex(DECIMAL, { error: "Escribe un número, con hasta 4 decimales." });

const planSchema = z
  .object({
    bank_product_id: z.string().min(1, { error: "Elige el producto." }),
    rate_pct: decimalField("la tasa"),
    advisor_share_pct: decimalField("la porción del asesor"),
    broker_share_pct: decimalField("la porción del broker"),
    valid_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, { error: "Indica desde cuándo rige." }),
    valid_until: z.string(),
    notes: z.string().max(NOTES_MAX, { error: `Máximo ${NOTES_MAX} caracteres.` }),
  })
  .superRefine((v, ctx) => {
    const rate = Number(toDecimal(v.rate_pct));
    if (DECIMAL.test(v.rate_pct.trim()) && !(rate > 0 && rate <= 100)) {
      ctx.addIssue({
        code: "custom",
        path: ["rate_pct"],
        message: "Debe ser mayor que 0 y como mucho 100.",
      });
    }
    const advisor = Number(toDecimal(v.advisor_share_pct));
    const broker = Number(toDecimal(v.broker_share_pct));
    if (DECIMAL.test(v.advisor_share_pct.trim()) && DECIMAL.test(v.broker_share_pct.trim())) {
      if (Math.abs(advisor + broker - 100) > 1e-9) {
        ctx.addIssue({
          code: "custom",
          path: ["broker_share_pct"],
          message: "Asesor y broker deben sumar 100.",
        });
      } else if (!(advisor > broker)) {
        ctx.addIssue({
          code: "custom",
          path: ["advisor_share_pct"],
          message: "El asesor lleva la porción mayor.",
        });
      }
    }
    if (v.valid_until && v.valid_from && v.valid_until <= v.valid_from) {
      ctx.addIssue({
        code: "custom",
        path: ["valid_until"],
        message: "Debe ser posterior al inicio.",
      });
    }
  });
type PlanValues = z.infer<typeof planSchema>;
const PLAN_FIELDS = [
  "bank_product_id",
  "rate_pct",
  "advisor_share_pct",
  "broker_share_pct",
  "valid_from",
  "valid_until",
  "notes",
] as const;

/** "70.0000" → "70"; "0.7500" → "0.75" (para editar). */
const plainDecimal = (v: string) => String(Number(v));

function complement(value: string): string | null {
  if (!DECIMAL.test(value.trim())) return null;
  const n = 100 - Number(toDecimal(value));
  return n >= 0 ? String(Math.round(n * 10_000) / 10_000) : null;
}

function ReadOnlyField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      <div className="bg-bg-subtle border-border-default rounded-md border px-3 py-1.5 text-sm">
        {children}
      </div>
    </div>
  );
}

/** Crear un plan o editar uno sin uso (`PATCH` con `If-Match`). El producto no cambia. */
export function PlanFormModal({
  open,
  plan,
  products,
  productsLoading,
  onClose,
}: {
  open: boolean;
  /** Plan que se edita; sin él, se crea. */
  plan: CommissionPlan | null;
  products: BankProduct[];
  productsLoading: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreatePlan();
  const update = useUpdatePlan();
  const editing = !!plan;

  const defaults = (): PlanValues => ({
    bank_product_id: plan?.bank_product.id ?? "",
    rate_pct: plan ? plainDecimal(plan.rate_pct) : "",
    advisor_share_pct: plan ? plainDecimal(plan.advisor_share_pct) : "",
    broker_share_pct: plan ? plainDecimal(plan.broker_share_pct) : "",
    valid_from: plan?.valid_from ?? bogotaDate(new Date()),
    valid_until: plan?.valid_until ?? "",
    notes: plan?.notes ?? "",
  });

  const { control, handleSubmit, setError, reset, setValue, getValues, formState } =
    useForm<PlanValues>({ resolver: zodResolver(planSchema), defaultValues: defaults() });
  const onError = useFormErrorHandler<PlanValues>(setError, PLAN_FIELDS);

  useEffect(() => {
    if (open) reset(defaults());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open, plan?.id]);

  const submit = handleSubmit((values) => {
    const common = {
      rate_pct: toDecimal(values.rate_pct),
      advisor_share_pct: toDecimal(values.advisor_share_pct),
      broker_share_pct: toDecimal(values.broker_share_pct),
      valid_from: values.valid_from,
      valid_until: values.valid_until || null,
      notes: values.notes.trim(),
    };
    if (editing && plan) {
      const body: PlanUpdateRequest = common;
      update.mutate(
        { id: plan.id, version: plan.version, body },
        {
          onSuccess: () => {
            toast.success({ title: "Plan actualizado", message: plan.bank_product.name });
            onClose();
          },
          onError,
        },
      );
      return;
    }
    const body: PlanCreateRequest = { bank_product_id: values.bank_product_id, ...common };
    create.mutate(body, {
      onSuccess: (created) => {
        toast.success({ title: "Plan creado", message: created.bank_product.name });
        onClose();
      },
      onError,
    });
  });

  const errors = formState.errors;
  const decimalInput = (
    name: "rate_pct" | "advisor_share_pct" | "broker_share_pct",
    label: string,
    help?: string,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} help={help} error={errors[name]?.message}>
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Input
              {...field}
              {...ctl}
              inputMode="decimal"
              suffix="%"
              onChange={(event) => {
                field.onChange(event.target.value);
                // Asesor y broker suman 100: al escribir uno se completa el otro.
                const other =
                  name === "advisor_share_pct"
                    ? "broker_share_pct"
                    : name === "broker_share_pct"
                      ? "advisor_share_pct"
                      : null;
                const rest = other ? complement(event.target.value) : null;
                if (other && rest !== null && getValues(other) !== rest) {
                  setValue(other, rest, { shouldValidate: formState.isSubmitted });
                }
              }}
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open={open}
      title={editing ? "Editar plan" : "Nuevo plan"}
      description={
        editing
          ? "Solo se edita un plan que ninguna liquidación usó. El producto no cambia."
          : "La vigencia no puede solaparse con otro plan del mismo producto."
      }
      okText={editing ? "Guardar cambios" : "Crear plan"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={560}
    >
      {editing ? (
        <ReadOnlyField label="Producto">{productLabel(plan.bank_product)}</ReadOnlyField>
      ) : (
        <FormField id={`${ids}-product`} label="Producto" error={errors.bank_product_id?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="bank_product_id"
              render={({ field }) => (
                <Select
                  {...ctl}
                  showSearch={{ optionFilterProp: "label" }}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el producto"
                  loading={productsLoading}
                  virtual={false}
                  options={products.map((p) => ({ value: p.id, label: productLabel(p) }))}
                />
              )}
            />
          )}
        </FormField>
      )}
      {decimalInput("rate_pct", "Tasa", "Porcentaje sobre el monto desembolsado.")}
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        {decimalInput("advisor_share_pct", "Porción del asesor")}
        {decimalInput("broker_share_pct", "Porción del broker")}
      </div>
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        <FormField id={`${ids}-from`} label="Rige desde" error={errors.valid_from?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="valid_from"
              render={({ field }) => <Input {...field} {...ctl} type="date" />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-until`}
          label="Hasta"
          optional="opcional"
          help="Sin incluir ese día. Vacío: sin fin."
          error={errors.valid_until?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="valid_until"
              render={({ field }) => <Input {...field} {...ctl} type="date" />}
            />
          )}
        </FormField>
      </div>
      <FormField
        id={`${ids}-notes`}
        label="Notas"
        optional="opcional"
        error={errors.notes?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="notes"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={2} maxLength={NOTES_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- cerrar ----------

const closeSchema = (plan: CommissionPlan | null) =>
  z.object({
    valid_until: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, { error: "Indica la fecha de cierre." })
      .refine((v) => !plan || v > plan.valid_from, {
        error: "Debe ser posterior al inicio del plan.",
      })
      .refine((v) => !plan?.valid_until || v <= plan.valid_until, {
        error: "Solo se adelanta el fin: no puede ser posterior al actual.",
      }),
  });
type CloseValues = { valid_until: string };

export function ClosePlanModal({
  plan,
  onClose,
}: {
  plan: CommissionPlan | null;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const close = useClosePlan();
  const { control, handleSubmit, setError, reset, formState } = useForm<CloseValues>({
    resolver: zodResolver(closeSchema(plan)),
    defaultValues: { valid_until: "" },
  });
  const onError = useFormErrorHandler<CloseValues>(setError, ["valid_until"]);

  useEffect(() => {
    if (!plan) return;
    const today = bogotaDate(new Date());
    reset({ valid_until: today > plan.valid_from ? today : "" });
  }, [plan, reset]);

  const submit = handleSubmit((values) => {
    if (!plan) return;
    close.mutate(
      { id: plan.id, validUntil: values.valid_until },
      {
        onSuccess: () => {
          toast.success({ title: "Plan cerrado", message: plan.bank_product.name });
          onClose();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={!!plan}
      title="Cerrar plan"
      description={
        plan
          ? `${productLabel(plan.bank_product)}: el plan deja de aplicar desde la fecha que elijas (ese día ya no rige). Los desembolsos anteriores siguen con este plan.`
          : undefined
      }
      okText="Cerrar plan"
      cancelText="Volver"
      danger
      loading={close.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField
        id={`${ids}-until`}
        label="Deja de regir el"
        error={formState.errors.valid_until?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="valid_until"
            render={({ field }) => (
              <Input
                {...field}
                {...ctl}
                type="date"
                min={plan?.valid_from}
                max={plan?.valid_until ?? undefined}
              />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- listado ----------

function PlanActions({
  plan,
  today,
  onEdit,
  onClose,
}: {
  plan: CommissionPlan;
  today: string;
  onEdit: (plan: CommissionPlan) => void;
  onClose: (plan: CommissionPlan) => void;
}) {
  const label = productLabel(plan.bank_product);
  return (
    <span className="flex flex-wrap justify-end gap-1">
      {!plan.in_use && (
        <Button size="small" onClick={() => onEdit(plan)} aria-label={`Editar el plan de ${label}`}>
          Editar
        </Button>
      )}
      {closable(plan, today) && (
        <Button
          size="small"
          onClick={() => onClose(plan)}
          aria-label={`Cerrar el plan de ${label}`}
        >
          Cerrar
        </Button>
      )}
    </span>
  );
}

/** Pestaña "Planes" de `/comisiones`: listado y, con `commission_plans.manage`, crear, editar y cerrar. */
export function PlansTab({
  params,
  canManage,
  canReadProducts,
  mobile,
  onChange,
}: {
  params: PlanParams;
  canManage: boolean;
  canReadProducts: boolean;
  mobile: boolean;
  onChange: (patch: Partial<PlanParams>) => void;
}) {
  const list = usePlans(params);
  const products = useBankProducts(canReadProducts);
  const today = bogotaDate(new Date());
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CommissionPlan | null>(null);
  const [closing, setClosing] = useState<CommissionPlan | null>(null);

  const edit = useCallback((plan: CommissionPlan | null) => {
    setEditing(plan);
    setFormOpen(true);
  }, []);

  const columns = useMemo(() => {
    const col = dataColumns<CommissionPlan>();
    return col.columns([
      col.accessor((r) => r.bank_product.name, {
        id: "product",
        header: "Producto",
        cell: ({ row }) => (
          <span className="grid">
            <span className="font-medium">{row.original.bank_product.name}</span>
            <span className="text-text-tertiary text-xs">
              {bankLabel(row.original.bank_product.bank)}
            </span>
          </span>
        ),
      }),
      col.accessor((r) => r.rate_pct, {
        id: "rate",
        header: "Tasa",
        cell: ({ row }) => <span className="tabular-nums">{formatPct(row.original.rate_pct)}</span>,
      }),
      col.display({
        id: "split",
        header: "Asesor / broker",
        cell: ({ row }) => (
          <span className="tabular-nums">
            {formatPct(row.original.advisor_share_pct)} / {formatPct(row.original.broker_share_pct)}
          </span>
        ),
      }),
      col.display({
        id: "validity",
        header: "Vigencia",
        cell: ({ row }) => validityLabel(row.original.valid_from, row.original.valid_until),
      }),
      col.display({
        id: "state",
        header: "Estado",
        cell: ({ row }) => <PlanBadges plan={row.original} today={today} />,
      }),
      col.accessor((r) => r.notes, {
        id: "notes",
        header: "Notas",
        cell: ({ row }) => row.original.notes || <span className="text-text-tertiary">—</span>,
      }),
      ...(canManage
        ? [
            col.display({
              id: "actions",
              header: () => <span className="sr-only">Acciones</span>,
              cell: ({ row }) => (
                <PlanActions plan={row.original} today={today} onEdit={edit} onClose={setClosing} />
              ),
            }),
          ]
        : []),
    ]);
  }, [canManage, today, edit]);

  let content;
  if (list.isPending) content = <LoadingState label="Cargando los planes" blocks={[52, 52, 52]} />;
  else if (list.isError) {
    content = (
      <ErrorState
        title="No pudimos cargar los planes"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (list.data.items.length === 0) {
    content = (
      <EmptyState
        size="sm"
        title={params.bank_product_id ? "Este producto no tiene planes" : "Todavía no hay planes"}
        description="Sin un plan vigente, los desembolsos del producto no se liquidan."
        action={
          canManage ? (
            <Button type="primary" onClick={() => edit(null)}>
              Nuevo plan
            </Button>
          ) : undefined
        }
      />
    );
  } else {
    const busy = list.isFetching && list.isPlaceholderData;
    content = (
      <div className="-mx-5 -mb-5">
        {mobile ? (
          <CardList
            ariaLabel="Planes de comisión"
            rows={list.data.items}
            getRowId={(r) => r.id}
            busy={busy}
            renderCard={(plan) => (
              <>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{plan.bank_product.name}</span>
                  <span className="text-text-tertiary ml-auto text-xs">
                    {bankLabel(plan.bank_product.bank)}
                  </span>
                </div>
                <PlanBadges plan={plan} today={today} />
                <DataList layout="inline">
                  <Datum label="Tasa">{formatPct(plan.rate_pct)}</Datum>
                  <Datum label="Asesor / broker">
                    {formatPct(plan.advisor_share_pct)} / {formatPct(plan.broker_share_pct)}
                  </Datum>
                  <Datum label="Vigencia">{validityLabel(plan.valid_from, plan.valid_until)}</Datum>
                  <Datum label="Notas">{plan.notes}</Datum>
                </DataList>
                {canManage && (
                  <PlanActions plan={plan} today={today} onEdit={edit} onClose={setClosing} />
                )}
              </>
            )}
          />
        ) : (
          <DataTable
            ariaLabel="Planes de comisión"
            columns={columns}
            rows={list.data.items}
            getRowId={(r) => r.id}
            busy={busy}
            alignRight={["rate", "split", "actions"]}
            minWidth={900}
          />
        )}
        <ListPagination
          page={params.page}
          pageSize={params.page_size}
          total={list.data.total}
          itemsLabel="Planes"
          onPage={(page) => onChange({ page })}
          onPageSize={(page_size) => onChange({ page_size })}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <>
      {canReadProducts && (
        <div className="bg-bg-surface border-border-default flex flex-wrap items-center gap-2 rounded-lg border p-3">
          <Select
            aria-label="Filtrar por producto"
            value={params.bank_product_id}
            onChange={(bank_product_id: string) => onChange({ bank_product_id })}
            options={[
              { value: "", label: "todos" },
              ...(products.data ?? []).map((p) => ({ value: p.id, label: productLabel(p) })),
            ]}
            labelRender={({ label }) => `Producto: ${String(label ?? "todos")}`}
            loading={products.isPending}
            showSearch={{ optionFilterProp: "label" }}
            virtual={false}
            popupMatchSelectWidth={false}
            size={mobile ? "large" : "middle"}
            style={mobile ? { width: "100%" } : { width: 320 }}
          />
          {params.bank_product_id && (
            <Button type="text" onClick={() => onChange({ bank_product_id: "" })}>
              Limpiar
            </Button>
          )}
        </div>
      )}
      <Card
        title="Planes"
        action={
          canManage ? (
            <Button type="primary" onClick={() => edit(null)}>
              Nuevo plan
            </Button>
          ) : undefined
        }
      >
        <p className="text-text-tertiary m-0 mb-4 text-xs">
          Un plan en uso ya no se edita: se cierra y se crea uno nuevo.
        </p>
        {content}
      </Card>
      {canManage && (
        <>
          <PlanFormModal
            open={formOpen}
            plan={editing}
            products={products.data ?? []}
            productsLoading={products.isPending}
            onClose={() => setFormOpen(false)}
          />
          <ClosePlanModal plan={closing} onClose={() => setClosing(null)} />
        </>
      )}
    </>
  );
}
