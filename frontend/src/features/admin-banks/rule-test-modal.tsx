"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField } from "@/components/ui/form-field";
import {
  contextSkeleton,
  describeCondition,
  parseJson,
  pretty,
} from "@/features/admin-banks/condition";
import {
  OUTCOME_CODES,
  OUTCOME_LABELS,
  OutcomeBadge,
  outcomeLabel,
} from "@/features/admin-banks/labels";
import { useTestRule, type Rule, type RuleTestResponse } from "@/features/admin-banks/queries";
import { isApiError, type ApiError } from "@/lib/api/errors";
import { useApiErrorToast } from "@/providers/api-error-toast";

// Probar una regla (`POST /bank-policy-rules/{id}/test`): casos con un contexto JSON (los
// campos de la lista blanca) y, si se quiere, el resultado esperado. No toca solicitudes ni
// la regla. El contexto arranca con los campos que usa la condición, en `null`.

const MAX_CASES = 20;
const NO_EXPECTATION = "";

const caseSchema = z.object({
  name: z.string().trim().max(120, { error: "Máximo 120 caracteres." }),
  expected: z.string(),
  context: z
    .string()
    .trim()
    .min(1, { error: "Escribe el contexto." })
    .refine(
      (text) => {
        const parsed = parseJson(text);
        return (
          parsed.ok &&
          typeof parsed.value === "object" &&
          parsed.value !== null &&
          !Array.isArray(parsed.value)
        );
      },
      { error: "Debe ser un objeto JSON." },
    ),
});
const schema = z.object({ cases: z.array(caseSchema).min(1).max(MAX_CASES) });
type TestValues = z.infer<typeof schema>;

function newCase(rule: Rule, index: number): TestValues["cases"][number] {
  return {
    name: `Caso ${index + 1}`,
    expected: NO_EXPECTATION,
    context: pretty(contextSkeleton(rule.condition)),
  };
}

function Results({ response }: { response: RuleTestResponse }) {
  return (
    <section aria-labelledby="rule-test-results" className="grid gap-2" aria-live="polite">
      <h3 id="rule-test-results" className="m-0 text-base font-semibold">
        Resultado (v{response.rule.version})
      </h3>
      <ul className="m-0 grid list-none gap-2 p-0" aria-label="Resultados de la prueba">
        {response.results.map((result, index) => (
          <li
            key={index}
            className="border-border-default grid gap-1 rounded-md border px-3 py-2 text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{result.name || `Caso ${index + 1}`}</span>
              <OutcomeBadge outcome={result.outcome} />
              {result.matches_expected !== null && (
                <span
                  className={`ml-auto text-xs font-medium ${
                    result.matches_expected ? "text-tone-success-fg" : "text-tone-danger-fg"
                  }`}
                >
                  {result.matches_expected
                    ? "Coincide con lo esperado"
                    : `Se esperaba: ${outcomeLabel(result.expected ?? "")}`}
                </span>
              )}
            </div>
            {result.unresolved_fields.length > 0 && (
              <p className="text-text-secondary m-0">
                Sin dato:{" "}
                <span className="font-mono text-xs">{result.unresolved_fields.join(", ")}</span>
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RuleTestModal({ rule, onClose }: { rule: Rule; onClose: () => void }) {
  const ids = useId();
  const showError = useApiErrorToast();
  const test = useTestRule(rule.id);
  const [conditionError, setConditionError] = useState<ApiError | null>(null);
  const { control, handleSubmit, setError, formState } = useForm<TestValues>({
    resolver: zodResolver(schema),
    defaultValues: { cases: [newCase(rule, 0)] },
  });
  const cases = useFieldArray({ control, name: "cases" });

  const submit = handleSubmit((values) => {
    setConditionError(null);
    test.mutate(
      {
        cases: values.cases.map((item) => {
          const context = parseJson(item.context);
          return {
            name: item.name,
            expected: (item.expected || null) as (typeof OUTCOME_CODES)[number] | null,
            context: (context.ok ? context.value : {}) as Record<string, unknown>,
          };
        }),
      },
      {
        onError: (error) => {
          if (isApiError(error) && error.code === "RULE_CONDITION_INVALID") {
            setConditionError(error);
            return;
          }
          // `cases.0.context.financing`: el error va al contexto de ese caso.
          const details = isApiError(error) ? error.details : [];
          let placed = false;
          for (const detail of details) {
            const match = /^cases\.(\d+)\.(context|name|expected)/.exec(detail.field ?? "");
            if (!match) continue;
            const where = detail.field?.slice(match[0].length).replace(/^\./, "");
            setError(`cases.${Number(match[1])}.${match[2] as "context"}`, {
              type: detail.code,
              message: where ? `${where}: ${detail.message}` : detail.message,
            });
            placed = true;
          }
          if (!placed) showError(error);
        },
      },
    );
  });

  return (
    <ActionModal
      open
      title={`Probar ${rule.code} v${rule.version}`}
      description={
        <>
          Evalúa la condición con datos de ejemplo, sin tocar solicitudes.{" "}
          <span className="font-mono text-xs">{describeCondition(rule.condition)}</span>
        </>
      }
      okText="Probar"
      cancelText="Cerrar"
      loading={test.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={760}
    >
      {conditionError && (
        <Alert
          type="error"
          showIcon
          title={conditionError.message}
          description={conditionError.details
            .map((d) => `${d.field ?? ""}: ${d.message}`)
            .join(" ")}
        />
      )}

      <ol className="m-0 grid list-none gap-4 p-0" aria-label="Casos de prueba">
        {cases.fields.map((item, index) => (
          <li key={item.id} className="border-border-default grid gap-3 rounded-md border p-3">
            <div className="grid items-start gap-3 min-[600px]:grid-cols-[1fr_200px_auto]">
              <FormField
                id={`${ids}-${index}-name`}
                label="Nombre del caso"
                error={formState.errors.cases?.[index]?.name?.message}
              >
                {(ctl) => (
                  <Controller
                    control={control}
                    name={`cases.${index}.name`}
                    render={({ field }) => <Input {...field} {...ctl} maxLength={120} />}
                  />
                )}
              </FormField>
              <FormField id={`${ids}-${index}-expected`} label="Resultado esperado">
                {(ctl) => (
                  <Controller
                    control={control}
                    name={`cases.${index}.expected`}
                    render={({ field }) => (
                      <Select
                        {...ctl}
                        value={field.value}
                        onChange={field.onChange}
                        virtual={false}
                        options={[
                          { value: NO_EXPECTATION, label: "Sin esperar nada" },
                          ...OUTCOME_CODES.map((code) => ({
                            value: code,
                            label: OUTCOME_LABELS[code],
                          })),
                        ]}
                      />
                    )}
                  />
                )}
              </FormField>
              {cases.fields.length > 1 && (
                <Button
                  className="self-end"
                  onClick={() => cases.remove(index)}
                  aria-label={`Quitar el caso ${index + 1}`}
                >
                  Quitar
                </Button>
              )}
            </div>
            <FormField
              id={`${ids}-${index}-context`}
              label="Contexto (JSON)"
              help='Con los campos que usa la condición, p. ej. {"financing": {"term_months": 240}}. Un campo en null da "Faltan datos".'
              error={formState.errors.cases?.[index]?.context?.message}
            >
              {(ctl) => (
                <Controller
                  control={control}
                  name={`cases.${index}.context`}
                  render={({ field }) => (
                    <Input.TextArea
                      {...field}
                      {...ctl}
                      rows={5}
                      spellCheck={false}
                      className="font-mono text-sm"
                    />
                  )}
                />
              )}
            </FormField>
          </li>
        ))}
      </ol>
      {cases.fields.length < MAX_CASES && (
        <Button
          className="justify-self-start"
          onClick={() => cases.append(newCase(rule, cases.fields.length))}
        >
          Agregar caso
        </Button>
      )}

      {test.data && <Results response={test.data} />}
    </ActionModal>
  );
}
