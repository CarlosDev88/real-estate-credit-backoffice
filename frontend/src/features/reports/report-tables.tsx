"use client";

import { useMemo } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { Money } from "@/components/ui/money";
import { StatusBadge } from "@/components/ui/status-badge";
import type { FunnelStage } from "@/features/dashboard/queries";
import type { ReportApplication, ReportFunnel } from "@/features/reports/queries";
import { formatDate, formatDateTime, formatInteger, formatRatio } from "@/lib/format";

const count = (n: number) => formatInteger(n) || "0";

// ---------- embudo agrupado ----------

interface FunnelRow {
  key: string;
  label: string;
  total: boolean;
  stages: FunnelStage[];
}

/** Número de la etapa y, debajo, su conversión contra "Creadas". */
function StageCell({ stage }: { stage: FunnelStage | undefined }) {
  if (!stage) return <span className="text-text-tertiary">—</span>;
  return (
    <span className="grid justify-items-end leading-tight">
      <span className="font-medium tabular-nums">{count(stage.count)}</span>
      <span className="text-text-tertiary text-xs tabular-nums">
        {formatRatio(stage.conversion) ?? "—"}
      </span>
    </span>
  );
}

/**
 * Embudo agrupado: una fila por grupo (y la del total arriba) y una columna por etapa con
 * el número y la conversión. Las etapas y sus nombres salen de la respuesta.
 */
export function GroupedFunnelTable({
  funnel,
  groupLabel,
}: {
  funnel: ReportFunnel;
  /** Encabezado de la primera columna ("Asesor", "Banco", "Finalidad"). */
  groupLabel: string;
}) {
  const stages = funnel.stages;
  const columns = useMemo(() => {
    const col = dataColumns<FunnelRow>();
    return col.columns([
      col.accessor((r) => r.label, {
        id: "group",
        header: groupLabel,
        cell: ({ row }) => (
          <span className={row.original.total ? "font-semibold" : "font-medium"}>
            {row.original.label}
          </span>
        ),
      }),
      ...stages.map((stage) =>
        col.display({
          id: stage.code,
          header: stage.label,
          cell: ({ row }) => (
            <StageCell stage={row.original.stages.find((s) => s.code === stage.code)} />
          ),
        }),
      ),
    ]);
  }, [stages, groupLabel]);

  const rows: FunnelRow[] = [
    { key: "__total", label: "Total", total: true, stages },
    ...funnel.groups.map((g) => ({
      key: g.key ?? "__none",
      label: g.label,
      total: false,
      stages: g.stages,
    })),
  ];

  return (
    <DataTable
      ariaLabel={`Embudo por ${groupLabel.toLowerCase()}`}
      columns={columns}
      rows={rows}
      getRowId={(r) => r.key}
      stickyColumn="group"
      alignRight={stages.map((s) => s.code)}
      minWidth={860}
    />
  );
}

// ---------- solicitudes ----------

const appCol = dataColumns<ReportApplication>();
const APPLICATION_COLUMNS = appCol.columns([
  appCol.accessor((r) => r.code, {
    id: "code",
    header: "Código",
    cell: ({ row }) => <span className="font-mono text-sm font-medium">{row.original.code}</span>,
  }),
  appCol.accessor((r) => r.created_at, {
    id: "created_at",
    header: "Creada",
    cell: ({ row }) => formatDate(row.original.created_at),
  }),
  appCol.display({
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
  appCol.accessor((r) => r.client_name, {
    id: "client_name",
    header: "Titular",
    cell: ({ row }) => (
      <span className="block">
        <span className="block font-medium">{row.original.client_name}</span>
        {/* Viene enmascarado de la API: se muestra tal cual. */}
        <span className="text-text-tertiary font-mono text-xs">
          {row.original.client_document_masked}
        </span>
      </span>
    ),
  }),
  appCol.accessor((r) => r.purpose, { id: "purpose", header: "Finalidad" }),
  appCol.accessor((r) => r.advisor_name, { id: "advisor_name", header: "Asesor" }),
  appCol.accessor((r) => r.bank_name, {
    id: "bank_name",
    header: "Banco",
    cell: ({ row }) => row.original.bank_name ?? <span className="text-text-tertiary">—</span>,
  }),
  appCol.accessor((r) => r.project_name, {
    id: "project_name",
    header: "Proyecto",
    cell: ({ row }) => row.original.project_name ?? <span className="text-text-tertiary">—</span>,
  }),
  appCol.accessor((r) => r.requested_amount, {
    id: "requested_amount",
    header: "Monto solicitado",
    cell: ({ row }) => (
      <Money
        value={
          row.original.requested_amount === null ? null : Number(row.original.requested_amount)
        }
      />
    ),
  }),
  appCol.accessor((r) => r.last_status_change_at, {
    id: "last_status_change_at",
    header: "Último cambio",
    cell: ({ row }) => (
      <span className="text-text-secondary text-sm">
        {formatDateTime(row.original.last_status_change_at)}
      </span>
    ),
  }),
  appCol.accessor((r) => r.filings_count, {
    id: "filings_count",
    header: "Radicaciones",
    cell: ({ row }) => <span className="tabular-nums">{count(row.original.filings_count)}</span>,
  }),
]);

function ApplicationCard({ row }: { row: ReportApplication }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-medium">{row.code}</span>
        <span className="text-text-tertiary ml-auto text-xs">{formatDate(row.created_at)}</span>
      </div>
      <div>
        <StatusBadge kind="application" code={row.status} label={row.status_label} />
      </div>
      <DataList layout="inline">
        <Datum label="Titular">
          {row.client_name}{" "}
          <span className="text-text-tertiary font-mono text-xs">{row.client_document_masked}</span>
        </Datum>
        <Datum label="Finalidad">{row.purpose}</Datum>
        <Datum label="Asesor">{row.advisor_name}</Datum>
        <Datum label="Banco">{row.bank_name}</Datum>
        <Datum label="Proyecto">{row.project_name}</Datum>
        <Datum label="Monto solicitado">
          {row.requested_amount === null ? null : <Money value={Number(row.requested_amount)} />}
        </Datum>
        <Datum label="Radicaciones">{count(row.filings_count)}</Datum>
      </DataList>
    </>
  );
}

export function ApplicationsReport({
  rows,
  busy,
  mobile,
}: {
  rows: ReportApplication[];
  busy: boolean;
  mobile: boolean;
}) {
  // El código no es único entre páginas si cambian los datos; con la fecha alcanza.
  const id = (r: ReportApplication) => `${r.code}-${r.created_at}`;
  if (mobile) {
    return (
      <CardList
        ariaLabel="Solicitudes del reporte"
        rows={rows}
        getRowId={id}
        renderCard={(row) => <ApplicationCard row={row} />}
        busy={busy}
      />
    );
  }
  return (
    <DataTable
      ariaLabel="Solicitudes del reporte"
      columns={APPLICATION_COLUMNS}
      rows={rows}
      getRowId={id}
      stickyColumn="code"
      alignRight={["requested_amount", "filings_count"]}
      busy={busy}
      minWidth={1240}
    />
  );
}
