"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Drawer, Input, Modal, Select } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { applicationHref } from "@/features/applications/applications-table";
import { FormField, useFormErrorHandler } from "@/features/applications/form-field";
import { useCatalog } from "@/features/applications/queries";
import { useAdvisors } from "@/features/applications/workspace-queries";
import { optionsOf } from "@/features/clients/catalog-options";
import {
  APPLICATION_ALREADY_OPEN,
  LOAN_PURPOSE_CATALOG,
  useAssignOpportunity,
  useCreateApplication,
  useOpportunity,
  type OpportunityAssignment,
  type OpportunityDetail,
} from "@/features/clients/detail-queries";
import { OpportunityStatus, projectText } from "@/features/clients/opportunities-tab";
import { applyFieldErrors, isApiError } from "@/lib/api/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { MOBILE_QUERY } from "@/features/applications/applications-list-screen";
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

function Datum({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-text-tertiary text-xs font-medium">{label}</dt>
      <dd className="m-0">{children}</dd>
    </div>
  );
}

const muted = (text: string | null | undefined) =>
  text ? text : <span className="text-text-tertiary">—</span>;

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
    <Modal
      open={open}
      title={current ? "Cambiar asesor" : "Asignar asesor"}
      onCancel={close}
      okText="Asignar"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={assign.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField
          id={`${ids}-advisor`}
          label="Asesor"
          error={formState.errors.advisor_id?.message}
        >
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
      </form>
    </Modal>
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
    <Modal
      open={open}
      title="Crear solicitud de crédito"
      width={560}
      onCancel={close}
      okText="Crear solicitud"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={create.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <p className="text-text-secondary m-0 text-sm">
          La solicitud empieza en borrador con este cliente como titular. El inmueble y los demás
          datos se completan en el expediente.
        </p>
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
      </form>
    </Modal>
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
            <span className="font-medium">{a.advisor?.name ?? "—"}</span>
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
  const toast = useToast();
  const showError = useApiErrorToast();
  const assign = useAssignOpportunity(clientId, opportunity.id);
  const assignments = opportunity.assignments as unknown as OpportunityAssignment[];
  const selfId = permissions.selfAssignId;
  const canAssignSelf = selfId !== null && opportunity.assigned_advisor?.id !== selfId;

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
        {permissions.canCreateApplication && (
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
      </div>

      <dl className="m-0 grid gap-4 min-[480px]:grid-cols-2">
        <Datum label="Estado">
          <OpportunityStatus status={opportunity.status} />
        </Datum>
        <Datum label="Origen">{opportunity.origin.label}</Datum>
        <Datum label="Proyecto">{muted(projectText(opportunity))}</Datum>
        <Datum label="Asesor">{muted(opportunity.assigned_advisor?.name)}</Datum>
        <Datum label="Registrada por">{muted(opportunity.origin_user?.name)}</Datum>
        <Datum label="Creada">{formatDateTime(opportunity.created_at)}</Datum>
        {opportunity.converted_at && (
          <Datum label="Convertida">{formatDateTime(opportunity.converted_at)}</Datum>
        )}
        {opportunity.lost_reason && (
          <Datum label="Motivo de pérdida">{opportunity.lost_reason.label}</Datum>
        )}
      </dl>

      <AssignmentHistory assignments={assignments} />

      {permissions.canAssign && (
        <AssignModal
          clientId={clientId}
          opportunity={opportunity}
          open={dialog === "assign"}
          onClose={() => setDialog(null)}
        />
      )}
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
  const mobile = useMediaQuery(MOBILE_QUERY);
  const query = useOpportunity(opportunityId);
  const notFound = isApiError(query.error) && query.error.status === 404;

  let body;
  if (query.isPending) {
    body = (
      <div
        role="status"
        aria-label="Cargando la oportunidad"
        className="bg-bg-muted h-24 animate-pulse rounded"
      />
    );
  } else if (query.isError) {
    body = (
      <Alert
        type="error"
        showIcon
        title={
          notFound
            ? "No encontramos esta oportunidad o no tienes acceso"
            : "No pudimos cargar la oportunidad"
        }
        description={notFound ? undefined : query.error.message}
        action={
          notFound ? undefined : (
            <Button size="small" onClick={() => void query.refetch()}>
              Reintentar
            </Button>
          )
        }
      />
    );
  } else {
    body = <PanelBody clientId={clientId} opportunity={query.data} permissions={permissions} />;
  }

  return (
    <Drawer
      open={opportunityId !== null}
      onClose={onClose}
      placement="right"
      size={mobile ? "100%" : 480}
      closable={{ "aria-label": "Cerrar" }}
      destroyOnHidden
      title={
        <div>
          <div className="text-text-tertiary text-sm font-normal">Oportunidad</div>
          <h2 className="m-0 text-lg font-semibold">
            {query.data ? (projectText(query.data) ?? "Sin proyecto") : "…"}
          </h2>
        </div>
      }
    >
      {body}
    </Drawer>
  );
}
