"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input, Select } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { applicationHref } from "@/features/applications/applications-table";
import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useCatalog } from "@/features/applications/queries";
import { useAdvisors } from "@/features/applications/workspace-queries";
import { optionsOf } from "@/features/clients/catalog-options";
import {
  APPLICATION_ALREADY_OPEN,
  LOAN_PURPOSE_CATALOG,
  LOST_REASON_CATALOG,
  useAssignOpportunity,
  useCreateApplication,
  useOpportunity,
  useTransitionOpportunity,
  type OpportunityAction,
  type OpportunityAssignment,
  type OpportunityDetail,
} from "@/features/clients/detail-queries";
import { OpportunityStatus, projectText } from "@/features/clients/opportunities-tab";
import { applyFieldErrors, isApiError } from "@/lib/api/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

export interface PanelPermissions {
  /** `opportunities.assign` y `users.read` (para listar asesores). */
  canAssign: boolean;
  /** `applications.create`. */
  canCreateApplication: boolean;
  /** `users.read`: elegir asesor al crear la solicitud si la oportunidad no tiene. */
  canListAdvisors: boolean;
  /**
   * Id del usuario si puede asignarse a sí mismo: tiene `opportunities.assign` pero no
   * `users.read` (no puede listar asesores). Si no, `null`.
   */
  selfAssignId: string | null;
}

// ---------- asignar asesor ----------

const REASON_MAX = 255;
const assignSchema = z.object({
  advisor_id: z.string().min(1, { error: "Elige el asesor." }),
  reason: z
    .string()
    .trim()
    .max(REASON_MAX, { error: `Máximo ${REASON_MAX} caracteres.` }),
});
type AssignValues = z.infer<typeof assignSchema>;
const ASSIGN_FIELDS = ["advisor_id", "reason"] as const;

function AssignModal({
  clientId,
  opportunity,
  open,
  onClose,
}: {
  clientId: string;
  opportunity: OpportunityDetail;
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const assign = useAssignOpportunity(clientId, opportunity.id);
  const advisors = useAdvisors(open);
  const { control, handleSubmit, setError, reset, formState } = useForm<AssignValues>({
    resolver: zodResolver(assignSchema),
    defaultValues: { advisor_id: "", reason: "" },
  });
  const onError = useFormErrorHandler<AssignValues>(setError, ASSIGN_FIELDS);
  const current = opportunity.assigned_advisor?.id;

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) => {
    assign.mutate(
      { advisor_id: values.advisor_id, reason: values.reason },
      {
        onSuccess: () => {
          toast.success({ title: "Asesor asignado" });
          close();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={open}
      title={current ? "Cambiar asesor" : "Asignar asesor"}
      okText="Asignar"
      loading={assign.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      <FormField id={`${ids}-advisor`} label="Asesor" error={formState.errors.advisor_id?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="advisor_id"
            render={({ field }) => (
              <Select
                {...ctl}
                value={field.value || undefined}
                onChange={field.onChange}
                placeholder="Elige el asesor"
                showSearch={{ optionFilterProp: "label" }}
                loading={advisors.isPending}
                options={(advisors.data ?? [])
                  .filter((user) => user.id !== current)
                  .map((user) => ({ value: user.id, label: user.name || user.email }))}
              />
            )}
          />
        )}
      </FormField>
      <FormField
        id={`${ids}-reason`}
        label="Motivo"
        optional="opcional"
        error={formState.errors.reason?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="reason"
            render={({ field }) => <Input {...field} {...ctl} maxLength={REASON_MAX} />}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- crear solicitud ----------

const applicationSchema = z.object({
  purpose_code: z.string().min(1, { error: "Elige la finalidad del crédito." }),
  assigned_advisor_id: z.string(),
});
type ApplicationValues = z.infer<typeof applicationSchema>;
const APPLICATION_FIELDS = ["purpose_code", "assigned_advisor_id"] as const;

/** Id de la solicitud en curso que devuelve `409 APPLICATION_ALREADY_OPEN`, si es visible. */
export function openApplicationId(error: unknown): string | null {
  if (!isApiError(error) || error.code !== APPLICATION_ALREADY_OPEN) return null;
  return error.details.find((d) => d.resource_id)?.resource_id ?? null;
}

function CreateApplicationModal({
  clientId,
  opportunity,
  canListAdvisors,
  open,
  onClose,
}: {
  clientId: string;
  opportunity: OpportunityDetail;
  canListAdvisors: boolean;
  open: boolean;
  onClose: () => void;
}) {
  const ids = useId();
  const router = useRouter();
  const toast = useToast();
  const showError = useApiErrorToast();
  const create = useCreateApplication(clientId);
  const purposes = useCatalog(LOAN_PURPOSE_CATALOG);
  // Sin asesor en la oportunidad, la API pide uno (`assigned_advisor_id`).
  const needsAdvisor = !opportunity.assigned_advisor;
  const advisors = useAdvisors(open && needsAdvisor && canListAdvisors);
  const [alreadyOpen, setAlreadyOpen] = useState<{ message: string; id: string | null } | null>(
    null,
  );
  const { control, handleSubmit, setError, reset, formState } = useForm<ApplicationValues>({
    resolver: zodResolver(applicationSchema),
    defaultValues: { purpose_code: "", assigned_advisor_id: "" },
  });
  const errors = formState.errors;

  const close = () => {
    reset();
    setAlreadyOpen(null);
    onClose();
  };

  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === APPLICATION_ALREADY_OPEN) {
      setAlreadyOpen({ message: error.message, id: openApplicationId(error) });
      return;
    }
    if (!isApiError(error) || error.details.length === 0) return showError(error);
    // El error de `assigned_advisor_id` va al campo solo si se ve; si no, al aviso.
    const fields =
      needsAdvisor && canListAdvisors ? APPLICATION_FIELDS : (["purpose_code"] as const);
    const leftover = applyFieldErrors(error, setError, fields);
    if (leftover.length) showError(error, leftover);
  };

  const submit = handleSubmit((values) => {
    setAlreadyOpen(null);
    create.mutate(
      {
        opportunity_id: opportunity.id,
        purpose_code: values.purpose_code,
        ...(needsAdvisor && values.assigned_advisor_id
          ? { assigned_advisor_id: values.assigned_advisor_id }
          : {}),
      },
      {
        onSuccess: (application) => {
          toast.success({ title: "Solicitud creada", message: application.code });
          router.push(applicationHref(application.id));
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={open}
      title="Crear solicitud de crédito"
      width={560}
      description="La solicitud empieza en borrador con este cliente como titular. El inmueble y los demás datos se completan en el expediente."
      okText="Crear solicitud"
      loading={create.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      {alreadyOpen && (
        <Alert
          type="warning"
          showIcon
          title={alreadyOpen.message}
          description={
            alreadyOpen.id ? (
              <Link href={applicationHref(alreadyOpen.id)} className="text-text-link underline">
                Ir a la solicitud en curso
              </Link>
            ) : undefined
          }
        />
      )}
      <FormField
        id={`${ids}-purpose`}
        label="Finalidad del crédito"
        error={errors.purpose_code?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="purpose_code"
            render={({ field }) => (
              <Select
                {...ctl}
                value={field.value || undefined}
                onChange={field.onChange}
                placeholder="Elige la finalidad"
                options={optionsOf(purposes.items)}
                loading={purposes.isPending}
                virtual={false}
              />
            )}
          />
        )}
      </FormField>
      {needsAdvisor &&
        (canListAdvisors ? (
          <FormField
            id={`${ids}-advisor`}
            label="Asesor de la solicitud"
            help="La oportunidad no tiene asesor asignado."
            error={errors.assigned_advisor_id?.message}
          >
            {(ctl) => (
              <Controller
                control={control}
                name="assigned_advisor_id"
                render={({ field }) => (
                  <Select
                    {...ctl}
                    value={field.value || undefined}
                    onChange={field.onChange}
                    placeholder="Elige el asesor"
                    showSearch={{ optionFilterProp: "label" }}
                    loading={advisors.isPending}
                    options={(advisors.data ?? []).map((user) => ({
                      value: user.id,
                      label: user.name || user.email,
                    }))}
                  />
                )}
              />
            )}
          </FormField>
        ) : (
          <p className="text-text-secondary m-0 text-sm">
            La oportunidad no tiene asesor asignado: la solicitud necesita uno.
          </p>
        ))}
    </ActionModal>
  );
}

// ---------- transiciones ----------

/**
 * Estados a los que no se llega con `/transitions`: `ASSIGNED` va por `/assignments`
 * ("Asignar asesor") y `CONVERTED` al crear la solicitud (contrato de `available_actions`).
 */
const NOT_BY_TRANSITION = new Set(["ASSIGNED", "CONVERTED"]);
const COMMENT_MAX = 1000;

/** Botones de transición: los de `available_actions` que van por `/transitions`. */
export function transitionActions(opportunity: OpportunityDetail): OpportunityAction[] {
  return opportunity.available_actions.filter((a) => !NOT_BY_TRANSITION.has(a.target_status));
}

const transitionSchema = (reasonRequired: boolean) =>
  z.object({
    reason_code: reasonRequired ? z.string().min(1, { error: "Elige el motivo." }) : z.string(),
    comment: z
      .string()
      .trim()
      .max(COMMENT_MAX, { error: `Máximo ${COMMENT_MAX} caracteres.` }),
  });
type TransitionValues = { reason_code: string; comment: string };
const TRANSITION_FIELDS = ["reason_code", "comment"] as const;

/**
 * Confirmación de una transición destructiva o con motivo (`reason_required`: el motivo
 * sale del catálogo `opportunity_lost_reason`). El texto del botón es el `label` de la API.
 */
function TransitionModal({
  clientId,
  opportunity,
  action,
  onClose,
}: {
  clientId: string;
  opportunity: OpportunityDetail;
  action: OpportunityAction | null;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const transition = useTransitionOpportunity(clientId, opportunity.id);
  const reasons = useCatalog(LOST_REASON_CATALOG);
  const reasonRequired = action?.reason_required ?? false;
  const { control, handleSubmit, setError, reset, formState } = useForm<TransitionValues>({
    resolver: zodResolver(transitionSchema(reasonRequired)),
    defaultValues: { reason_code: "", comment: "" },
  });
  const onError = useFormErrorHandler<TransitionValues>(setError, TRANSITION_FIELDS);

  const close = () => {
    reset({ reason_code: "", comment: "" });
    onClose();
  };

  const submit = handleSubmit((values) => {
    if (!action) return;
    transition.mutate(
      {
        target_status: action.target_status,
        ...(reasonRequired ? { reason_code: values.reason_code } : {}),
        comment: values.comment,
      },
      {
        onSuccess: (updated) => {
          toast.success({ title: action.label, message: updated.status_label });
          close();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={!!action}
      title={action?.label ?? ""}
      description={
        action ? (
          <>
            La oportunidad pasa a <b className="text-text-primary">{action.target_status_label}</b>.
          </>
        ) : undefined
      }
      okText={action?.label ?? "Confirmar"}
      cancelText="Volver"
      danger={action?.kind === "destructive"}
      loading={transition.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      {reasonRequired && (
        <FormField
          id={`${ids}-reason`}
          label="Motivo"
          error={formState.errors.reason_code?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="reason_code"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el motivo"
                  options={optionsOf(reasons.items)}
                  loading={reasons.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
      )}
      <FormField
        id={`${ids}-comment`}
        label="Comentario"
        optional="opcional"
        error={formState.errors.comment?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="comment"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={COMMENT_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- panel ----------

function AssignmentHistory({ assignments }: { assignments: OpportunityAssignment[] }) {
  if (assignments.length === 0) return null;
  return (
    <section aria-labelledby="opportunity-assignments" className="grid gap-2">
      <h3 id="opportunity-assignments" className="m-0 text-sm font-semibold">
        Asignaciones
      </h3>
      <ol className="m-0 grid list-none gap-2 p-0">
        {assignments.map((a) => (
          <li key={a.id} className="text-sm">
            <span className="font-medium">{a.advisor.name}</span>
            <span className="text-text-tertiary">
              {" "}
              · {formatDateTime(a.created_at)}
              {a.assigned_by && ` · por ${a.assigned_by.name}`}
              {a.ended_at && ` · hasta ${formatDate(a.ended_at)}`}
            </span>
            {a.reason && <p className="text-text-secondary m-0">{a.reason}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

type Dialog = "assign" | "application" | null;

function PanelBody({
  clientId,
  opportunity,
  permissions,
}: {
  clientId: string;
  opportunity: OpportunityDetail;
  permissions: PanelPermissions;
}) {
  const [dialog, setDialog] = useState<Dialog>(null);
  const [confirming, setConfirming] = useState<OpportunityAction | null>(null);
  const toast = useToast();
  const showError = useApiErrorToast();
  const assign = useAssignOpportunity(clientId, opportunity.id);
  const transition = useTransitionOpportunity(clientId, opportunity.id);
  const selfId = permissions.selfAssignId;
  // El asesor que crea la oportunidad ya queda asignado: "Asignarme" solo sirve en una
  // `NEW` sin asesor (la que registró un broker o el administrador).
  const canAssignSelf =
    selfId !== null && opportunity.status === "NEW" && !opportunity.assigned_advisor;
  const actions = transitionActions(opportunity);
  // "Crear solicitud" es la conversión: solo si la API ofrece pasar a `CONVERTED`.
  const canConvert =
    permissions.canCreateApplication &&
    opportunity.available_actions.some((a) => a.target_status === "CONVERTED");

  /** Destructivas o con motivo, con confirmación; las demás, directo. */
  const run = (action: OpportunityAction) => {
    if (action.kind === "destructive" || action.reason_required) {
      setConfirming(action);
      return;
    }
    transition.mutate(
      { target_status: action.target_status, comment: "" },
      {
        onSuccess: (updated) =>
          toast.success({ title: action.label, message: updated.status_label }),
        onError: (error) => showError(error),
      },
    );
  };

  const assignSelf = () => {
    if (!selfId) return;
    assign.mutate(
      { advisor_id: selfId, reason: "" },
      {
        onSuccess: () => toast.success({ title: "Te asignaste la oportunidad" }),
        onError: (error) => showError(error),
      },
    );
  };

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap gap-2">
        {canConvert && (
          <Button type="primary" onClick={() => setDialog("application")}>
            Crear solicitud de crédito
          </Button>
        )}
        {permissions.canAssign && (
          <Button onClick={() => setDialog("assign")}>
            {opportunity.assigned_advisor ? "Cambiar asesor" : "Asignar asesor"}
          </Button>
        )}
        {canAssignSelf && (
          <Button onClick={assignSelf} loading={assign.isPending}>
            Asignarme
          </Button>
        )}
        {actions.map((action) => (
          <Button
            key={action.code}
            danger={action.kind === "destructive"}
            loading={
              transition.isPending && transition.variables?.target_status === action.target_status
            }
            onClick={() => run(action)}
          >
            {action.label}
          </Button>
        ))}
      </div>

      <DataList>
        <Datum label="Estado">
          <OpportunityStatus status={opportunity.status} label={opportunity.status_label} />
        </Datum>
        <Datum label="Origen">{opportunity.origin.label}</Datum>
        <Datum label="Proyecto">{projectText(opportunity)}</Datum>
        <Datum label="Asesor">{opportunity.assigned_advisor?.name}</Datum>
        <Datum label="Registrada por">{opportunity.origin_user?.name}</Datum>
        <Datum label="Creada">{formatDateTime(opportunity.created_at)}</Datum>
        {opportunity.converted_at && (
          <Datum label="Convertida">{formatDateTime(opportunity.converted_at)}</Datum>
        )}
        {opportunity.lost_reason && (
          <Datum label="Motivo de pérdida">{opportunity.lost_reason.label}</Datum>
        )}
      </DataList>

      <AssignmentHistory assignments={opportunity.assignments} />

      {permissions.canAssign && (
        <AssignModal
          clientId={clientId}
          opportunity={opportunity}
          open={dialog === "assign"}
          onClose={() => setDialog(null)}
        />
      )}
      <TransitionModal
        clientId={clientId}
        opportunity={opportunity}
        action={confirming}
        onClose={() => setConfirming(null)}
      />
      {/* Por el permiso, no por `canConvert`: al crear la solicitud la oportunidad pasa a
          `CONVERTED` y se refresca antes de navegar; si el modal se desmontara, no llegaría
          al expediente nuevo. */}
      {permissions.canCreateApplication && (
        <CreateApplicationModal
          clientId={clientId}
          opportunity={opportunity}
          canListAdvisors={permissions.canListAdvisors}
          open={dialog === "application"}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

/** Panel lateral con el detalle de una oportunidad (`GET /opportunities/{id}`). */
export function OpportunityPanel({
  clientId,
  opportunityId,
  permissions,
  onClose,
}: {
  clientId: string;
  opportunityId: string | null;
  permissions: PanelPermissions;
  onClose: () => void;
}) {
  const query = useOpportunity(opportunityId);
  const notFound = isApiError(query.error) && query.error.status === 404;

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando la oportunidad" blocks={[96]} />;
  } else if (notFound) {
    // Sin "Reintentar": volver a pedir no cambia un 404.
    body = (
      <Alert type="error" showIcon title="No encontramos esta oportunidad o no tienes acceso" />
    );
  } else if (query.isError) {
    body = (
      <ErrorState
        title="No pudimos cargar la oportunidad"
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    body = <PanelBody clientId={clientId} opportunity={query.data} permissions={permissions} />;
  }

  return (
    <SidePanel
      open={opportunityId !== null}
      onClose={onClose}
      width={480}
      eyebrow="Oportunidad"
      title={query.data ? (projectText(query.data) ?? "Sin proyecto") : "…"}
    >
      {body}
    </SidePanel>
  );
}
