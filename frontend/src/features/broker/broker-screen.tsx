"use client";

import { Button, Select } from "antd";
import { useMemo, useState } from "react";

import { Card, DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { StatusBadge } from "@/components/ui/status-badge";
import { BuyerLinkModal } from "@/features/applications/action-modals";
import { useMe } from "@/features/auth/queries";
import {
  OPPORTUNITY_STATUSES,
  PAGE_SIZES,
  useBrokerParams,
  type BrokerTab,
  type OpportunityStatusCode,
} from "@/features/broker/broker-params";
import { ProspectModal } from "@/features/broker/prospect-modal";
import {
  useBrokerApplications,
  useBrokerOpportunities,
  useStatusSnapshot,
  type ApplicationSummary,
  type BrokerOpportunity,
  type StatusCount,
} from "@/features/broker/queries";
import { useCatalogLabel } from "@/features/clients/catalog-options";
import { OPPORTUNITY_STATUS_CATALOG } from "@/features/clients/detail-queries";
import { OpportunityStatus } from "@/features/clients/opportunities-tab";
import { formatDate } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const MOBILE_QUERY = "(max-width: 860px)";
const NO_PROJECT = "Sin proyecto";
const NO_ADVISOR = "Sin asesor todavía";

const days = (n: number) => (n === 1 ? "1 día" : `${n} días`);
const bankText = (a: ApplicationSummary) =>
  [a.bank_name, a.product_name].filter(Boolean).join(" · ") || null;
const dash = <span className="text-text-tertiary">—</span>;

// ---------- resumen de estados ----------

/** Foto de hoy por estado de sus solicitudes (conteos de la API). */
function StatusSummary({ snapshot }: { snapshot: StatusCount[] }) {
  const total = snapshot.reduce((sum, s) => sum + s.count, 0);
  return (
    <Card
      title="Estado de tus solicitudes"
      action={<span className="text-sm">{total} en total</span>}
    >
      {total === 0 ? (
        <p className="text-text-secondary m-0 text-sm">
          Todavía no hay solicitudes de tus prospectos.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-2 p-0">
          {snapshot
            .filter((s) => s.count > 0)
            .map((s) => (
              <li key={s.status} className="flex items-center gap-2">
                <StatusBadge kind="application" code={s.status} label={s.status_label} />
                <span className="font-semibold tabular-nums">{s.count}</span>
              </li>
            ))}
        </ul>
      )}
    </Card>
  );
}

/** La tarjeta del resumen con un esqueleto del alto de la lista de estados de la demo. */
function StatusSummarySkeleton() {
  return (
    <Card title="Estado de tus solicitudes">
      <div aria-busy="true">
        <span className="sr-only" role="status">
          Cargando el estado de tus solicitudes
        </span>
        <div
          aria-hidden="true"
          className="bg-bg-muted h-36 animate-pulse rounded-lg motion-reduce:animate-none min-[600px]:h-14 min-[1100px]:h-7"
        />
      </div>
    </Card>
  );
}

// ---------- prospectos ----------

const opCol = dataColumns<BrokerOpportunity>();
const OPPORTUNITY_COLUMNS = opCol.columns([
  opCol.accessor((r) => r.client_name, {
    id: "client",
    header: "Cliente",
    cell: ({ row }) => <span className="font-medium">{row.original.client_name}</span>,
  }),
  opCol.accessor((r) => r.project_name, {
    id: "project",
    header: "Proyecto",
    cell: ({ row }) =>
      row.original.project_name ?? <span className="text-text-tertiary">{NO_PROJECT}</span>,
  }),
  opCol.display({
    id: "status",
    header: "Estado",
    cell: ({ row }) => (
      <OpportunityStatus status={row.original.status} label={row.original.status_label} />
    ),
  }),
  opCol.accessor((r) => r.advisor_name, {
    id: "advisor",
    header: "Asesor",
    cell: ({ row }) =>
      row.original.advisor_name ?? <span className="text-text-tertiary">{NO_ADVISOR}</span>,
  }),
  opCol.accessor((r) => r.updated_at, {
    id: "updated_at",
    header: "Actualizado",
    cell: ({ row }) => (
      <span className="text-text-secondary text-sm">{formatDate(row.original.updated_at)}</span>
    ),
  }),
]);

function OpportunityCard({ row }: { row: BrokerOpportunity }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="min-w-0 truncate font-medium">{row.client_name}</span>
        <span className="text-text-tertiary ml-auto text-xs">{formatDate(row.updated_at)}</span>
      </div>
      <div>
        <OpportunityStatus status={row.status} label={row.status_label} />
      </div>
      <DataList layout="inline">
        <Datum label="Proyecto">{row.project_name ?? NO_PROJECT}</Datum>
        <Datum label="Asesor">{row.advisor_name ?? NO_ADVISOR}</Datum>
      </DataList>
    </>
  );
}

function OpportunitiesPanel({
  status,
  page,
  pageSize,
  mobile,
  canCreate,
  onStatus,
  onPage,
  onPageSize,
  onCreate,
}: {
  status: OpportunityStatusCode | "";
  page: number;
  pageSize: number;
  mobile: boolean;
  canCreate: boolean;
  onStatus: (status: OpportunityStatusCode | "") => void;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  onCreate: () => void;
}) {
  const list = useBrokerOpportunities(
    { tab: "prospectos", status, page, page_size: pageSize },
    true,
  );
  const label = useCatalogLabel(OPPORTUNITY_STATUS_CATALOG);

  let content;
  if (list.isPending)
    content = <LoadingState label="Cargando tus prospectos" blocks={[52, 52, 52]} />;
  else if (list.isError) {
    content = (
      <ErrorState
        title="No pudimos cargar tus prospectos"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (list.data.items.length === 0) {
    content = (
      <EmptyState
        size="sm"
        title={status ? "No tienes prospectos en este estado" : "Todavía no tienes prospectos"}
        description={status ? undefined : 'Registra el primero con "Nuevo prospecto".'}
        action={
          !status && canCreate ? (
            <Button type="primary" onClick={onCreate}>
              Nuevo prospecto
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
            ariaLabel="Prospectos"
            rows={list.data.items}
            getRowId={(r) => r.id}
            renderCard={(row) => <OpportunityCard row={row} />}
            busy={busy}
          />
        ) : (
          <DataTable
            ariaLabel="Prospectos"
            columns={OPPORTUNITY_COLUMNS}
            rows={list.data.items}
            getRowId={(r) => r.id}
            busy={busy}
            minWidth={760}
          />
        )}
        <ListPagination
          page={page}
          pageSize={pageSize}
          total={list.data.total}
          itemsLabel="Prospectos"
          onPage={onPage}
          onPageSize={onPageSize}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <Card
      title="Prospectos"
      className="min-w-0"
      action={
        <Select
          aria-label="Filtrar por estado"
          value={status}
          onChange={onStatus}
          options={[
            { value: "", label: "todos" },
            ...OPPORTUNITY_STATUSES.map((code) => ({ value: code, label: label(code) })),
          ]}
          labelRender={() => `Estado: ${status ? label(status) : "todos"}`}
          virtual={false}
          popupMatchSelectWidth={false}
          style={{ width: 220 }}
        />
      }
    >
      {content}
    </Card>
  );
}

// ---------- solicitudes ----------

function ApplicationCard({
  row,
  onSendLink,
}: {
  row: ApplicationSummary;
  onSendLink?: (row: ApplicationSummary) => void;
}) {
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-medium">{row.code}</span>
        <span className="text-text-tertiary ml-auto text-xs">{formatDate(row.updated_at)}</span>
      </div>
      <div>
        <StatusBadge kind="application" code={row.status} label={row.status_label} />
      </div>
      <DataList layout="inline">
        <Datum label="Cliente">{row.client_name}</Datum>
        <Datum label="Banco">{bankText(row)}</Datum>
        <Datum label="Asesor">{row.advisor_name}</Datum>
        <Datum label="En la etapa">{days(row.days_in_stage)}</Datum>
      </DataList>
      {onSendLink && (
        <div>
          <Button onClick={() => onSendLink(row)}>Enviar enlace</Button>
        </div>
      )}
    </>
  );
}

function ApplicationsPanel({
  page,
  pageSize,
  mobile,
  onSendLink,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  mobile: boolean;
  onSendLink?: (row: ApplicationSummary) => void;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  const list = useBrokerApplications(
    { tab: "solicitudes", status: "", page, page_size: pageSize },
    true,
  );
  const columns = useMemo(() => {
    const col = dataColumns<ApplicationSummary>();
    return col.columns([
      col.accessor((r) => r.code, {
        id: "code",
        header: "Código",
        cell: ({ row }) => (
          <span className="font-mono text-sm font-medium">{row.original.code}</span>
        ),
      }),
      col.accessor((r) => r.client_name, { id: "client", header: "Cliente" }),
      col.display({
        id: "status",
        header: "Estado",
        cell: ({ row }) => (
          <StatusBadge
            kind="application"
            code={row.original.status}
            label={row.original.status_label}
          />
        ),
      }),
      col.display({
        id: "bank",
        header: "Banco",
        cell: ({ row }) => bankText(row.original) ?? dash,
      }),
      col.accessor((r) => r.advisor_name, { id: "advisor", header: "Asesor" }),
      col.accessor((r) => r.days_in_stage, {
        id: "days",
        header: "En la etapa",
        cell: ({ row }) => <span className="tabular-nums">{days(row.original.days_in_stage)}</span>,
      }),
      ...(onSendLink
        ? [
            col.display({
              id: "actions",
              header: () => <span className="sr-only">Acciones</span>,
              cell: ({ row }) => (
                <Button
                  size="small"
                  onClick={() => onSendLink(row.original)}
                  aria-label={`Enviar enlace de ${row.original.code}`}
                >
                  Enviar enlace
                </Button>
              ),
            }),
          ]
        : []),
    ]);
  }, [onSendLink]);

  let content;
  if (list.isPending)
    content = <LoadingState label="Cargando las solicitudes" blocks={[52, 52, 52]} />;
  else if (list.isError) {
    content = (
      <ErrorState
        title="No pudimos cargar las solicitudes"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (list.data.items.length === 0) {
    content = (
      <EmptyState
        size="sm"
        title="Todavía no hay solicitudes"
        description="Aparecen aquí cuando el asesor crea la solicitud de uno de tus prospectos."
      />
    );
  } else {
    const busy = list.isFetching && list.isPlaceholderData;
    content = (
      <div className="-mx-5 -mb-5">
        {mobile ? (
          <CardList
            ariaLabel="Solicitudes"
            rows={list.data.items}
            getRowId={(r) => r.id}
            renderCard={(row) => <ApplicationCard row={row} onSendLink={onSendLink} />}
            busy={busy}
          />
        ) : (
          <DataTable
            ariaLabel="Solicitudes"
            columns={columns}
            rows={list.data.items}
            getRowId={(r) => r.id}
            busy={busy}
            stickyColumn="code"
            alignRight={["days", "actions"]}
            minWidth={900}
          />
        )}
        <ListPagination
          page={page}
          pageSize={pageSize}
          total={list.data.total}
          itemsLabel="Solicitudes"
          onPage={onPage}
          onPageSize={onPageSize}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <Card title="Solicitudes" className="min-w-0">
      <p className="text-text-tertiary m-0 mb-4 text-xs">
        Solo el estado: los documentos y los datos financieros los ve el asesor.
      </p>
      {content}
    </Card>
  );
}

// ---------- pantalla ----------

/**
 * Inicio del broker (`/prospectos`, REQ §6): bandeja de prospectos, alta de cliente y
 * oportunidad, enlace de autogestión para el comprador y el estado de sus solicitudes.
 * Solo lo que la API le responde al broker.
 */
export function BrokerScreen() {
  const me = useMe();
  const permissions = useMemo(() => new Set(me.data?.permissions ?? []), [me.data]);
  const { params, update } = useBrokerParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const canCreate = permissions.has("clients.create") && permissions.has("opportunities.create");
  const canSendLink = permissions.has("buyer_access.create");
  const snapshot = useStatusSnapshot(permissions.has("dashboard.read"));
  const [creating, setCreating] = useState(false);
  const [linkFor, setLinkFor] = useState<ApplicationSummary | null>(null);

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Mis prospectos"
        description="Los compradores que registraste, quién los atiende y cómo van sus solicitudes."
        actions={
          canCreate ? (
            <Button type="primary" onClick={() => setCreating(true)}>
              Nuevo prospecto
            </Button>
          ) : undefined
        }
      />

      {snapshot.data ? (
        <StatusSummary snapshot={snapshot.data} />
      ) : (
        // Mientras carga, la tarjeta ya ocupa su lugar: las pestañas no saltan (PERF-06).
        snapshot.isLoading && <StatusSummarySkeleton />
      )}

      <ScrollTabs
        ariaLabel="Mis prospectos"
        items={[
          { key: "prospectos", label: "Prospectos" },
          { key: "solicitudes", label: "Solicitudes" },
        ]}
        value={params.tab}
        onChange={(tab) => update({ tab: tab as BrokerTab })}
      />

      {params.tab === "prospectos" ? (
        <OpportunitiesPanel
          status={params.status}
          page={params.page}
          pageSize={params.page_size}
          mobile={mobile}
          canCreate={canCreate}
          onStatus={(status) => update({ status })}
          onPage={(page) => update({ page })}
          onPageSize={(page_size) => update({ page_size })}
          onCreate={() => setCreating(true)}
        />
      ) : (
        <ApplicationsPanel
          page={params.page}
          pageSize={params.page_size}
          mobile={mobile}
          onSendLink={canSendLink ? setLinkFor : undefined}
          onPage={(page) => update({ page })}
          onPageSize={(page_size) => update({ page_size })}
        />
      )}

      {canCreate && <ProspectModal open={creating} onClose={() => setCreating(false)} />}
      {canSendLink && (
        <BuyerLinkModal
          applicationId={linkFor?.id ?? ""}
          open={!!linkFor}
          onClose={() => setLinkFor(null)}
          context={linkFor ? `${linkFor.code} · ${linkFor.client_name}` : undefined}
        />
      )}
    </div>
  );
}
