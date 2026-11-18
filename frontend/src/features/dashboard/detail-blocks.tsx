"use client";

import type { UseQueryResult } from "@tanstack/react-query";

import { Card, DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { BlockState, EmptyNote } from "@/features/dashboard/block-state";
import { FunnelTable } from "@/features/dashboard/funnel-table";
import {
  isForbidden,
  type AdvisorWorkload,
  type BankResult,
  type DashboardBankResults,
  type DashboardFunnel,
  type DashboardWorkload,
} from "@/features/dashboard/queries";
import { formatDecimal, formatInteger } from "@/lib/format";

const count = (n: number) => formatInteger(n) || "0";
const DASH = <span className="text-text-tertiary">—</span>;

// ---------- embudo ----------

export function FunnelBlock({ query }: { query: UseQueryResult<DashboardFunnel> }) {
  return (
    <Card title="Embudo">
      <p className="text-text-tertiary m-0 mb-4 text-xs">
        Solicitudes creadas en el periodo y hasta qué etapa llegaron.
      </p>
      <BlockState
        query={query}
        errorTitle="No pudimos cargar el embudo."
        loadingLabel="Cargando el embudo"
      >
        {(data) =>
          (data.stages[0]?.count ?? 0) === 0 ? (
            <EmptyNote>No se crearon solicitudes en el periodo.</EmptyNote>
          ) : (
            <FunnelTable stages={data.stages} caption="Embudo de solicitudes del periodo" />
          )
        }
      </BlockState>
    </Card>
  );
}

// ---------- carga por asesor ----------

const workloadCol = dataColumns<AdvisorWorkload>();
const WORKLOAD_COLUMNS = workloadCol.columns([
  workloadCol.accessor((r) => r.advisor_name, {
    id: "advisor_name",
    header: "Asesor",
    cell: ({ row }) => <span className="font-medium">{row.original.advisor_name}</span>,
  }),
  workloadCol.accessor((r) => r.open_applications, {
    id: "open_applications",
    header: "Solicitudes abiertas",
    cell: ({ row }) => (
      <span className="tabular-nums">{count(row.original.open_applications)}</span>
    ),
  }),
  workloadCol.accessor((r) => r.waiting_buyer, {
    id: "waiting_buyer",
    header: "Esperando al comprador",
    cell: ({ row }) => <span className="tabular-nums">{count(row.original.waiting_buyer)}</span>,
  }),
  workloadCol.accessor((r) => r.ready_to_file, {
    id: "ready_to_file",
    header: "Listas para radicar",
    cell: ({ row }) => <span className="tabular-nums">{count(row.original.ready_to_file)}</span>,
  }),
  workloadCol.accessor((r) => r.overdue_tasks, {
    id: "overdue_tasks",
    header: "Tareas vencidas",
    cell: ({ row }) => <span className="tabular-nums">{count(row.original.overdue_tasks)}</span>,
  }),
  workloadCol.accessor((r) => r.due_today_tasks, {
    id: "due_today_tasks",
    header: "Tareas para hoy",
    cell: ({ row }) => <span className="tabular-nums">{count(row.original.due_today_tasks)}</span>,
  }),
]);
const WORKLOAD_RIGHT = [
  "open_applications",
  "waiting_buyer",
  "ready_to_file",
  "overdue_tasks",
  "due_today_tasks",
] as const;

function WorkloadCard({ row }: { row: AdvisorWorkload }) {
  return (
    <>
      <b className="font-medium">{row.advisor_name}</b>
      <DataList layout="inline">
        <Datum label="Solicitudes abiertas">{count(row.open_applications)}</Datum>
        <Datum label="Esperando al comprador">{count(row.waiting_buyer)}</Datum>
        <Datum label="Listas para radicar">{count(row.ready_to_file)}</Datum>
        <Datum label="Tareas vencidas">{count(row.overdue_tasks)}</Datum>
        <Datum label="Tareas para hoy">{count(row.due_today_tasks)}</Datum>
      </DataList>
    </>
  );
}

/** Carga por asesor. Sin permiso (el broker recibe `403`), el bloque no aparece. */
export function WorkloadBlock({
  query,
  mobile,
}: {
  query: UseQueryResult<DashboardWorkload>;
  mobile: boolean;
}) {
  if (isForbidden(query.error)) return null;
  return (
    <Card title="Carga por asesor">
      <p className="text-text-tertiary m-0 mb-4 text-xs">
        Hoy, sin el filtro de fechas. Las tareas son las pendientes de cada asesor.
      </p>
      <BlockState
        query={query}
        errorTitle="No pudimos cargar la carga por asesor."
        loadingLabel="Cargando la carga por asesor"
      >
        {(data) =>
          data.advisors.length === 0 ? (
            <EmptyNote>No hay asesores con solicitudes abiertas.</EmptyNote>
          ) : mobile ? (
            <div className="-mx-5">
              <CardList
                ariaLabel="Carga por asesor"
                rows={data.advisors}
                getRowId={(r) => r.advisor_id}
                renderCard={(row) => <WorkloadCard row={row} />}
              />
            </div>
          ) : (
            <div className="-mx-5 -mb-5">
              <DataTable
                ariaLabel="Carga por asesor"
                columns={WORKLOAD_COLUMNS}
                rows={data.advisors}
                getRowId={(r) => r.advisor_id}
                alignRight={WORKLOAD_RIGHT}
                stickyColumn="advisor_name"
                minWidth={760}
              />
            </div>
          )
        }
      </BlockState>
    </Card>
  );
}

// ---------- resultados por banco ----------

const bankCol = dataColumns<BankResult>();
const avgDays = (value: string | null) => formatDecimal(value) ?? DASH;
const BANK_COLUMNS = bankCol.columns([
  bankCol.accessor((r) => r.bank_name, {
    id: "bank_name",
    header: "Banco",
    cell: ({ row }) => <span className="font-medium">{row.original.bank_name}</span>,
  }),
  ...(
    [
      ["filings", "Radicaciones"],
      ["returned", "Devueltas"],
      ["approved", "Aprobadas"],
      ["rejected", "Rechazadas"],
      ["disbursed", "Desembolsadas"],
    ] as const
  ).map(([key, header]) =>
    bankCol.accessor((r) => r[key], {
      id: key,
      header,
      cell: ({ row }) => <span className="tabular-nums">{count(row.original[key])}</span>,
    }),
  ),
  bankCol.accessor((r) => r.avg_days_to_response, {
    id: "avg_days_to_response",
    header: "Días promedio a la respuesta",
    cell: ({ row }) => (
      <span className="tabular-nums">{avgDays(row.original.avg_days_to_response)}</span>
    ),
  }),
]);
const BANK_RIGHT = [
  "filings",
  "returned",
  "approved",
  "rejected",
  "disbursed",
  "avg_days_to_response",
] as const;

function BankCard({ row }: { row: BankResult }) {
  return (
    <>
      <b className="font-medium">{row.bank_name}</b>
      <DataList layout="inline">
        <Datum label="Radicaciones">{count(row.filings)}</Datum>
        <Datum label="Devueltas">{count(row.returned)}</Datum>
        <Datum label="Aprobadas">{count(row.approved)}</Datum>
        <Datum label="Rechazadas">{count(row.rejected)}</Datum>
        <Datum label="Desembolsadas">{count(row.disbursed)}</Datum>
        <Datum label="Días promedio a la respuesta">{avgDays(row.avg_days_to_response)}</Datum>
      </DataList>
    </>
  );
}

/** Resultados por banco. Sin permiso (el broker recibe `403`), el bloque no aparece. */
export function BankResultsBlock({
  query,
  mobile,
}: {
  query: UseQueryResult<DashboardBankResults>;
  mobile: boolean;
}) {
  if (isForbidden(query.error)) return null;
  return (
    <Card title="Resultados por banco">
      <p className="text-text-tertiary m-0 mb-4 text-xs">
        Radicaciones del periodo y las respuestas que recibieron.
      </p>
      <BlockState
        query={query}
        errorTitle="No pudimos cargar los resultados por banco."
        loadingLabel="Cargando los resultados por banco"
      >
        {(data) =>
          data.banks.length === 0 ? (
            <EmptyNote>No hay radicaciones en el periodo.</EmptyNote>
          ) : mobile ? (
            <div className="-mx-5">
              <CardList
                ariaLabel="Resultados por banco"
                rows={data.banks}
                getRowId={(r) => r.bank_id}
                renderCard={(row) => <BankCard row={row} />}
              />
            </div>
          ) : (
            <div className="-mx-5 -mb-5">
              <DataTable
                ariaLabel="Resultados por banco"
                columns={BANK_COLUMNS}
                rows={data.banks}
                getRowId={(r) => r.bank_id}
                alignRight={BANK_RIGHT}
                stickyColumn="bank_name"
                minWidth={820}
              />
            </div>
          )
        }
      </BlockState>
    </Card>
  );
}
