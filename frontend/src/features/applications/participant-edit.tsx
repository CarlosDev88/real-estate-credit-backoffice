"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Checkbox, Input, Radio, Select } from "antd";
import { useEffect, useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Money, MoneyInput } from "@/components/ui/money";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import {
  CatalogSelect,
  LockedAlert,
  maxText,
  NOT_NEGATIVE,
  REQUIRED,
  useEditErrors,
} from "@/features/applications/dossier-kit";
import {
  useAddParticipant,
  useClientOptions,
  useCreateIncomeSource,
  useCurrentVersion,
  useDeleteIncomeSource,
  useIncomeSources,
  useRemoveParticipant,
  useSaveFinancialProfile,
  useUpdateIncomeSource,
  useUpdateParticipant,
  type IncomeSource,
  type ParticipantCreateRequest,
} from "@/features/applications/dossier-queries";
import { useCatalog } from "@/features/applications/queries";
import type { FinancialProfile, Participant } from "@/features/applications/workspace-queries";
import { optionsOf } from "@/features/clients/catalog-options";
import { compactPhone, makeClientSchema } from "@/features/clients/client-form";
import { DOCUMENT_TYPE_CATALOG } from "@/features/clients/queries";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { formatDateOnly } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Papel del titular (código de la API): no cambia de papel ni se retira. */
export const PRIMARY = "PRIMARY";
/** Catálogo de los papeles. En la lista y en el panel se usa siempre el `role_label` de la API. */
const PARTICIPANT_ROLE_CATALOG = "participant_role";
/** Papeles que se agregan o a los que se cambia (`RoleCodeEnum`): todos menos el titular. */
type AddableRole = components["schemas"]["RoleCodeEnum"];

/** Opciones de papel del catálogo, sin el titular. */
function useAddableRoles() {
  const { items, isPending } = useCatalog(PARTICIPANT_ROLE_CATALOG);
  const options = useMemo(() => optionsOf(items.filter((item) => item.code !== PRIMARY)), [items]);
  return { options, isPending };
}

const DUPLICATE_CLIENT_DOCUMENT = "DUPLICATE_CLIENT_DOCUMENT";

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="border-border-default grid gap-3 border-t pt-4">
      <h3 id={id} className="m-0 text-base font-semibold">
        {title}
      </h3>
      {children}
    </section>
  );
}

// ---------- agregar ----------

const newClientSchema = makeClientSchema().omit({ origin_type: true });
const addSchema = z
  .object({
    mode: z.enum(["existing", "new"]),
    role_code: z.enum(["CO_APPLICANT", "SOLIDARY_DEBTOR"]),
    client_id: z.string(),
    contributes_income: z.boolean(),
    income_share_cop: z.number().int().min(0, { error: NOT_NEGATIVE }).nullable(),
    // Solo se valida con "Cliente nuevo" (en `superRefine`); con uno existente se ignora.
    client: z.object({
      document_type_code: z.string(),
      document_number: z.string(),
      first_names: z.string(),
      last_names: z.string(),
      email: z.string(),
      phone: z.string(),
      birth_date: z.string(),
    }),
  })
  .superRefine((v, ctx) => {
    if (v.mode === "existing") {
      if (!v.client_id)
        ctx.addIssue({ code: "custom", path: ["client_id"], message: "Elige el cliente." });
      return;
    }
    const parsed = newClientSchema.safeParse(v.client);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        ctx.addIssue({ code: "custom", path: ["client", ...issue.path], message: issue.message });
      }
    }
  });
type AddValues = z.infer<typeof addSchema>;
const EMPTY_ADD: AddValues = {
  mode: "existing",
  role_code: "CO_APPLICANT",
  client_id: "",
  contributes_income: true,
  income_share_cop: null,
  client: {
    document_type_code: "",
    document_number: "",
    first_names: "",
    last_names: "",
    email: "",
    phone: "",
    birth_date: "",
  },
};
const ADD_FIELDS = [
  "role_code",
  "client_id",
  "contributes_income",
  "income_share_cop",
  "client.document_type_code",
  "client.document_number",
  "client.first_names",
  "client.last_names",
  "client.email",
  "client.phone",
  "client.birth_date",
] as const;

/** Busca clientes visibles (espera 300 ms entre teclas). */
function ClientPicker({
  value,
  onChange,
  exclude,
  control,
}: {
  value: string;
  onChange: (value: string) => void;
  exclude: Set<string>;
  control: object;
}) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), 300);
    return () => clearTimeout(id);
  }, [text]);
  const options = useClientOptions(term, true);
  return (
    <Select
      {...control}
      showSearch={{ filterOption: false, onSearch: setText }}
      value={value || undefined}
      onChange={onChange}
      placeholder="Busca por nombre o documento"
      notFoundContent={options.isFetching ? "Buscando…" : "Sin resultados"}
      loading={options.isFetching}
      virtual={false}
      options={(options.data ?? []).map((c) => ({
        value: c.id,
        label: `${c.full_name} · ${c.document_type.code} ${c.document_number}`,
        disabled: exclude.has(c.id),
      }))}
    />
  );
}

/**
 * Agregar un segundo solicitante o un deudor solidario (`POST .../participants`): un
 * cliente existente o uno nuevo con sus datos de identidad. Si el documento ya existe y
 * se ve, se ofrece agregar ese cliente.
 */
export function AddParticipantModal({
  applicationId,
  participants,
  open,
  onClose,
}: {
  applicationId: string;
  participants: Participant[];
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const add = useAddParticipant(applicationId);
  const roles = useAddableRoles();
  const [existing, setExisting] = useState<{ id: string; message: string } | null>(null);
  const form = useForm<AddValues>({ resolver: zodResolver(addSchema), defaultValues: EMPTY_ADD });
  const { onError, locked, clearLocked } = useEditErrors<AddValues>(form.setError, ADD_FIELDS);
  const errors = form.formState.errors;
  const mode = useWatch({ control: form.control, name: "mode" });
  const contributes = useWatch({ control: form.control, name: "contributes_income" });
  const current = new Set(participants.map((p) => p.client.id));

  const close = () => {
    form.reset(EMPTY_ADD);
    setExisting(null);
    clearLocked();
    onClose();
  };

  const send = (body: ParticipantCreateRequest) =>
    add.mutate(body, {
      onSuccess: () => {
        toast.success({ title: "Participante agregado" });
        close();
      },
      onError: (error) => {
        const found =
          isApiError(error) && error.code === DUPLICATE_CLIENT_DOCUMENT
            ? error.details.find((d) => d.resource_id)?.resource_id
            : undefined;
        if (found && isApiError(error)) {
          setExisting({ id: found, message: error.message });
          return;
        }
        onError(error);
      },
    });

  const common = (values: AddValues) => ({
    role_code: values.role_code as AddableRole,
    contributes_income: values.contributes_income,
    income_share_cop: values.contributes_income ? values.income_share_cop : null,
  });

  const submit = form.handleSubmit((values) => {
    setExisting(null);
    if (values.mode === "existing") {
      send({ ...common(values), client_id: values.client_id });
      return;
    }
    const c = values.client;
    send({
      ...common(values),
      document_type_code: c.document_type_code ?? "",
      document_number: (c.document_number ?? "").trim(),
      first_names: (c.first_names ?? "").trim(),
      last_names: (c.last_names ?? "").trim(),
      ...(c.email?.trim() ? { email: c.email.trim() } : {}),
      ...(c.phone?.trim() ? { phone: compactPhone(c.phone.trim()) } : {}),
      ...(c.birth_date ? { birth_date: c.birth_date } : {}),
    });
  });

  const clientText = (
    name: "document_number" | "first_names" | "last_names" | "email" | "phone",
    label: string,
    optional = false,
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={optional ? "opcional" : undefined}
      error={errors.client?.[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={form.control}
          name={`client.${name}`}
          render={({ field }) => <Input {...ctl} {...field} value={field.value ?? ""} />}
        />
      )}
    </FormField>
  );

  return (
    <ActionModal
      open={open}
      title="Agregar participante"
      description="Un segundo solicitante o un deudor solidario. Sus documentos se piden según su papel."
      okText="Agregar"
      loading={add.isPending}
      onSubmit={submit}
      onCancel={close}
      width={600}
    >
      <LockedAlert message={locked} />
      {existing && (
        <Alert
          type="warning"
          showIcon
          title={existing.message}
          action={
            <Button
              size="small"
              onClick={() => send({ ...common(form.getValues()), client_id: existing.id })}
            >
              Agregar ese cliente
            </Button>
          }
        />
      )}
      <FormField id={`${ids}-role`} label="Papel" error={errors.role_code?.message}>
        {(ctl) => (
          <Controller
            control={form.control}
            name="role_code"
            render={({ field }) => (
              <Select
                {...ctl}
                value={field.value}
                onChange={field.onChange}
                options={roles.options}
                loading={roles.isPending}
                virtual={false}
              />
            )}
          />
        )}
      </FormField>
      <Controller
        control={form.control}
        name="mode"
        render={({ field }) => (
          <Radio.Group
            aria-label="Cliente"
            value={field.value}
            onChange={(e) => field.onChange(e.target.value)}
            options={[
              { value: "existing", label: "Cliente existente" },
              { value: "new", label: "Cliente nuevo" },
            ]}
          />
        )}
      />
      {mode === "existing" ? (
        <FormField id={`${ids}-client`} label="Cliente" error={errors.client_id?.message}>
          {(ctl) => (
            <Controller
              control={form.control}
              name="client_id"
              render={({ field }) => (
                <ClientPicker
                  value={field.value}
                  onChange={field.onChange}
                  exclude={current}
                  control={ctl}
                />
              )}
            />
          )}
        </FormField>
      ) : (
        <div className="grid gap-4 min-[600px]:grid-cols-2">
          <FormField
            id={`${ids}-doc-type`}
            label="Tipo de documento"
            error={errors.client?.document_type_code?.message}
          >
            {(ctl) => (
              <Controller
                control={form.control}
                name="client.document_type_code"
                render={({ field }) => (
                  <CatalogSelect
                    {...ctl}
                    catalog={DOCUMENT_TYPE_CATALOG}
                    value={field.value}
                    onChange={(v) => field.onChange(v ?? "")}
                  />
                )}
              />
            )}
          </FormField>
          {clientText("document_number", "Número de documento")}
          {clientText("first_names", "Nombres")}
          {clientText("last_names", "Apellidos")}
          {clientText("email", "Correo", true)}
          {clientText("phone", "Celular", true)}
          <FormField
            id={`${ids}-birth`}
            label="Fecha de nacimiento"
            optional="opcional"
            error={errors.client?.birth_date?.message}
          >
            {(ctl) => (
              <Controller
                control={form.control}
                name="client.birth_date"
                render={({ field }) => (
                  <Input {...ctl} {...field} value={field.value ?? ""} type="date" />
                )}
              />
            )}
          </FormField>
        </div>
      )}
      <IncomeShareFields
        ids={ids}
        control={form.control}
        contributes={contributes}
        shareError={errors.income_share_cop?.message}
      />
    </ActionModal>
  );
}

/** "Aporta ingresos" y, si aporta, cuánto (opcional). */
function IncomeShareFields({
  ids,
  control,
  contributes,
  shareError,
}: {
  ids: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- lo comparten dos formularios
  control: any;
  contributes: boolean;
  shareError?: string;
}) {
  return (
    <>
      <Controller
        control={control}
        name="contributes_income"
        render={({ field }) => (
          <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
            Aporta ingresos al crédito
          </Checkbox>
        )}
      />
      {contributes && (
        <FormField
          id={`${ids}-share`}
          label="Ingreso que aporta"
          optional="opcional"
          help="Mensual. Vacío: se toma su perfil financiero."
          error={shareError}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="income_share_cop"
              render={({ field }) => (
                <MoneyInput
                  {...ctl}
                  className="w-full"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                />
              )}
            />
          )}
        </FormField>
      )}
    </>
  );
}

// ---------- participación ----------

const roleSchema = z.object({
  role_code: z.string(),
  contributes_income: z.boolean(),
  income_share_cop: z.number().int().min(0, { error: NOT_NEGATIVE }).nullable(),
});
type RoleValues = z.infer<typeof roleSchema>;
const ROLE_FIELDS = ["role_code", "contributes_income", "income_share_cop"] as const;

function ParticipationForm({
  applicationId,
  participant,
  version,
  onLocked,
}: {
  applicationId: string;
  participant: Participant;
  version: () => number;
  onLocked: (message: string | null) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const update = useUpdateParticipant(applicationId, version);
  const roles = useAddableRoles();
  const primary = participant.role === PRIMARY;
  const defaults: RoleValues = {
    role_code: participant.role,
    contributes_income: participant.contributes_income,
    income_share_cop: participant.income_share_cop,
  };
  const form = useForm<RoleValues>({ resolver: zodResolver(roleSchema), defaultValues: defaults });
  const { onError, locked } = useEditErrors<RoleValues>(form.setError, ROLE_FIELDS);
  const contributes = useWatch({ control: form.control, name: "contributes_income" });
  useEffect(() => onLocked(locked), [locked, onLocked]);

  const submit = form.handleSubmit((values) =>
    update.mutate(
      {
        participantId: participant.id,
        body: {
          ...(primary ? {} : { role_code: values.role_code as AddableRole }),
          contributes_income: values.contributes_income,
          income_share_cop: values.contributes_income ? values.income_share_cop : null,
        },
      },
      { onSuccess: () => toast.success({ title: "Participación guardada" }), onError },
    ),
  );

  return (
    <form noValidate className="grid gap-3" onSubmit={(e) => void submit(e)}>
      {primary ? (
        <DataList layout="inline">
          <Datum label="Papel">{participant.role_label}</Datum>
        </DataList>
      ) : (
        <FormField
          id={`${ids}-role`}
          label="Papel"
          error={form.formState.errors.role_code?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="role_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value}
                  onChange={field.onChange}
                  options={roles.options}
                  loading={roles.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      )}
      <IncomeShareFields
        ids={ids}
        control={form.control}
        contributes={contributes}
        shareError={form.formState.errors.income_share_cop?.message}
      />
      <div>
        <Button htmlType="submit" loading={update.isPending}>
          Guardar participación
        </Button>
      </div>
    </form>
  );
}

// ---------- perfil financiero ----------

const optionalMoney = z.number().int().min(0, { error: NOT_NEGATIVE });
const profileSchema = z.object({
  employment_profile_code: z.string().min(1, { error: REQUIRED }),
  contract_type_code: z.string().nullable(),
  employer_name: z
    .string()
    .trim()
    .max(180, { error: maxText(180) }),
  job_title: z
    .string()
    .trim()
    .max(120, { error: maxText(120) }),
  employment_start_date: z.string(),
  monthly_income_cop: optionalMoney,
  monthly_expenses_cop: optionalMoney,
  assets_cop: optionalMoney,
  liabilities_cop: optionalMoney,
  funds_origin_code: z.string().nullable(),
});
type ProfileValues = z.infer<typeof profileSchema>;
const PROFILE_FIELDS = Object.keys(profileSchema.shape) as (keyof ProfileValues)[];

function toProfile(profile: FinancialProfile | undefined): ProfileValues {
  return {
    employment_profile_code: profile?.employment_profile.code ?? "",
    contract_type_code: profile?.contract_type?.code ?? null,
    employer_name: profile?.employer_name ?? "",
    job_title: profile?.job_title ?? "",
    employment_start_date: profile?.employment_start_date ?? "",
    monthly_income_cop: profile?.monthly_income_cop ?? 0,
    monthly_expenses_cop: profile?.monthly_expenses_cop ?? 0,
    assets_cop: profile?.assets_cop ?? 0,
    liabilities_cop: profile?.liabilities_cop ?? 0,
    funds_origin_code: profile?.funds_origin?.code ?? null,
  };
}

function ProfileForm({
  applicationId,
  participant,
  profile,
  version,
  onLocked,
}: {
  applicationId: string;
  participant: Participant;
  profile: FinancialProfile | undefined;
  version: () => number;
  onLocked: (message: string | null) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const save = useSaveFinancialProfile(applicationId, version);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toProfile(profile),
  });
  const { onError, locked } = useEditErrors<ProfileValues>(form.setError, PROFILE_FIELDS);
  const errors = form.formState.errors;
  useEffect(() => onLocked(locked), [locked, onLocked]);

  const submit = form.handleSubmit((v) =>
    save.mutate(
      {
        participantId: participant.id,
        body: {
          ...v,
          employment_start_date: v.employment_start_date || null,
        },
      },
      {
        onSuccess: () =>
          toast.success({
            title: "Perfil financiero guardado",
            message: profile?.data_confirmed_at
              ? "Un cambio real deja el perfil sin confirmar por el comprador."
              : undefined,
          }),
        onError,
      },
    ),
  );

  const catalog = (
    name: "employment_profile_code" | "contract_type_code" | "funds_origin_code",
    label: string,
    code: string,
    currentLabel: string | null,
    optional: boolean,
  ) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional={optional ? "opcional" : undefined}
      error={errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <CatalogSelect
              {...ctl}
              catalog={code}
              allowClear={optional}
              currentLabel={currentLabel}
              value={field.value}
              onChange={(v) => field.onChange(optional ? v : (v ?? ""))}
            />
          )}
        />
      )}
    </FormField>
  );

  const moneyField = (
    name: "monthly_income_cop" | "monthly_expenses_cop" | "assets_cop" | "liabilities_cop",
    label: string,
  ) => (
    <FormField id={`${ids}-${name}`} label={label} error={errors[name]?.message}>
      {(ctl) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => (
            <MoneyInput
              {...ctl}
              className="w-full"
              value={field.value}
              onChange={(v) => field.onChange(v ?? 0)}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  const text = (name: "employer_name" | "job_title", label: string) => (
    <FormField
      id={`${ids}-${name}`}
      label={label}
      optional="opcional"
      error={errors[name]?.message}
    >
      {(ctl) => (
        <Controller
          control={form.control}
          name={name}
          render={({ field }) => <Input {...ctl} {...field} />}
        />
      )}
    </FormField>
  );

  return (
    <form noValidate className="grid gap-3" onSubmit={(e) => void submit(e)}>
      {profile && (
        <p className="text-text-tertiary m-0 text-xs">
          {profile.data_confirmed_at
            ? `Confirmado por el comprador el ${formatDateOnly(profile.data_confirmed_at.slice(0, 10)) ?? ""}.`
            : "Sin confirmar por el comprador."}
        </p>
      )}
      <div className="grid gap-3 min-[600px]:grid-cols-2">
        {catalog(
          "employment_profile_code",
          "Perfil laboral",
          "employment_profile",
          profile?.employment_profile.label ?? null,
          false,
        )}
        {catalog(
          "contract_type_code",
          "Tipo de contrato",
          "contract_type",
          profile?.contract_type?.label ?? null,
          true,
        )}
        {text("employer_name", "Empresa")}
        {text("job_title", "Cargo")}
        <FormField
          id={`${ids}-start`}
          label="Desde"
          optional="opcional"
          error={errors.employment_start_date?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="employment_start_date"
              render={({ field }) => <Input {...ctl} {...field} type="date" />}
            />
          )}
        </FormField>
        {catalog(
          "funds_origin_code",
          "Origen de los fondos",
          "funds_origin",
          profile?.funds_origin?.label ?? null,
          true,
        )}
        {moneyField("monthly_income_cop", "Ingreso mensual")}
        {moneyField("monthly_expenses_cop", "Gastos mensuales")}
        {moneyField("assets_cop", "Activos")}
        {moneyField("liabilities_cop", "Pasivos")}
      </div>
      <div>
        <Button htmlType="submit" loading={save.isPending}>
          {profile ? "Guardar perfil" : "Crear perfil"}
        </Button>
      </div>
    </form>
  );
}

// ---------- fuentes de ingreso ----------

const incomeSchema = z.object({
  source_type_code: z.string().min(1, { error: REQUIRED }),
  payer_name: z
    .string()
    .trim()
    .max(180, { error: maxText(180) }),
  monthly_amount_cop: z
    .number()
    .int()
    .min(0, { error: NOT_NEGATIVE })
    .nullable()
    .refine((v) => v !== null, { error: REQUIRED }),
  start_date: z.string(),
  is_primary: z.boolean(),
  notes: z
    .string()
    .trim()
    .max(2000, { error: maxText(2000) }),
});
type IncomeValues = z.input<typeof incomeSchema>;
type IncomeOutput = z.output<typeof incomeSchema>;
const INCOME_FIELDS = Object.keys(incomeSchema.shape) as (keyof IncomeValues)[];

function toIncome(source: IncomeSource | null): IncomeValues {
  return {
    source_type_code: source?.source_type.code ?? "",
    payer_name: source?.payer_name ?? "",
    monthly_amount_cop: source?.monthly_amount_cop ?? null,
    start_date: source?.start_date ?? "",
    is_primary: source?.is_primary ?? false,
    notes: source?.notes ?? "",
  };
}

function IncomeModal({
  applicationId,
  profileId,
  source,
  open,
  version,
  onClose,
}: {
  applicationId: string;
  profileId: string;
  /** La que se edita; `null` para una nueva. */
  source: IncomeSource | null;
  open: boolean;
  version: () => number;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const create = useCreateIncomeSource(applicationId);
  const update = useUpdateIncomeSource(applicationId, version);
  const form = useForm<IncomeValues, unknown, IncomeOutput>({
    resolver: zodResolver(incomeSchema),
    defaultValues: toIncome(source),
  });
  const { onError, locked, clearLocked } = useEditErrors<IncomeValues>(
    form.setError,
    INCOME_FIELDS,
  );
  const errors = form.formState.errors;

  useEffect(() => {
    if (open) {
      form.reset(toIncome(source));
      clearLocked();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open, source?.id]);

  const submit = form.handleSubmit((v) => {
    const body = {
      source_type_code: v.source_type_code,
      payer_name: v.payer_name,
      monthly_amount_cop: v.monthly_amount_cop!,
      start_date: v.start_date || null,
      is_primary: v.is_primary,
      notes: v.notes,
    };
    const done = {
      onSuccess: () => {
        toast.success({ title: source ? "Ingreso actualizado" : "Ingreso agregado" });
        onClose();
      },
      onError,
    };
    if (source) update.mutate({ sourceId: source.id, body }, done);
    else create.mutate({ profileId, body }, done);
  });

  return (
    <ActionModal
      open={open}
      title={source ? "Editar ingreso" : "Agregar ingreso"}
      okText={source ? "Guardar cambios" : "Agregar"}
      loading={create.isPending || update.isPending}
      onSubmit={submit}
      onCancel={onClose}
      width={560}
    >
      <LockedAlert message={locked} />
      <div className="grid gap-4 min-[600px]:grid-cols-2">
        <FormField
          id={`${ids}-type`}
          label="Tipo de ingreso"
          error={errors.source_type_code?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="source_type_code"
              render={({ field }) => (
                <CatalogSelect
                  {...ctl}
                  catalog="income_source_type"
                  currentLabel={source?.source_type.label ?? null}
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? "")}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-amount`}
          label="Monto mensual"
          error={errors.monthly_amount_cop?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="monthly_amount_cop"
              render={({ field }) => (
                <MoneyInput
                  {...ctl}
                  className="w-full"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-payer`}
          label="Pagador"
          optional="opcional"
          error={errors.payer_name?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="payer_name"
              render={({ field }) => <Input {...ctl} {...field} />}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-start`}
          label="Desde"
          optional="opcional"
          error={errors.start_date?.message}
        >
          {(ctl) => (
            <Controller
              control={form.control}
              name="start_date"
              render={({ field }) => <Input {...ctl} {...field} type="date" />}
            />
          )}
        </FormField>
      </div>
      <Controller
        control={form.control}
        name="is_primary"
        render={({ field }) => (
          <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
            Es el ingreso principal
          </Checkbox>
        )}
      />
      <FormField
        id={`${ids}-notes`}
        label="Notas"
        optional="opcional"
        error={errors.notes?.message}
      >
        {(ctl) => (
          <Controller
            control={form.control}
            name="notes"
            render={({ field }) => <Input.TextArea {...ctl} {...field} rows={2} maxLength={2000} />}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

function IncomeSources({
  applicationId,
  profile,
  version,
}: {
  applicationId: string;
  profile: FinancialProfile;
  version: () => number;
}) {
  const toast = useToast();
  const sources = useIncomeSources(applicationId, profile.id);
  const remove = useDeleteIncomeSource(applicationId);
  const { onError, locked } = useEditErrors(() => undefined, []);
  const [editing, setEditing] = useState<IncomeSource | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<IncomeSource | null>(null);

  let body;
  if (sources.isPending) body = <LoadingState label="Cargando los ingresos" blocks={[48]} />;
  else if (sources.isError) {
    body = (
      <ErrorState
        variant="inline"
        title="No pudimos cargar los ingresos."
        onRetry={() => void sources.refetch()}
      />
    );
  } else if (sources.data.length === 0) {
    body = <p className="text-text-secondary m-0 text-sm">Sin fuentes de ingreso registradas.</p>;
  } else {
    body = (
      <ul className="m-0 grid list-none gap-2 p-0" aria-label="Fuentes de ingreso">
        {sources.data.map((source) => (
          <li
            key={source.id}
            className="border-border-default flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <div className="font-medium">
                {source.source_type.label}
                {source.is_primary && (
                  <span className="text-text-tertiary text-xs font-normal"> · principal</span>
                )}
              </div>
              <div className="text-text-tertiary text-xs">
                {[
                  source.payer_name,
                  source.start_date ? `desde ${formatDateOnly(source.start_date)}` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <Money value={source.monthly_amount_cop} className="text-sm font-medium" />
            <Button
              size="small"
              type="text"
              onClick={() => setEditing(source)}
              aria-label={`Editar ${source.source_type.label}`}
            >
              Editar
            </Button>
            <Button
              size="small"
              type="text"
              danger
              onClick={() => setRemoving(source)}
              aria-label={`Quitar ${source.source_type.label}`}
            >
              Quitar
            </Button>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="grid gap-3">
      <LockedAlert message={locked} />
      {body}
      <p className="text-text-tertiary m-0 text-xs">
        Suman <Money value={profile.income_sources_total_cop} /> al mes (informativo: puede diferir
        del ingreso mensual del perfil).
      </p>
      <div>
        <Button onClick={() => setAdding(true)}>Agregar ingreso</Button>
      </div>
      <IncomeModal
        applicationId={applicationId}
        profileId={profile.id}
        source={editing}
        open={adding || !!editing}
        version={version}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
      />
      <ActionModal
        open={!!removing}
        title="Quitar ingreso"
        description={
          removing ? `Se quita "${removing.source_type.label}" del perfil financiero.` : undefined
        }
        okText="Quitar ingreso"
        cancelText="Volver"
        danger
        loading={remove.isPending}
        onCancel={() => setRemoving(null)}
        onSubmit={() =>
          removing &&
          remove.mutate(removing.id, {
            onSuccess: () => {
              toast.success({ title: "Ingreso quitado" });
              setRemoving(null);
            },
            onError: (error) => {
              setRemoving(null);
              onError(error);
            },
          })
        }
      />
    </div>
  );
}

// ---------- panel ----------

/**
 * Panel de un participante: cómo participa (`PATCH`), su perfil financiero (`PUT`) y sus
 * fuentes de ingreso. "Quitar participante" (`DELETE`, con confirmación) no está para el
 * titular. Las escrituras con `If-Match` usan la versión vigente de la solicitud.
 */
export function ParticipantPanel({
  applicationId,
  version,
  participant,
  profile,
  onClose,
}: {
  applicationId: string;
  version: number;
  participant: Participant | null;
  profile: FinancialProfile | undefined;
  onClose: () => void;
}) {
  const toast = useToast();
  const current = useCurrentVersion(applicationId, version);
  const remove = useRemoveParticipant(applicationId);
  const [confirming, setConfirming] = useState(false);
  const [locked, setLocked] = useState<string | null>(null);
  const removeErrors = useEditErrors(() => undefined, []);
  const primary = participant?.role === PRIMARY;
  const shownLock = locked ?? removeErrors.locked;

  return (
    <>
      <SidePanel
        open={!!participant}
        onClose={() => {
          setLocked(null);
          onClose();
        }}
        eyebrow={participant ? participant.role_label : undefined}
        title={participant?.client.full_name ?? ""}
        width={600}
        footer={
          participant && !primary ? (
            <div className="flex justify-between gap-2">
              <Button danger onClick={() => setConfirming(true)}>
                Quitar participante
              </Button>
              <Button onClick={onClose}>Cerrar</Button>
            </div>
          ) : undefined
        }
      >
        {participant && (
          <div className="grid gap-4">
            <LockedAlert message={shownLock} />
            <p className="text-text-tertiary m-0 text-sm">
              Los datos personales se corrigen en la ficha del cliente.
            </p>
            <Section title="Participación">
              <ParticipationForm
                key={`${participant.id}-${participant.updated_at}`}
                applicationId={applicationId}
                participant={participant}
                version={current}
                onLocked={setLocked}
              />
            </Section>
            <Section title="Perfil financiero">
              <ProfileForm
                key={`${participant.id}-${profile?.updated_at ?? "nuevo"}`}
                applicationId={applicationId}
                participant={participant}
                profile={profile}
                version={current}
                onLocked={setLocked}
              />
            </Section>
            <Section title="Fuentes de ingreso">
              {profile ? (
                <IncomeSources applicationId={applicationId} profile={profile} version={current} />
              ) : (
                <p className="text-text-secondary m-0 text-sm">
                  Primero guarda el perfil financiero.
                </p>
              )}
            </Section>
          </div>
        )}
      </SidePanel>
      <ActionModal
        open={confirming}
        title="Quitar participante"
        description={
          participant
            ? `${participant.client.full_name} deja de participar en la solicitud. Sus documentos ya no se piden.`
            : undefined
        }
        okText="Quitar participante"
        cancelText="Volver"
        danger
        loading={remove.isPending}
        onCancel={() => setConfirming(false)}
        onSubmit={() =>
          participant &&
          remove.mutate(participant.id, {
            onSuccess: () => {
              toast.success({ title: "Participante quitado" });
              setConfirming(false);
              onClose();
            },
            onError: (error) => {
              setConfirming(false);
              removeErrors.onError(error);
            },
          })
        }
      />
    </>
  );
}
