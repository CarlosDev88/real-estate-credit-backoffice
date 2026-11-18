"use client";

import Link from "next/link";
import { useMemo } from "react";

import { Card, DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { Money } from "@/components/ui/money";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { bankLabel, useActiveBanks, useAdvisors } from "@/features/dashboard/queries";
import {
  ReviewBadge,
  SETTLEMENT_STATUS_OPTIONS,
  SettlementStatusBadge,
  ShareStatusBadge,
} from "@/features/commissions/commission-badges";
import {
  CommissionFilters,
  filterErrors,
  type FilterDef,
} from "@/features/commissions/commission-filters";
import {
  EMPTY_SETTLEMENT_FILTERS,
  hasSettlementFilters,
  PAGE_SIZES,
  SETTLEMENT_FILTER_KEYS,
  type SettlementParams,
} from "@/features/commissions/commissions-params";
import {
  useBrokers,
  useSettlements,
  type CommissionSettlement,
  type CommissionShare,
} from "@/features/commissions/queries";
import { SettlementPanel } from "@/features/commissions/settlement-panel";
import { formatDateOnly } from "@/lib/format";

const shareOf = (s: CommissionSettlement, role: CommissionShare["beneficiary_role"]) =>
  s.shares.find((share) => share.beneficiary_role === role);

function ShareCell({ share }: { share: CommissionShare | undefined }) {
  if (!share) return <span className="text-text-tertiary">—</span>;
  return (
    <span className="grid gap-1">
      <span className="font-medium">{share.beneficiary.name}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Money value={share.amount_cop} className="text-text-secondary text-sm" />
        <ShareStatusBadge code={share.status} label={share.status_label} />
      </span>
    </span>
  );
}

function StatusCell({ row }: { row: CommissionSettlement }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      <SettlementStatusBadge code={row.status} label={row.status_label} />
      {row.needs_review && <ReviewBadge />}
    </span>
  );
}

const col = dataColumns<CommissionSettlement>();
const COLUMNS = col.columns([
  col.accessor((r) => r.application.code, {
    id: "application",
    header: "Solicitud",
    cell: ({ row }) => (
      <Link
        href={`/solicitudes/${row.original.application.id}`}
        className="text-text-link font-mono text-sm font-medium"
      >
        {row.original.application.code}
      </Link>
    ),
  }),
  col.accessor((r) => r.disbursed_on, {
    id: "disbursed_on",
    header: "Desembolso",
    cell: ({ row }) => formatDateOnly(row.original.disbursed_on),
  }),
  col.accessor((r) => r.lead_origin_label, { id: "origin", header: "Origen" }),
  col.accessor((r) => r.total_amount_cop, {
    id: "total",
    header: "Total",
    cell: ({ row }) => <Money value={row.original.total_amount_cop} />,
  }),
  col.display({
    id: "advisor",
    header: "Asesor",
    cell: ({ row }) => <ShareCell share={shareOf(row.original, "ADVISOR")} />,
  }),
  col.display({
    id: "broker",
    header: "Broker",
    cell: ({ row }) => <ShareCell share={shareOf(row.original, "INDEPENDENT_BROKER")} />,
  }),
  col.display({
    id: "status",
    header: "Estado",
    cell: ({ row }) => <StatusCell row={row.original} />,
  }),
]);

function SettlementCard({ row }: { row: CommissionSettlement }) {
  const advisor = shareOf(row, "ADVISOR");
  const broker = shareOf(row, "INDEPENDENT_BROKER");
  return (
    <>
      <div className="flex items-center gap-2">
        <Link
          href={`/solicitudes/${row.application.id}`}
          className="text-text-link font-mono text-sm font-medium"
        >
          {row.application.code}
        </Link>
        <span className="text-text-tertiary ml-auto text-xs">
          {formatDateOnly(row.disbursed_on)}
        </span>
      </div>
      <StatusCell row={row} />
      <DataList layout="inline">
        <Datum label="Total">
          <Money value={row.total_amount_cop} />
        </Datum>
        <Datum label="Origen">{row.lead_origin_label}</Datum>
        <Datum label="Asesor">
          {advisor && `${advisor.beneficiary.name} · ${advisor.status_label}`}
        </Datum>
        <Datum label="Broker">
          {broker && `${broker.beneficiary.name} · ${broker.status_label}`}
        </Datum>
      </DataList>
    </>
  );
}

function useFilterDefs(params: SettlementParams, permissions: ReadonlySet<string>): FilterDef[] {
  const canUsers = permissions.has("users.read");
  const canBanks = permissions.has("banks.read");
  const advisors = useAdvisors(canUsers);
  const brokers = useBrokers(canUsers);
  const banks = useActiveBanks(canBanks);
  return useMemo(() => {
    const defs: FilterDef[] = [
      { type: "date", key: "date_from", label: "Desde", max: params.date_to || undefined },
      { type: "date", key: "date_to", label: "Hasta", min: params.date_from || undefined },
      {
        type: "select",
        key: "status",
        label: "Estado",
        allLabel: "todos",
        options: SETTLEMENT_STATUS_OPTIONS,
        width: 160,
      },
    ];
    if (canBanks) {
      defs.push({
        type: "select",
        key: "bank_id",
        label: "Banco",
        allLabel: "todos",
        options: (banks.data ?? []).map((b) => ({ value: b.id, label: bankLabel(b) })),
        loading: banks.isPending,
        width: 160,
      });
    }
    if (canUsers) {
      defs.push(
        {
          type: "select",
          key: "advisor_id",
          label: "Asesor",
          allLabel: "todos",
          options: (advisors.data ?? []).map((u) => ({ value: u.id, label: u.name || u.email })),
          loading: advisors.isPending,
          width: 180,
        },
        {
          type: "select",
          key: "broker_id",
          label: "Broker",
          allLabel: "todos",
          options: (brokers.data ?? []).map((u) => ({ value: u.id, label: u.name || u.email })),
          loading: brokers.isPending,
          width: 180,
        },
      );
    }
    defs.push({
      type: "select",
      key: "needs_review",
      label: "Revisión",
      allLabel: "todas",
      options: [
        { value: "true", label: "pendiente" },
        { value: "false", label: "sin pendiente" },
      ],
      width: 190,
    });
    return defs;
  }, [params.date_from, params.date_to, canBanks, canUsers, banks, advisors, brokers]);
}

/** Pestaña "Liquidaciones" de `/comisiones`: filtros, listado y el detalle en el panel. */
export function SettlementsTab({
  params,
  openId,
  permissions,
  mobile,
  onChange,
  onOpen,
}: {
  params: SettlementParams;
  openId: string;
  permissions: ReadonlySet<string>;
  mobile: boolean;
  onChange: (patch: Partial<SettlementParams>) => void;
  onOpen: (id: string | null) => void;
}) {
  const list = useSettlements(params);
  const defs = useFilterDefs(params, permissions);
  const errors = filterErrors(list.error, SETTLEMENT_FILTER_KEYS);
  const hasErrors = Object.keys(errors).length > 0;
  const filtered = hasSettlementFilters(params);
  const openRow = list.data?.items.find((s) => s.id === openId);

  let content;
  if (list.isPending) {
    content = <LoadingState label="Cargando las liquidaciones" blocks={[52, 52, 52, 52]} />;
  } else if (list.isError) {
    content = hasErrors ? (
      <p className="text-text-secondary m-0 text-sm">Corrige los filtros marcados.</p>
    ) : (
      <ErrorState
        title="No pudimos cargar las liquidaciones"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (list.data.items.length === 0) {
    content = (
      <EmptyState
        size="sm"
        title={filtered ? "No hay liquidaciones con estos filtros" : "Todavía no hay liquidaciones"}
        description={
          filtered
            ? undefined
            : "Se crean solas cuando una solicitud se desembolsa y el producto tiene un plan vigente."
        }
      />
    );
  } else {
    const busy = list.isFetching && list.isPlaceholderData;
    content = (
      <div className="-mx-5 -mb-5">
        {mobile ? (
          <CardList
            ariaLabel="Liquidaciones"
            rows={list.data.items}
            getRowId={(r) => r.id}
            renderCard={(row) => <SettlementCard row={row} />}
            onOpen={(row) => onOpen(row.id)}
            busy={busy}
          />
        ) : (
          <DataTable
            ariaLabel="Liquidaciones"
            columns={COLUMNS}
            rows={list.data.items}
            getRowId={(r) => r.id}
            onOpen={(row) => onOpen(row.id)}
            busy={busy}
            stickyColumn="application"
            alignRight={["total"]}
            minWidth={980}
          />
        )}
        <ListPagination
          page={params.page}
          pageSize={params.page_size}
          total={list.data.total}
          itemsLabel="Liquidaciones"
          onPage={(page) => onChange({ page })}
          onPageSize={(page_size) => onChange({ page_size })}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <>
      <CommissionFilters
        defs={defs}
        values={{ ...params } as unknown as Record<string, string>}
        errors={errors}
        onChange={(patch) => onChange(patch)}
        onClear={() => onChange(EMPTY_SETTLEMENT_FILTERS)}
        active={filtered}
        mobile={mobile}
      />
      <Card title="Liquidaciones" className="min-w-0">
        {content}
      </Card>
      <SettlementPanel
        id={openId || null}
        initial={openRow}
        canManage={permissions.has("commissions.manage")}
        onClose={() => onOpen(null)}
      />
    </>
  );
}
