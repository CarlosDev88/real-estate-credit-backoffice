"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Input, Select } from "antd";
import { useId } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { ToneBadge } from "@/components/ui/status-badge";
import { useCatalog } from "@/features/admin-common/catalogs";
import { fromLocalInput } from "@/features/admin-common/datetime";
import {
  labelIn,
  PARTICIPANT_ROLE_LABELS,
  PARTICIPANT_ROLES,
  type ParticipantRole,
} from "@/features/admin-documents/labels";
import {
  productOptionLabel,
  usePreviewChecklist,
  useProductOptions,
  type PreviewResponse,
} from "@/features/admin-documents/queries";
import {
  EMPLOYMENT_CATALOG,
  PROPERTY_CONDITION_CATALOG,
  PURPOSE_CATALOG,
} from "@/features/admin-documents/requirement-form-modal";
import { requirementTerms } from "@/features/admin-documents/requirements-tab";

// Vista previa del checklist (`POST /document-requirements/preview`): qué documentos se
// pedirían a un caso con los requisitos publicados y vigentes, sin tocar solicitudes.

const MAX_PARTICIPANTS = 10;
const ANY = "";

const schema = z.object({
  bank_product_id: z.string(),
  purpose_code: z.string(),
  property_condition_code: z.string(),
  at: z.string(),
  participants: z
    .array(
      z.object({
        role: z.enum(PARTICIPANT_ROLES),
        employment_profile_code: z.string(),
      }),
    )
    .min(1)
    .max(MAX_PARTICIPANTS),
});
type PreviewValues = z.infer<typeof schema>;
const FIELDS = ["bank_product_id", "purpose_code", "property_condition_code", "at"] as const;

type PreviewDocument = PreviewResponse["application_requirements"][number];

function DocumentList({ documents, label }: { documents: PreviewDocument[]; label: string }) {
  if (documents.length === 0) {
    return <p className="text-text-tertiary m-0 text-sm">No se le pide ningún documento.</p>;
  }
  return (
    <ul aria-label={label} className="m-0 grid list-none p-0">
      {documents.map((document) => (
        <li
          key={document.requirement_id}
          className="border-border-default flex flex-wrap items-center gap-2 border-b py-2 text-sm last:border-b-0"
        >
          <span className="font-medium">{document.document_type.name}</span>
          {document.is_general && <ToneBadge tone="neutral">General</ToneBadge>}
          <span className="text-text-secondary ml-auto text-xs">
            {requirementTerms(document)} · v{document.version}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function PreviewTab() {
  const ids = useId();
  const products = useProductOptions();
  const purposes = useCatalog(PURPOSE_CATALOG);
  const profiles = useCatalog(EMPLOYMENT_CATALOG);
  const conditions = useCatalog(PROPERTY_CONDITION_CATALOG);
  const preview = usePreviewChecklist();
  const { control, handleSubmit, setError, formState } = useForm<PreviewValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      bank_product_id: ANY,
      purpose_code: ANY,
      property_condition_code: ANY,
      at: "",
      participants: [{ role: "PRIMARY", employment_profile_code: ANY }],
    },
  });
  const participants = useFieldArray({ control, name: "participants" });
  const onError = useFormErrorHandler<PreviewValues>(setError, FIELDS);

  const submit = handleSubmit((values) =>
    preview.mutate(
      {
        bank_product_id: values.bank_product_id || null,
        purpose_code: values.purpose_code || null,
        property_condition_code: values.property_condition_code || null,
        at: fromLocalInput(values.at),
        participants: values.participants.map((p) => ({
          role: p.role as ParticipantRole,
          employment_profile_code: p.employment_profile_code || null,
        })),
      },
      { onError },
    ),
  );

  const select = (
    name: "bank_product_id" | "purpose_code" | "property_condition_code",
    label: string,
    options: { value: string; label: string }[],
    emptyLabel: string,
    loading = false,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} error={formState.errors[name]?.message}>
      {(ctl) => (
        <Controller
          control={control}
          name={name}
          render={({ field }) => (
            <Select
              {...ctl}
              value={field.value}
              onChange={field.onChange}
              loading={loading}
              showSearch={{ optionFilterProp: "label" }}
              options={[{ value: ANY, label: emptyLabel }, ...options]}
            />
          )}
        />
      )}
    </FormField>
  );

  const result = preview.data;

  return (
    <div className="grid items-start gap-4 min-[1100px]:grid-cols-[minmax(0,420px)_1fr]">
      <Card title="Caso">
        <form noValidate onSubmit={(event) => void submit(event)} className="grid gap-4">
          {select(
            "bank_product_id",
            "Producto",
            (products.data ?? []).map((p) => ({ value: p.id, label: productOptionLabel(p) })),
            "Ninguno (solo los generales)",
            products.isPending,
          )}
          {select(
            "purpose_code",
            "Finalidad",
            purposes.items.map((i) => ({ value: i.code, label: i.label })),
            "Sin finalidad",
          )}
          {select(
            "property_condition_code",
            "Condición del inmueble",
            conditions.items.map((i) => ({ value: i.code, label: i.label })),
            "Sin dato",
          )}
          <fieldset className="m-0 grid gap-3 border-0 p-0">
            <legend className="mb-1.5 p-0 text-sm font-medium">Participantes</legend>
            {participants.fields.map((item, index) => (
              <div
                key={item.id}
                className="border-border-default grid items-end gap-2 rounded-md border p-3 min-[600px]:grid-cols-[1fr_1fr_auto]"
              >
                <FormField id={`${ids}-${index}-role`} label={`Rol del participante ${index + 1}`}>
                  {(ctl) => (
                    <Controller
                      control={control}
                      name={`participants.${index}.role`}
                      render={({ field }) => (
                        <Select
                          {...ctl}
                          value={field.value}
                          onChange={field.onChange}
                          virtual={false}
                          options={PARTICIPANT_ROLES.map((role) => ({
                            value: role,
                            label: PARTICIPANT_ROLE_LABELS[role],
                          }))}
                        />
                      )}
                    />
                  )}
                </FormField>
                <FormField id={`${ids}-${index}-profile`} label={`Perfil laboral ${index + 1}`}>
                  {(ctl) => (
                    <Controller
                      control={control}
                      name={`participants.${index}.employment_profile_code`}
                      render={({ field }) => (
                        <Select
                          {...ctl}
                          value={field.value}
                          onChange={field.onChange}
                          virtual={false}
                          options={[
                            { value: ANY, label: "Sin dato" },
                            ...profiles.items.map((i) => ({ value: i.code, label: i.label })),
                          ]}
                        />
                      )}
                    />
                  )}
                </FormField>
                {participants.fields.length > 1 && (
                  <Button
                    onClick={() => participants.remove(index)}
                    aria-label={`Quitar el participante ${index + 1}`}
                  >
                    Quitar
                  </Button>
                )}
              </div>
            ))}
            {participants.fields.length < MAX_PARTICIPANTS && (
              <Button
                className="justify-self-start"
                onClick={() =>
                  participants.append({ role: "CO_APPLICANT", employment_profile_code: ANY })
                }
              >
                Agregar participante
              </Button>
            )}
          </fieldset>
          <FormField
            id={`${ids}-at`}
            label="Fecha del caso"
            optional="opcional"
            help="Sin fecha, ahora: se aplican las versiones vigentes en ese momento."
            error={formState.errors.at?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="at"
                render={({ field }) => <Input {...field} {...ctl} type="datetime-local" />}
              />
            )}
          </FormField>
          <Button type="primary" htmlType="submit" loading={preview.isPending}>
            Ver checklist
          </Button>
        </form>
      </Card>

      <Card title="Checklist que saldría">
        <div aria-live="polite" className="grid gap-5">
          {!result ? (
            <EmptyState
              size="sm"
              title="Arma un caso y mira qué documentos se pedirían"
              description="Usa los requisitos publicados y vigentes, sin tocar solicitudes."
            />
          ) : (
            <>
              {result.participants.map((participant) => (
                <section key={participant.index} className="grid gap-1">
                  <h3 className="m-0 text-base font-semibold">
                    {labelIn(PARTICIPANT_ROLE_LABELS, participant.role)}
                    {participant.employment_profile && (
                      <span className="text-text-secondary font-normal">
                        {" "}
                        · {participant.employment_profile.label}
                      </span>
                    )}
                  </h3>
                  <DocumentList
                    documents={participant.documents}
                    label={`Documentos del participante ${participant.index + 1}`}
                  />
                </section>
              ))}
              <section className="grid gap-1">
                <h3 className="m-0 text-base font-semibold">De la solicitud</h3>
                <DocumentList
                  documents={result.application_requirements}
                  label="Documentos de la solicitud"
                />
              </section>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
