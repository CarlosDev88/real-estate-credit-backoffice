"use client";

import { DataList, Datum, Card } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import {
  formatPct,
  SHARE_STATUS_OPTIONS,
  ShareStatusBadge,
} from "@/features/commissions/commission-badges";
import {
  CommissionFilters,
  filterErrors,
  type FilterDef,
} from "@/features/commissions/commission-filters";
import { PAGE_SIZES, useMyCommissionParams } from "@/features/commissions/commissions-params";
import { useMyCommissions, type MyCommission } from "@/features/commissions/queries";
import { formatDateOnly } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const MOBILE_QUERY = "(max-width: 860px)";
const FILTER_KEYS = ["status", "date_from", "date_to"] as const;

// Solo lo que trae `GET /me/commissions`: la parte propia, sin base, tasa, total ni la
// parte del otro beneficiario.
const col = dataColumns<MyCommission>();
const COLUMNS = col.columns([
  col.accessor((r) => r.application_code, {
    id: "application_code",
    header: "Solicitud",
    cell: ({ row }) => (
      <span className="font-mono text-sm font-medium">{row.original.application_code}</span>
    ),
  }),
  col.accessor((r) => r.client_display_name, { id: "client", header: "Cliente" }),
  col.accessor((r) => r.disbursed_on, {
    id: "disbursed_on",
    header: "Desembolso",
    cell: ({ row }) => formatDateOnly(row.original.disbursed_on),
  }),
  col.accessor((r) => r.share_pct, {
    id: "share_pct",
    header: "Porción",
    cell: ({ row }) => <span className="tabular-nums">{formatPct(row.original.share_pct)}</span>,
  }),
  col.accessor((r) => r.amount_cop, {
    id: "amount",
    header: "Monto",
    cell: ({ row }) => <Money value={row.original.amount_cop} />,
  }),
  col.display({
    id: "status",
    header: "Estado",
    cell: ({ row }) => (
      <ShareStatusBadge code={row.original.status} label={row.original.status_label} />
    ),
  }),
  col.accessor((r) => r.paid_at, {
    id: "paid_at",
    header: "Pagada el",
    cell: ({ row }) =>
      formatDateOnly(row.original.paid_at) ?? <span className="text-text-tertiary">—</span>,
  }),
]);

function MyCommissionCard({ row }: { row: MyCommission }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-medium">{row.application_code}</span>
        <span className="ml-auto">
          <ShareStatusBadge code={row.status} label={row.status_label} />
        </span>
      </div>
      <DataList layout="inline">
        <Datum label="Cliente">{row.client_display_name}</Datum>
        <Datum label="Desembolso">{formatDateOnly(row.disbursed_on)}</Datum>
        <Datum label="Porción">{formatPct(row.share_pct)}</Datum>
        <Datum label="Monto">
          <Money value={row.amount_cop} />
        </Datum>
        <Datum label="Pagada el">{formatDateOnly(row.paid_at)}</Datum>
      </DataList>
    </>
  );
}

/** Mis comisiones (`/mis-comisiones`, con `commissions.read_own`): asesor y broker. */
export function MyCommissionsScreen() {
  const { params, update } = useMyCommissionParams();
  const list = useMyCommissions(params);
  const mobile = useMediaQuery(MOBILE_QUERY);
  const errors = filterErrors(list.error, FILTER_KEYS);
  const hasErrors = Object.keys(errors).length > 0;
  const filtered = !!(params.status || params.date_from || params.date_to);

  const defs: FilterDef[] = [
    { type: "date", key: "date_from", label: "Desde", max: params.date_to || undefined },
    { type: "date", key: "date_to", label: "Hasta", min: params.date_from || undefined },
    {
      type: "select",
      key: "status",
      label: "Estado",
      allLabel: "todos",
      options: SHARE_STATUS_OPTIONS,
      width: 220,
    },
  ];

  let content;
  if (list.isPending) {
    content = <LoadingState label="Cargando tus comisiones" blocks={[52, 52, 52]} />;
  } else if (list.isError) {
    content = hasErrors ? (
      <p className="text-text-secondary m-0 text-sm">Corrige los filtros marcados.</p>
    ) : (
      <ErrorState
        title="No pudimos cargar tus comisiones"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (list.data.items.length === 0) {
    content = (
      <EmptyState
        size="sm"
        title={filtered ? "No hay comisiones con estos filtros" : "Todavía no tienes comisiones"}
        description={
          filtered ? undefined : "Aparecen aquí cuando una solicitud tuya se desembolsa."
        }
      />
    );
  } else {
    const busy = list.isFetching && list.isPlaceholderData;
    content = (
      <div className="-mx-5 -mb-5">
        {mobile ? (
          <CardList
            ariaLabel="Mis comisiones"
            rows={list.data.items}
            getRowId={(r) => r.id}
            renderCard={(row) => <MyCommissionCard row={row} />}
            busy={busy}
          />
        ) : (
          <DataTable
            ariaLabel="Mis comisiones"
            columns={COLUMNS}
            rows={list.data.items}
            getRowId={(r) => r.id}
            busy={busy}
            alignRight={["share_pct", "amount"]}
            minWidth={820}
          />
        )}
        <ListPagination
          page={params.page}
          pageSize={params.page_size}
          total={list.data.total}
          itemsLabel="Comisiones"
          onPage={(page) => update({ page })}
          onPageSize={(page_size) => update({ page_size })}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Mis comisiones"
        description="Tu parte de cada desembolso, con su estado de pago."
      />
      <CommissionFilters
        defs={defs}
        values={{ status: params.status, date_from: params.date_from, date_to: params.date_to }}
        errors={errors}
        onChange={(patch) => update(patch)}
        onClear={() => update({ status: "", date_from: "", date_to: "" })}
        active={filtered}
        mobile={mobile}
      />
      <Card title="Comisiones" className="min-w-0">
        {content}
      </Card>
    </div>
  );
}
