"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Input, Radio, Select } from "antd";
import { useId } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useCatalog } from "@/features/admin-common/catalogs";
import { fromLocalInput, toLocalInput } from "@/features/admin-common/datetime";
import { describeCondition, parseJson, pretty } from "@/features/admin-banks/condition";
import { SEVERITY_CODES, SEVERITY_LABELS, type Severity } from "@/features/admin-banks/labels";
import { LOAN_PURPOSE_CATALOG } from "@/features/admin-banks/product-form-modal";
import { useCreateRule, useUpdateRule, type Rule } from "@/features/admin-banks/queries";
import { isApiError, type ErrorDetail } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar una regla (`POST`/`PATCH /bank-policy-rules`). Un borrador se edita en el
// sitio; una versión publicada no cambia: la API crea un borrador con la versión siguiente.
// Zod revisa el formato (código del contrato, JSON válido); la condición la valida la API
// contra su lista blanca de campos y su error va al campo.

export const RULE_CODE_PATTERN = /^[A-Z][A-Z0-9_]{1,79}$/;
const ALL_PURPOSES = "";

const EXAMPLE_CONDITION = {
  operator: "lte",
  left: { field: "financing.term_months" },
  right: 360,
};

const schema = z.object({
  code: z
    .string()
    .trim()
    .min(1, { error: "Escribe el código." })
    .max(80, { error: "Máximo 80 caracteres." })
    .regex(RULE_CODE_PATTERN, { error: "Usa mayúsculas, números y _, y empieza por una letra." }),
  purpose_code: z.string(),
  severity: z.enum(SEVERITY_CODES),
  message: z
    .string()
    .trim()
    .min(1, { error: "Escribe el mensaje." })
    .max(1000, { error: "Máximo 1000 caracteres." }),
  condition: z
    .string()
    .trim()
    .min(1, { error: "Escribe la condición." })
    .refine((text) => parseJson(text).ok, { error: "No es un JSON válido." }),
  valid_from: z.string(),
  valid_to: z.string(),
});
type RuleValues = z.infer<typeof schema>;
const FIELDS = [
  "code",
  "purpose_code",
  "severity",
  "message",
  "condition",
  "valid_from",
  "valid_to",
] as const;
const API_FIELDS: Record<string, (typeof FIELDS)[number]> = {
  purpose_code: "purpose_code",
  severity: "severity",
  message: "message",
  valid_from: "valid_from",
  valid_to: "valid_to",
  code: "code",
};

function toValues(rule: Rule | undefined): RuleValues {
  return {
    code: rule?.code ?? "",
    purpose_code: rule?.purpose?.code ?? ALL_PURPOSES,
    severity: (rule?.severity as Severity | undefined) ?? "BLOCKING",
    message: rule?.message ?? "",
    condition: pretty(rule ? rule.condition : EXAMPLE_CONDITION),
    valid_from: toLocalInput(rule?.valid_from),
    valid_to: toLocalInput(rule?.valid_to),
  };
}

function toBody(values: RuleValues) {
  const parsed = parseJson(values.condition);
  return {
    purpose_code: values.purpose_code || null,
    severity: values.severity,
    message: values.message,
    condition: parsed.ok ? parsed.value : null,
    valid_to: fromLocalInput(values.valid_to),
    ...(values.valid_from ? { valid_from: fromLocalInput(values.valid_from) ?? undefined } : {}),
  };
}

export function RuleFormModal({
  productId,
  rule,
  onClose,
  onSaved,
}: {
  productId: string;
  /** Sin regla: crear. */
  rule?: Rule;
  onClose: () => void;
  /** La regla guardada (en un `201` de edición, el borrador nuevo) para abrirla. */
  onSaved: (rule: Rule) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateRule();
  const update = useUpdateRule(rule?.id ?? "");
  const purposes = useCatalog(LOAN_PURPOSE_CATALOG);
  const initial = toValues(rule);
  const { control, handleSubmit, setError, setValue, getValues, formState } = useForm<RuleValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<RuleValues>(setError, FIELDS);
  const published = rule !== undefined && rule.status !== "DRAFT";

  // Los errores de la condición llegan con la ruta del nodo (`condition.left`).
  const onError = (error: unknown) => {
    if (!isApiError(error)) return onFieldError(error);
    if (error.code === "DUPLICATE_CODE") {
      setError("code", { type: error.code, message: error.message });
      return;
    }
    if (error.code === "RULE_DRAFT_EXISTS") {
      const draftId = error.details[0]?.resource_id;
      toast.warning({
        title: error.message,
        message: error.details[0]?.message,
        action: draftId
          ? { label: "Abrir el borrador", onClick: () => onSaved({ id: draftId } as Rule) }
          : undefined,
      });
      return;
    }
    const condition = error.details.filter((d: ErrorDetail) => d.field?.startsWith("condition"));
    for (const detail of condition) {
      const where = detail.field === "condition" ? "" : `${detail.field}: `;
      setError("condition", { type: detail.code, message: `${where}${detail.message}` });
    }
    const rest = error.details.filter((d: ErrorDetail) => !d.field?.startsWith("condition"));
    for (const detail of rest) {
      const field = detail.field ? API_FIELDS[detail.field] : undefined;
      if (field) setError(field, { type: detail.code, message: detail.message });
    }
    if (condition.length === 0 && rest.every((d) => !d.field || !API_FIELDS[d.field])) {
      onFieldError(error);
    }
  };

  const submit = handleSubmit((values) => {
    if (!rule) {
      create.mutate(
        { ...toBody(values), code: values.code, bank_product_id: productId },
        {
          onSuccess: (created) => {
            toast.success({
              title: "Regla creada",
              message: "Queda en borrador hasta publicarla.",
            });
            onClose();
            onSaved(created);
          },
          onError,
        },
      );
      return;
    }
    const body = toBody(values);
    const before = toBody(initial);
    const changed = Object.fromEntries(
      Object.entries(body).filter(
        ([key, value]) =>
          JSON.stringify(value) !== JSON.stringify(before[key as keyof typeof before]),
      ),
    );
    if (Object.keys(changed).length === 0) return onClose();
    update.mutate(changed, {
      onSuccess: ({ rule: saved, newVersion }) => {
        toast.success(
          newVersion
            ? {
                title: `Se creó el borrador v${saved.version}`,
                message: "La versión publicada sigue igual hasta que publiques el borrador.",
              }
            : { title: "Regla guardada" },
        );
        onClose();
        onSaved(saved);
      },
      onError,
    });
  });

  const condition = useWatch({ control, name: "condition" });
  const parsed = parseJson(condition);
  const summary = parsed.ok ? describeCondition(parsed.value) : null;

  return (
    <ActionModal
      open
      title={rule ? `Editar ${rule.code}` : "Nueva regla"}
      description={
        published
          ? `La versión v${rule.version} está publicada y no cambia: al guardar se crea el borrador v${rule.version + 1}.`
          : rule
            ? undefined
            : "La regla nace en borrador; se aplica a las solicitudes cuando se publica."
      }
      okText={published ? "Crear borrador" : rule ? "Guardar" : "Crear regla"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={720}
    >
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-code`}
          label="Código"
          help={rule ? "Identifica la regla y no se cambia." : "Mayúsculas, números y _."}
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
                  disabled={!!rule}
                  autoComplete="off"
                  className="font-mono"
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-purpose`}
          label="Finalidad"
          error={formState.errors.purpose_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="purpose_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value}
                  onChange={field.onChange}
                  loading={purposes.isPending}
                  virtual={false}
                  options={[
                    { value: ALL_PURPOSES, label: "Todas las finalidades" },
                    ...purposes.items.map((item) => ({ value: item.code, label: item.label })),
                  ]}
                />
              )}
            />
          )}
        </FormField>
      </div>

      <Controller
        control={control}
        name="severity"
        render={({ field }) => (
          <fieldset className="m-0 grid gap-1.5 border-0 p-0">
            <legend className="mb-1.5 p-0 text-sm font-medium">Severidad</legend>
            <Radio.Group
              value={field.value}
              onChange={(event) => field.onChange(event.target.value)}
              options={SEVERITY_CODES.map((code) => ({
                value: code,
                label: SEVERITY_LABELS[code],
              }))}
            />
            <p className="text-text-tertiary m-0 text-xs">
              Bloqueante: si no cumple o faltan datos, la solicitud no es elegible para este
              producto. Advertencia: se muestra, pero no cambia la elegibilidad.
            </p>
          </fieldset>
        )}
      />

      <FormField
        id={`${ids}-message`}
        label="Mensaje"
        help="Lo que ve el asesor cuando la solicitud no cumple."
        error={formState.errors.message?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="message"
            render={({ field }) => <Input.TextArea {...field} {...ctl} rows={2} maxLength={1000} />}
          />
        )}
      </FormField>

      <FormField
        id={`${ids}-condition`}
        label="Condición (JSON)"
        help='Lo que debe cumplirse. Operadores: eq, gte, lte, in, and, or, sum, ratio; campos como {"field": "financing.term_months"}.'
        error={formState.errors.condition?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="condition"
            render={({ field }) => (
              <Input.TextArea
                {...field}
                {...ctl}
                rows={8}
                spellCheck={false}
                className="font-mono text-sm"
              />
            )}
          />
        )}
      </FormField>
      <div className="-mt-2 flex flex-wrap items-start gap-2 text-sm">
        <Button
          size="small"
          disabled={!parsed.ok}
          onClick={() => {
            const value = parseJson(getValues("condition"));
            if (value.ok) setValue("condition", pretty(value.value));
          }}
        >
          Formatear
        </Button>
        {summary && (
          <p className="text-text-secondary m-0 min-w-0 flex-1" aria-live="polite">
            Se lee: <span className="font-mono text-xs">{summary}</span>
          </p>
        )}
      </div>

      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-from`}
          label="Vigente desde"
          optional="opcional"
          help={rule ? undefined : "Sin fecha, desde ahora."}
          error={formState.errors.valid_from?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="valid_from"
              render={({ field }) => <Input {...field} {...ctl} type="datetime-local" />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-to`}
          label="Vigente hasta"
          optional="opcional"
          help="Sin fecha, sin vencimiento."
          error={formState.errors.valid_to?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="valid_to"
              render={({ field }) => <Input {...field} {...ctl} type="datetime-local" />}
            />
          )}
        </FormField>
      </div>
    </ActionModal>
  );
}
