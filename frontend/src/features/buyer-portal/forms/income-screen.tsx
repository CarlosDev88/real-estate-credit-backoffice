"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { App, Button, Checkbox, Input } from "antd";
import { useEffect, useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { Card } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Money, MoneyInput } from "@/components/ui/money";
import {
  CatalogSelect,
  DateInput,
  FieldGrid,
  FormActions,
  FormLoadError,
  FormLoading,
  FormScreen,
  NOT_NEGATIVE,
  REQUIRED,
  maxText,
  useSaveErrors,
} from "@/features/buyer-portal/forms/form-kit";
import {
  useBuyerParticipants,
  useConfirmFinancialProfile,
  useFinancialProfile,
  useIncomeSourceActions,
  useIncomeSources,
  useSaveFinancialProfile,
  type BuyerIncomeSource,
  type BuyerParticipantSummary,
} from "@/features/buyer-portal/forms/form-queries";
import { usePortal } from "@/features/buyer-portal/portal-context";
import type { BuyerFinancialProfile } from "@/features/buyer-portal/queries";
import { formatDateOnly, formatDateTime } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

const money = z.number({ error: REQUIRED }).int().min(0, { error: NOT_NEGATIVE });

// ---------- perfil financiero ----------

const profileSchema = z.object({
  employment_profile_code: z.string().min(1, { error: REQUIRED }),
  contract_type_code: z.string().nullable(),
  employer_name: z.string().max(180, { error: maxText(180) }),
  job_title: z.string().max(120, { error: maxText(120) }),
  employment_start_date: z.string().nullable(),
  monthly_income_cop: money,
  monthly_expenses_cop: money,
  assets_cop: money,
  liabilities_cop: money,
  funds_origin_code: z.string().nullable(),
});
type ProfileValues = z.infer<typeof profileSchema>;
const PROFILE_FIELDS = new Set(Object.keys(profileSchema.shape));

function toProfileValues(profile: BuyerFinancialProfile | null): ProfileValues {
  return {
    employment_profile_code: profile?.employment_profile.code ?? "",
    contract_type_code: profile?.contract_type?.code ?? null,
    employer_name: profile?.employer_name ?? "",
    job_title: profile?.job_title ?? "",
    employment_start_date: profile?.employment_start_date ?? null,
    monthly_income_cop: profile?.monthly_income_cop ?? 0,
    monthly_expenses_cop: profile?.monthly_expenses_cop ?? 0,
    assets_cop: profile?.assets_cop ?? 0,
    liabilities_cop: profile?.liabilities_cop ?? 0,
    funds_origin_code: profile?.funds_origin?.code ?? null,
  };
}

type MoneyField = "monthly_income_cop" | "monthly_expenses_cop" | "assets_cop" | "liabilities_cop";
const MONEY_FIELDS: { name: MoneyField; label: string }[] = [
  { name: "monthly_income_cop", label: "Ingreso mensual" },
  { name: "monthly_expenses_cop", label: "Gastos mensuales" },
  { name: "assets_cop", label: "Activos" },
  { name: "liabilities_cop", label: "Pasivos" },
];

function FinancialProfileForm({
  participantId,
  profile,
}: {
  participantId: string;
  profile: BuyerFinancialProfile | null;
}) {
  const { applicationId } = usePortal();
  const id = useId();
  const save = useSaveFinancialProfile(applicationId, participantId);
  const toast = useToast();
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toProfileValues(profile),
  });
  const onError = useSaveErrors(form.setError, (name) => PROFILE_FIELDS.has(name));
  const { errors } = form.formState;

  useEffect(() => form.reset(toProfileValues(profile)), [profile, form]);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      {
        ...values,
        employer_name: values.employer_name.trim(),
        job_title: values.job_title.trim(),
      },
      { onSuccess: () => toast.success({ title: "Guardamos el perfil financiero" }), onError },
    ),
  );

  const select = (
    name: "employment_profile_code" | "contract_type_code" | "funds_origin_code",
    label: string,
    catalog: string,
    optional: boolean,
  ) => (
    <FormField
      id={`${id}-${name}`}
      label={label}
      optional={optional ? "opcional" : undefined}
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
              allowClear={optional}
              value={field.value}
              onChange={(v) => field.onChange(optional ? v : (v ?? ""))}
              onBlur={field.onBlur}
            />
          )}
        />
      )}
    </FormField>
  );

  return (
    <form noValidate onSubmit={(event) => void submit(event)} className="grid gap-4">
      <h3 className="m-0 text-lg font-semibold">Perfil financiero</h3>
      <FieldGrid>
        {select("employment_profile_code", "Perfil laboral", "employment_profile", false)}
        {select("contract_type_code", "Tipo de contrato", "contract_type", true)}
        <FormField
          id={`${id}-employer`}
          label="Empresa"
          optional="opcional"
          error={errors.employer_name?.message}
        >
          {(control) => (
            <Controller
              control={form.control}
              name="employer_name"
              render={({ field }) => <Input {...control} {...field} size="large" />}
            />
          )}
        </FormField>
        <FormField
          id={`${id}-job`}
          label="Cargo"
          optional="opcional"
          error={errors.job_title?.message}
        >
          {(control) => (
            <Controller
              control={form.control}
              name="job_title"
              render={({ field }) => <Input {...control} {...field} size="large" />}
            />
          )}
        </FormField>
        <FormField
          id={`${id}-start`}
          label="Fecha de ingreso"
          optional="opcional"
          error={errors.employment_start_date?.message}
        >
          {(control) => (
            <Controller
              control={form.control}
              name="employment_start_date"
              render={({ field }) => (
                <DateInput
                  {...control}
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                />
              )}
            />
          )}
        </FormField>
        {MONEY_FIELDS.map(({ name, label }) => (
          <FormField key={name} id={`${id}-${name}`} label={label} error={errors[name]?.message}>
            {(control) => (
              <Controller
                control={form.control}
                name={name}
                render={({ field }) => (
                  <MoneyInput
                    {...control}
                    size="large"
                    value={field.value}
                    onChange={(v) => field.onChange(v ?? 0)}
                    onBlur={field.onBlur}
                  />
                )}
              />
            )}
          </FormField>
        ))}
        {select("funds_origin_code", "Origen de los fondos", "funds_origin", true)}
      </FieldGrid>
      <FormActions saving={save.isPending} label="Guardar perfil financiero" />
    </form>
  );
}

// ---------- fuentes de ingreso ----------

const sourceSchema = z.object({
  source_type_code: z.string().min(1, { error: REQUIRED }),
  payer_name: z.string().max(180, { error: maxText(180) }),
  monthly_amount_cop: z
    .number({ error: REQUIRED })
    .int()
    .min(0, { error: NOT_NEGATIVE })
    .nullable()
    .refine((v) => v !== null, { error: REQUIRED }),
  start_date: z.string().nullable(),
  is_primary: z.boolean(),
});
type SourceValues = z.input<typeof sourceSchema>;
type SourceOutput = z.output<typeof sourceSchema>;
const SOURCE_FIELDS = new Set(Object.keys(sourceSchema.shape));

function toSourceValues(source: BuyerIncomeSource | null): SourceValues {
  return {
    source_type_code: source?.source_type.code ?? "",
    payer_name: source?.payer_name ?? "",
    monthly_amount_cop: source?.monthly_amount_cop ?? null,
    start_date: source?.start_date ?? null,
    is_primary: source?.is_primary ?? false,
  };
}

function IncomeSourceModal({
  profileId,
  source,
  open,
  onClose,
}: {
  profileId: string;
  /** `null` para una nueva. */
  source: BuyerIncomeSource | null;
  open: boolean;
  onClose: () => void;
}) {
  const { applicationId } = usePortal();
  const id = useId();
  const actions = useIncomeSourceActions(applicationId, profileId);
  const toast = useToast();
  const form = useForm<SourceValues, unknown, SourceOutput>({
    resolver: zodResolver(sourceSchema),
    defaultValues: toSourceValues(source),
  });
  const onError = useSaveErrors(form.setError, (name) => SOURCE_FIELDS.has(name));
  const { errors } = form.formState;
  const saving = actions.create.isPending || actions.update.isPending;

  useEffect(() => {
    if (open) form.reset(toSourceValues(source));
  }, [open, source, form]);

  const submit = form.handleSubmit((values) => {
    const body = {
      ...values,
      payer_name: values.payer_name.trim(),
    };
    const done = {
      onSuccess: () => {
        toast.success({ title: source ? "Guardamos el ingreso" : "Agregamos el ingreso" });
        onClose();
      },
      onError,
    };
    if (source) actions.update.mutate({ sourceId: source.id, body }, done);
    else actions.create.mutate(body, done);
  });

  return (
    <ActionModal
      open={open}
      title={source ? "Editar ingreso" : "Agregar ingreso"}
      okText="Guardar"
      loading={saving}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField id={`${id}-type`} label="Tipo de ingreso" error={errors.source_type_code?.message}>
        {(control) => (
          <Controller
            control={form.control}
            name="source_type_code"
            render={({ field }) => (
              <CatalogSelect
                {...control}
                catalog="income_source_type"
                value={field.value}
                onChange={(v) => field.onChange(v ?? "")}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      <FormField
        id={`${id}-payer`}
        label="Pagador"
        optional="opcional"
        error={errors.payer_name?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="payer_name"
            render={({ field }) => <Input {...control} {...field} size="large" />}
          />
        )}
      </FormField>
      <FormField
        id={`${id}-amount`}
        label="Monto mensual"
        error={errors.monthly_amount_cop?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="monthly_amount_cop"
            render={({ field }) => (
              <MoneyInput
                {...control}
                size="large"
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      <FormField
        id={`${id}-start`}
        label="Fecha de inicio"
        optional="opcional"
        error={errors.start_date?.message}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="start_date"
            render={({ field }) => (
              <DateInput
                {...control}
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
              />
            )}
          />
        )}
      </FormField>
      <Controller
        control={form.control}
        name="is_primary"
        render={({ field }) => (
          <Checkbox checked={field.value} onChange={(e) => field.onChange(e.target.checked)}>
            Es mi ingreso principal
          </Checkbox>
        )}
      />
    </ActionModal>
  );
}

function IncomeSources({ profileId }: { profileId: string }) {
  const { applicationId, readOnly } = usePortal();
  const sources = useIncomeSources(applicationId, profileId);
  const actions = useIncomeSourceActions(applicationId, profileId);
  const { modal } = App.useApp();
  const toast = useToast();
  const showError = useApiErrorToast();
  const [editing, setEditing] = useState<BuyerIncomeSource | null | undefined>(undefined);

  const confirmRemove = (source: BuyerIncomeSource) =>
    void modal.confirm({
      title: "¿Eliminar este ingreso?",
      content: `${source.source_type.label}${source.payer_name ? ` · ${source.payer_name}` : ""}`,
      okText: "Eliminar",
      okButtonProps: { danger: true },
      cancelText: "Cancelar",
      onOk: () =>
        actions.remove
          .mutateAsync(source.id)
          .then(() => toast.success({ title: "Eliminamos el ingreso" }))
          .catch(showError),
    });

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 text-lg font-semibold">Fuentes de ingreso</h3>
        {!readOnly && (
          <Button className="ml-auto" onClick={() => setEditing(null)}>
            Agregar ingreso
          </Button>
        )}
      </div>
      {sources.isPending && <div className="bg-bg-muted h-16 animate-pulse rounded-lg" />}
      {sources.isError && <p className="text-text-secondary m-0">{sources.error.message}</p>}
      {sources.data?.length === 0 && (
        <p className="text-text-secondary m-0">Todavía no registraste fuentes de ingreso.</p>
      )}
      {!!sources.data?.length && (
        <ul className="border-border-default m-0 grid list-none rounded-lg border p-0">
          {sources.data.map((source) => (
            <li
              key={source.id}
              className="border-border-default flex flex-wrap items-center gap-x-3 gap-y-1 border-b p-3 last:border-b-0"
            >
              {/* En móvil la descripción ocupa la fila; debajo, el monto y las acciones. */}
              <div className="min-w-0 basis-full min-[520px]:flex-1 min-[520px]:basis-0">
                <b className="text-md block font-medium">
                  {source.source_type.label}
                  {source.is_primary && (
                    <span className="text-text-tertiary text-sm font-normal"> · Principal</span>
                  )}
                </b>
                <small className="text-text-tertiary block text-sm">
                  {[
                    source.payer_name,
                    source.start_date && `Desde ${formatDateOnly(source.start_date)}`,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Sin pagador"}
                </small>
              </div>
              <Money value={source.monthly_amount_cop} className="text-md font-medium" />
              {!readOnly && (
                <span className="ml-auto flex gap-1">
                  <Button
                    type="text"
                    onClick={() => setEditing(source)}
                    aria-label={`Editar ${source.source_type.label}`}
                  >
                    Editar
                  </Button>
                  <Button
                    type="text"
                    danger
                    onClick={() => confirmRemove(source)}
                    aria-label={`Eliminar ${source.source_type.label}`}
                  >
                    Eliminar
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <IncomeSourceModal
        profileId={profileId}
        source={editing ?? null}
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
      />
    </div>
  );
}

// ---------- confirmación ----------

function Confirmation({
  participantId,
  profile,
}: {
  participantId: string;
  profile: BuyerFinancialProfile;
}) {
  const { applicationId, readOnly } = usePortal();
  const confirm = useConfirmFinancialProfile(applicationId, participantId);
  const toast = useToast();
  const onError = useSaveErrors(
    () => {},
    () => false,
  );

  if (profile.data_confirmed_at) {
    return (
      <p className="text-tone-success-fg m-0 flex items-center gap-2 font-medium">
        <svg viewBox="0 0 20 20" fill="currentColor" width={18} height={18} aria-hidden="true">
          <path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1.2 13L4.5 9.7l1.4-1.4 2.9 2.9 5.3-5.3 1.4 1.4-6.7 6.7Z" />
        </svg>
        Confirmados el {formatDateTime(profile.data_confirmed_at)}
      </p>
    );
  }
  if (readOnly) return null;
  return (
    <div className="grid gap-2">
      <p className="text-text-secondary m-0 text-sm">
        Cuando todo esté al día, confírmalo para que tu asesor sepa que puede revisarlo.
      </p>
      <Button
        size="large"
        loading={confirm.isPending}
        onClick={() =>
          confirm.mutate(undefined, {
            onSuccess: () => toast.success({ title: "Confirmaste tus datos" }),
            onError,
          })
        }
      >
        Confirmar mis datos
      </Button>
    </div>
  );
}

// ---------- pantalla ----------

function ParticipantIncome({ participant }: { participant: BuyerParticipantSummary }) {
  const { applicationId } = usePortal();
  const profile = useFinancialProfile(applicationId, participant.id);
  return (
    <Card
      variant="portal"
      id={`participante-${participant.id}`}
      title={
        <>
          {participant.full_name}
          <span className="text-text-tertiary text-md font-normal">
            {" "}
            · {participant.role_label}
          </span>
        </>
      }
    >
      {profile.isPending && <FormLoading />}
      {profile.isError && (
        <FormLoadError message={profile.error.message} onRetry={() => void profile.refetch()} />
      )}
      {profile.isSuccess && (
        <>
          <FinancialProfileForm participantId={participant.id} profile={profile.data} />
          {profile.data ? (
            <>
              <IncomeSources profileId={profile.data.id} />
              <Confirmation participantId={participant.id} profile={profile.data} />
            </>
          ) : (
            <p className="text-text-secondary m-0 text-sm">
              Guarda el perfil financiero para agregar tus fuentes de ingreso.
            </p>
          )}
        </>
      )}
    </Card>
  );
}

/** `/portal/ingresos`: una sección por participante que aporta ingresos. */
export function IncomeScreen() {
  const { applicationId } = usePortal();
  const participants = useBuyerParticipants(applicationId);
  const earners = participants.data?.filter((p) => p.contributes_income) ?? [];

  // El enlace del inicio apunta a `#participante-<id>`: se desplaza al llegar los datos.
  useEffect(() => {
    if (!participants.data || !window.location.hash) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
  }, [participants.data]);

  return (
    <FormScreen
      title="Ingresos y gastos"
      description="El perfil financiero y los ingresos de cada persona que aporta a la solicitud."
    >
      {participants.isPending && <FormLoading />}
      {participants.isError && (
        <FormLoadError
          message={participants.error.message}
          onRetry={() => void participants.refetch()}
        />
      )}
      {participants.data && earners.length === 0 && (
        <p className="text-text-secondary m-0">Nadie de la solicitud aporta ingresos todavía.</p>
      )}
      {earners.map((participant) => (
        <ParticipantIncome key={participant.id} participant={participant} />
      ))}
    </FormScreen>
  );
}
