"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Checkbox, Input, InputNumber, Select } from "antd";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { useCatalog } from "@/features/admin-common/catalogs";
import { changedFields } from "@/features/admin-common/changes";
import { fromLocalInput, toLocalInput } from "@/features/admin-common/datetime";
import {
  labelIn,
  PARTICIPANT_ROLE_LABELS,
  PARTICIPANT_ROLES,
  type ParticipantRole,
} from "@/features/admin-documents/labels";
import {
  productOptionLabel,
  useCreateRequirement,
  useDocumentTypeOptions,
  useProductOptions,
  useUpdateRequirement,
  type Requirement,
} from "@/features/admin-documents/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

// Crear o editar un requisito (`POST`/`PATCH /document-requirements`). El alcance (producto,
// tipo, finalidad, perfil, rol y condición del inmueble) se elige al crear y no se edita;
// un campo vacío aplica a cualquier valor. Sobre una versión publicada, el `PATCH` crea un
// borrador nuevo (`201`). Zod solo revisa el formato.

export const PURPOSE_CATALOG = "loan_purpose";
export const EMPLOYMENT_CATALOG = "employment_profile";
export const PROPERTY_CONDITION_CATALOG = "property_condition";
const ANY = "";
const GROUP_PATTERN = /^[A-Z][A-Z0-9_]{1,49}$/;

const schema = z.object({
  bank_product_id: z.string(),
  document_type_id: z.string().min(1, { error: "Elige el tipo documental." }),
  purpose_code: z.string(),
  employment_profile_code: z.string(),
  participant_role: z.string(),
  property_condition_code: z.string(),
  is_required: z.boolean(),
  is_waivable: z.boolean(),
  minimum_files: z
    .number({ error: "Escribe cuántos archivos." })
    .int()
    .min(1, { error: "Mínimo 1." })
    .max(24, { error: "Máximo 24." }),
  alternative_group_code: z
    .string()
    .trim()
    .refine((value) => value === "" || GROUP_PATTERN.test(value), {
      error: "Usa mayúsculas, números y _, y empieza por una letra.",
    }),
  validity_days: z
    .number()
    .int({ error: "Días enteros." })
    .min(1, { error: "Mínimo 1 día." })
    .max(3650, { error: "Máximo 3650 días." })
    .nullable(),
  sort_order: z
    .number({ error: "Escribe el orden." })
    .int()
    .min(0, { error: "Mínimo 0." })
    .max(100000, { error: "Máximo 100000." }),
  valid_from: z.string(),
  valid_to: z.string(),
});
type RequirementValues = z.infer<typeof schema>;
const FIELDS = Object.keys(schema.shape) as (keyof RequirementValues)[];
const ATTRIBUTES = [
  "is_required",
  "is_waivable",
  "minimum_files",
  "alternative_group_code",
  "validity_days",
  "sort_order",
  "valid_from",
  "valid_to",
] as const;
// Los campos de la API que en el formulario llevan otro nombre.
const API_FIELDS: Record<string, keyof RequirementValues> = {
  bank_product_id: "bank_product_id",
  document_type_id: "document_type_id",
  purpose_code: "purpose_code",
  employment_profile_code: "employment_profile_code",
  participant_role: "participant_role",
  property_condition_code: "property_condition_code",
};

function toValues(requirement: Requirement | undefined): RequirementValues {
  return {
    bank_product_id: requirement?.bank_product?.id ?? ANY,
    document_type_id: requirement?.document_type.id ?? "",
    purpose_code: requirement?.purpose?.code ?? ANY,
    employment_profile_code: requirement?.employment_profile?.code ?? ANY,
    participant_role: (requirement?.participant_role as string | null | undefined) ?? ANY,
    property_condition_code: requirement?.property_condition?.code ?? ANY,
    is_required: requirement?.is_required ?? true,
    is_waivable: requirement?.is_waivable ?? false,
    minimum_files: requirement?.minimum_files ?? 1,
    alternative_group_code: requirement?.alternative_group_code ?? "",
    validity_days: requirement?.validity_days ?? null,
    sort_order: requirement?.sort_order ?? 100,
    valid_from: toLocalInput(requirement?.valid_from),
    valid_to: toLocalInput(requirement?.valid_to),
  };
}

function attributes(values: RequirementValues) {
  return {
    is_required: values.is_required,
    is_waivable: values.is_waivable,
    minimum_files: values.minimum_files,
    alternative_group_code: values.alternative_group_code || null,
    validity_days: values.validity_days,
    sort_order: values.sort_order,
    valid_to: fromLocalInput(values.valid_to),
    ...(values.valid_from ? { valid_from: fromLocalInput(values.valid_from) ?? undefined } : {}),
  };
}

/** El alcance de un requisito, en texto ("General · Cédula · Titular"). */
export function scopeText(requirement: Requirement): string {
  return [
    requirement.bank_product ? productOptionLabel(requirement.bank_product) : "General",
    requirement.purpose?.label,
    requirement.employment_profile?.label,
    labelIn(PARTICIPANT_ROLE_LABELS, requirement.participant_role as string | null),
    requirement.property_condition?.label,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function RequirementFormModal({
  requirement,
  onClose,
  onSaved,
}: {
  requirement?: Requirement;
  onClose: () => void;
  /** El requisito guardado (o el borrador nuevo) para abrirlo. */
  onSaved: (id: string) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateRequirement();
  const update = useUpdateRequirement(requirement?.id ?? "");
  const types = useDocumentTypeOptions(!requirement);
  const products = useProductOptions(!requirement);
  const purposes = useCatalog(PURPOSE_CATALOG);
  const profiles = useCatalog(EMPLOYMENT_CATALOG);
  const conditions = useCatalog(PROPERTY_CONDITION_CATALOG);
  const initial = toValues(requirement);
  const { control, handleSubmit, setError, formState } = useForm<RequirementValues>({
    resolver: zodResolver(schema),
    defaultValues: initial,
  });
  const onFieldError = useFormErrorHandler<RequirementValues>(setError, FIELDS);
  const published = requirement !== undefined && requirement.status !== "DRAFT";

  const onError = (error: unknown) => {
    if (
      isApiError(error) &&
      (error.code === "REQUIREMENT_SCOPE_EXISTS" || error.code === "REQUIREMENT_DRAFT_EXISTS")
    ) {
      const id = error.details[0]?.resource_id;
      toast.warning({
        title: error.message,
        message: error.details[0]?.message,
        action: id ? { label: "Abrir ese requisito", onClick: () => onSaved(id) } : undefined,
      });
      return;
    }
    if (isApiError(error)) {
      for (const detail of error.details) {
        const field = detail.field ? API_FIELDS[detail.field] : undefined;
        if (field) setError(field, { type: detail.code, message: detail.message });
      }
    }
    onFieldError(error);
  };

  const submit = handleSubmit((values) => {
    if (!requirement) {
      create.mutate(
        {
          ...attributes(values),
          document_type_id: values.document_type_id,
          bank_product_id: values.bank_product_id || null,
          purpose_code: values.purpose_code || null,
          employment_profile_code: values.employment_profile_code || null,
          participant_role: (values.participant_role || null) as ParticipantRole | null,
          property_condition_code: values.property_condition_code || null,
        },
        {
          onSuccess: (created) => {
            toast.success({
              title: "Requisito creado",
              message: "Queda en borrador hasta publicarlo.",
            });
            onClose();
            onSaved(created.id);
          },
          onError,
        },
      );
      return;
    }
    const body = changedFields(attributes(values), attributes(initial), [...ATTRIBUTES]);
    if (Object.keys(body).length === 0) return onClose();
    update.mutate(body, {
      onSuccess: ({ requirement: saved, newVersion }) => {
        toast.success(
          newVersion
            ? {
                title: `Se creó el borrador v${saved.version}`,
                message: "La versión publicada sigue igual hasta que publiques el borrador.",
              }
            : { title: "Requisito guardado" },
        );
        onClose();
        onSaved(saved.id);
      },
      onError,
    });
  });

  const errors = formState.errors;
  const anyOption = (label: string) => ({ value: ANY, label });

  const select = (
    name:
      | "bank_product_id"
      | "document_type_id"
      | "purpose_code"
      | "employment_profile_code"
      | "participant_role"
      | "property_condition_code",
    label: string,
    options: { value: string; label: string }[],
    loading = false,
    help?: string,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} help={help} error={errors[name]?.message}>
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Select
              {...ctl}
              value={field.value === "" && name === "document_type_id" ? undefined : field.value}
              onChange={field.onChange}
              placeholder="Elige el tipo documental"
              loading={loading}
              showSearch={{ optionFilterProp: "label" }}
              options={options}
            />
          )}
        />
      )}
    </FormField>
  );

  const integer = (
    name: "minimum_files" | "validity_days" | "sort_order",
    label: string,
    options: { min: number; max: number; optional?: boolean; help?: string; suffix?: string },
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={options.optional ? "opcional" : undefined}
      help={options.help}
      error={errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <InputNumber<number>
              {...ctl}
              value={field.value}
              onChange={(v) => field.onChange(v ?? (options.optional ? null : undefined))}
              min={options.min}
              max={options.max}
              precision={0}
              suffix={options.suffix}
              className="w-full"
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open
      title={
        requirement ? `Editar requisito de ${requirement.document_type.name}` : "Nuevo requisito"
      }
      description={
        published
          ? `La versión v${requirement.version} está publicada y no cambia: al guardar se crea el borrador v${requirement.version + 1}.`
          : requirement
            ? undefined
            : 'Un campo en "cualquiera" aplica a todos los valores. El requisito nace en borrador.'
      }
      okText={published ? "Crear borrador" : requirement ? "Guardar" : "Crear requisito"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={720}
    >
      {requirement ? (
        <section aria-labelledby={`${ids}-scope`} className="grid gap-2">
          <h3 id={`${ids}-scope`} className="m-0 text-sm font-semibold">
            Alcance (no se cambia)
          </h3>
          <DataList layout="inline">
            <Datum label="Tipo documental">{requirement.document_type.name}</Datum>
            <Datum label="Aplica a">{scopeText(requirement)}</Datum>
          </DataList>
        </section>
      ) : (
        <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
          {select(
            "document_type_id",
            "Tipo documental",
            (types.data ?? []).map((type) => ({
              value: type.id,
              label: type.is_active ? type.name : `${type.name} (inactivo)`,
            })),
            types.isPending,
          )}
          {select(
            "bank_product_id",
            "Producto",
            [
              anyOption("General (todos los productos)"),
              ...(products.data ?? []).map((product) => ({
                value: product.id,
                label: productOptionLabel(product),
              })),
            ],
            products.isPending,
          )}
          {select("purpose_code", "Finalidad", [
            anyOption("Cualquiera"),
            ...purposes.items.map((item) => ({ value: item.code, label: item.label })),
          ])}
          {select("participant_role", "Rol del participante", [
            anyOption("Cualquiera"),
            ...PARTICIPANT_ROLES.map((role) => ({
              value: role,
              label: PARTICIPANT_ROLE_LABELS[role]!,
            })),
          ])}
          {select("employment_profile_code", "Perfil laboral", [
            anyOption("Cualquiera"),
            ...profiles.items.map((item) => ({ value: item.code, label: item.label })),
          ])}
          {select("property_condition_code", "Condición del inmueble", [
            anyOption("Cualquiera"),
            ...conditions.items.map((item) => ({ value: item.code, label: item.label })),
          ])}
        </div>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <Controller
          control={control}
          name="is_required"
          render={({ field }) => (
            <Checkbox
              checked={field.value}
              onChange={(event) => field.onChange(event.target.checked)}
            >
              Obligatorio
            </Checkbox>
          )}
        />
        <Controller
          control={control}
          name="is_waivable"
          render={({ field }) => (
            <Checkbox
              checked={field.value}
              onChange={(event) => field.onChange(event.target.checked)}
            >
              Se puede exonerar
            </Checkbox>
          )}
        />
      </div>

      <div className="grid items-start gap-4 min-[600px]:grid-cols-3">
        {integer("minimum_files", "Archivos mínimos", { min: 1, max: 24 })}
        {integer("validity_days", "Vigencia", {
          min: 1,
          max: 3650,
          optional: true,
          suffix: "días",
          help: "Sin valor, la del tipo.",
        })}
        {integer("sort_order", "Orden en el checklist", { min: 0, max: 100000 })}
      </div>
      <FormField
        id={`${ids}-group`}
        label="Grupo alternativo"
        optional="opcional"
        help="Requisitos del mismo alcance con el mismo código: basta uno de ellos (p. ej. CEDULA_O_PASAPORTE)."
        error={errors.alternative_group_code?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="alternative_group_code"
            render={({ field }) => (
              <Input {...field} {...ctl} maxLength={50} autoComplete="off" className="font-mono" />
            )}
          />
        )}
      </FormField>
      <div className="grid items-start gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-from`}
          label="Vigente desde"
          optional="opcional"
          help={requirement ? undefined : "Sin fecha, desde ahora."}
          error={errors.valid_from?.message}
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
          error={errors.valid_to?.message}
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
