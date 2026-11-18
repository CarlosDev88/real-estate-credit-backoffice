"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Modal, Select } from "antd";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { FormField } from "@/components/ui/form-field";
import { useCatalog } from "@/features/applications/queries";
import { optionsOf, useCatalogLabel } from "@/features/clients/catalog-options";
import { PlusIcon } from "@/features/clients/components/icons";
import {
  OPPORTUNITY_STATUS_CATALOG,
  useActiveProjects,
  useClientOpportunities,
  useCreateOpportunity,
  type Opportunity,
  type OpportunityDetail,
} from "@/features/clients/detail-queries";
import { ORIGIN_CATALOG, type ClientDetail } from "@/features/clients/queries";
import { applyFieldErrors, isApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

/** `409` de `POST /opportunities`: ya hay una oportunidad abierta para ese proyecto. */
export const DUPLICATE_OPPORTUNITY = "DUPLICATE_OPPORTUNITY";

/**
 * Estado de la oportunidad con la etiqueta del catálogo `opportunity_status`. El design
 * system aún no tiene tonos para oportunidades (`toneFor` no tiene ese tipo): va en
 * neutro hasta que el front 1 lo agregue.
 */
export function OpportunityStatus({ status }: { status: string }) {
  const label = useCatalogLabel(OPPORTUNITY_STATUS_CATALOG);
  return <StatusBadge kind="application" code={null} label={label(status)} />;
}

export function projectText(opportunity: Pick<Opportunity, "project">): string | null {
  const project = opportunity.project;
  if (!project) return null;
  return project.partner_name ? `${project.name} · ${project.partner_name}` : project.name;
}

const NO_PROJECT = "Sin proyecto";
const NO_ADVISOR = "Sin asesor";

function OpportunityRow({
  opportunity,
  onOpen,
}: {
  opportunity: Opportunity;
  onOpen: (opportunity: Opportunity) => void;
}) {
  const project = projectText(opportunity);
  const created = formatDate(opportunity.created_at);
  return (
    <li className="border-border-default border-b last:border-b-0">
      <button
        type="button"
        onClick={() => onOpen(opportunity)}
        aria-haspopup="dialog"
        className="hover:bg-brand-subtle focus-visible:outline-focus-ring grid w-full cursor-pointer gap-1 border-0 bg-transparent px-4 py-3 text-left text-inherit focus-visible:outline-2 focus-visible:-outline-offset-2 min-[861px]:grid-cols-[150px_1fr_1fr_1fr_110px] min-[861px]:items-center min-[861px]:gap-3"
      >
        <span>
          <OpportunityStatus status={opportunity.status} />
        </span>
        <span className="min-w-0 truncate font-medium">
          {project ?? <span className="text-text-tertiary font-normal">{NO_PROJECT}</span>}
        </span>
        <span className="text-text-secondary min-w-0 truncate text-sm">
          {opportunity.origin.label}
        </span>
        <span className="text-text-secondary min-w-0 truncate text-sm">
          {opportunity.assigned_advisor?.name ?? (
            <span className="text-text-tertiary">{NO_ADVISOR}</span>
          )}
        </span>
        <span className="text-text-tertiary text-sm min-[861px]:text-right">{created}</span>
      </button>
    </li>
  );
}

const opportunitySchema = z.object({
  origin_type: z.string().min(1, { error: "Elige el origen." }),
  project_id: z.string(),
});
type OpportunityValues = z.infer<typeof opportunitySchema>;
const OPPORTUNITY_FIELDS = ["origin_type", "project_id"] as const;

function NewOpportunityModal({
  client,
  open,
  onClose,
  onCreated,
}: {
  client: ClientDetail;
  open: boolean;
  onClose: () => void;
  onCreated: (opportunity: OpportunityDetail) => void;
}) {
  const ids = useId();
  const toast = useToast();
  const showError = useApiErrorToast();
  const create = useCreateOpportunity(client.id);
  const origins = useCatalog(ORIGIN_CATALOG);
  const projects = useActiveProjects(open);
  const defaults: OpportunityValues = { origin_type: client.origin?.code ?? "", project_id: "" };
  const { control, handleSubmit, setError, reset, formState } = useForm<OpportunityValues>({
    resolver: zodResolver(opportunitySchema),
    values: defaults,
  });
  const errors = formState.errors;

  const close = () => {
    reset(defaults);
    onClose();
  };

  const onError = (error: unknown) => {
    if (isApiError(error) && error.code === DUPLICATE_OPPORTUNITY) {
      setError("project_id", { type: error.code, message: error.message });
      return;
    }
    if (!isApiError(error) || error.details.length === 0) return showError(error);
    const leftover = applyFieldErrors(error, setError, OPPORTUNITY_FIELDS);
    if (leftover.length) showError(error, leftover);
  };

  const submit = handleSubmit((values) => {
    create.mutate(
      {
        client_id: client.id,
        origin_type: values.origin_type,
        project_id: values.project_id || null,
      },
      {
        onSuccess: (opportunity) => {
          toast.success({ title: "Oportunidad creada" });
          close();
          onCreated(opportunity);
        },
        onError,
      },
    );
  });

  return (
    <Modal
      open={open}
      title="Nueva oportunidad"
      width={560}
      onCancel={close}
      okText="Crear oportunidad"
      cancelText="Cancelar"
      onOk={() => void submit()}
      confirmLoading={create.isPending}
      destroyOnHidden
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="grid gap-4 pt-2">
        <FormField id={`${ids}-origin`} label="Origen" error={errors.origin_type?.message}>
          {(ctl) => (
            <Controller
              control={control}
              name="origin_type"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={field.onChange}
                  placeholder="Elige el origen"
                  options={optionsOf(origins.items)}
                  loading={origins.isPending}
                  virtual={false}
                />
              )}
            />
          )}
        </FormField>
        <FormField
          id={`${ids}-project`}
          label="Proyecto"
          optional="opcional"
          help="Solo proyectos activos."
          error={errors.project_id?.message}
        >
          {(ctl) => (
            <Controller
              control={control}
              name="project_id"
              render={({ field }) => (
                <Select
                  {...ctl}
                  value={field.value || undefined}
                  onChange={(value: string | undefined) => field.onChange(value ?? "")}
                  allowClear
                  placeholder={NO_PROJECT}
                  showSearch={{ optionFilterProp: "label" }}
                  options={(projects.data ?? []).map((project) => ({
                    value: project.id,
                    label: `${project.name} · ${project.partner.name}`,
                  }))}
                  loading={projects.isPending}
                />
              )}
            />
          )}
        </FormField>
      </form>
    </Modal>
  );
}

/** Pestaña Oportunidades: lista, "Nueva oportunidad" y apertura del panel lateral. */
export function OpportunitiesTab({
  client,
  canCreate,
  onOpen,
}: {
  client: ClientDetail;
  canCreate: boolean;
  onOpen: (id: string) => void;
}) {
  const query = useClientOpportunities(client.id);
  const [creating, setCreating] = useState(false);
  const items = query.data?.items ?? [];

  let body;
  if (query.isPending) {
    body = (
      <div
        role="status"
        aria-label="Cargando oportunidades"
        className="bg-bg-muted m-4 h-10 animate-pulse rounded"
      />
    );
  } else if (query.isError) {
    body = (
      <div className="p-3">
        <Alert
          type="error"
          showIcon
          title="No pudimos cargar las oportunidades"
          description={query.error.message}
          action={
            <Button size="small" onClick={() => void query.refetch()}>
              Reintentar
            </Button>
          }
        />
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState
        title="Este cliente no tiene oportunidades"
        description={
          canCreate
            ? "Crea una para registrar su interés y, después, su solicitud de crédito."
            : undefined
        }
      />
    );
  } else {
    body = (
      <ul aria-label="Oportunidades" className="m-0 list-none p-0">
        {items.map((opportunity) => (
          <OpportunityRow
            key={opportunity.id}
            opportunity={opportunity}
            onOpen={(o) => onOpen(o.id)}
          />
        ))}
      </ul>
    );
  }

  return (
    <section
      aria-labelledby="client-opportunities"
      className="bg-bg-surface border-border-default max-w-[1100px] overflow-hidden rounded-lg border"
    >
      <div className="border-border-default flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <h2 id="client-opportunities" className="m-0 flex-1 text-base font-semibold">
          Oportunidades
        </h2>
        {canCreate && (
          <Button size="small" icon={<PlusIcon />} onClick={() => setCreating(true)}>
            Nueva oportunidad
          </Button>
        )}
      </div>
      {items.length > 0 && (
        <div
          aria-hidden="true"
          className="bg-bg-subtle text-text-secondary border-border-default hidden grid-cols-[150px_1fr_1fr_1fr_110px] gap-3 border-b px-4 py-2 text-xs font-medium min-[861px]:grid"
        >
          <span>Estado</span>
          <span>Proyecto</span>
          <span>Origen</span>
          <span>Asesor</span>
          <span className="text-right">Creada</span>
        </div>
      )}
      {body}
      {canCreate && (
        <NewOpportunityModal
          client={client}
          open={creating}
          onClose={() => setCreating(false)}
          onCreated={(opportunity) => onOpen(opportunity.id)}
        />
      )}
    </section>
  );
}
