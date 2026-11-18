"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "antd";
import Link from "next/link";
import { useMemo } from "react";

import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { StatusBadge, TONE_CLASS } from "@/components/ui/status-badge";
import { PlusIcon } from "@/components/ui/icons";
import type { WorkdayApplication, WorkdaySummary } from "@/features/workday/queries";
import { PAGE_SIZES, SORTABLE_FIELDS } from "@/features/workday/workday-params";
import { formatInteger } from "@/lib/format";

export const applicationHref = (id: string) => `/solicitudes/${id}`;

const count = (n: number) => formatInteger(n) || "0";

// ---------- segmentos de atención ----------

/**
 * Segmentos de `GET /workday/summary` como filtros: cada uno es un botón que se marca
 * (`aria-pressed`). Los segmentos no son excluyentes; "Todas" quita el filtro.
 */
export function AttentionSegments({
  query,
  value,
  onChange,
}: {
  query: UseQueryResult<WorkdaySummary>;
  value: string;
  onChange: (code: string) => void;
}) {
  if (query.isPending) return <LoadingState label="Cargando el resumen" blocks={[64]} />;
  if (query.isError) {
    return (
      <ErrorState
        variant="inline"
        title="No pudimos cargar el resumen de atención."
        onRetry={() => void query.refetch()}
        retrying={query.isRefetching}
      />
    );
  }
  const items = [
    { code: "", label: "Todas", count: query.data.total },
    ...query.data.segments.map((s) => ({ code: s.code, label: s.label, count: s.count })),
  ];
  return (
    <div role="group" aria-label="Segmentos de atención">
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 min-[600px]:grid-cols-4 min-[1100px]:grid-cols-8">
        {items.map((item) => {
          const pressed = value === item.code;
          return (
            <li key={item.code || "all"} className="grid">
              <button
                type="button"
                aria-pressed={pressed}
                onClick={() => onChange(pressed ? "" : item.code)}
                className={`grid cursor-pointer content-start gap-0.5 rounded-lg border px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring ${
                  pressed
                    ? "border-brand-primary bg-brand-subtle text-text-primary shadow-[inset_0_0_0_1px_var(--um-brand-primary)]"
                    : "bg-bg-surface border-border-default text-text-primary hover:border-border-strong"
                }`}
              >
                <span className="text-xl leading-tight font-semibold tabular-nums">
                  {count(item.count)}
                </span>
                <span className="text-text-secondary text-xs leading-snug font-medium">
                  {item.label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------- celdas ----------

function CodeLink({ row }: { row: WorkdayApplication }) {
  return (
    <Link
      href={applicationHref(row.id)}
      className="text-text-link font-mono text-sm font-medium no-underline hover:underline"
    >
      {row.code}
    </Link>
  );
}

/**
 * Señales de atención (texto de la API) y tareas pendientes. Los segmentos no tienen tono
 * en `toneFor`: van en neutro, con su texto.
 */
function AttentionCell({ row }: { row: WorkdayApplication }) {
  if (row.attention.length === 0 && row.pending_tasks_count === 0) {
    return <span className="text-text-tertiary">—</span>;
  }
  return (
    <ul className="m-0 flex list-none flex-wrap gap-1 p-0">
      {row.attention.map((a) => (
        <li
          key={a.code}
          className={`inline-flex min-h-[22px] items-center rounded-full border px-2 py-px text-xs font-medium ${TONE_CLASS.neutral}`}
        >
          {a.label}
        </li>
      ))}
      {row.pending_tasks_count > 0 && (
        <li className="text-text-secondary inline-flex h-[22px] items-center text-xs whitespace-nowrap">
          {row.pending_tasks_count === 1
            ? "1 tarea pendiente"
            : `${row.pending_tasks_count} tareas pendientes`}
        </li>
      )}
    </ul>
  );
}

function daysLabel(days: number): string {
  return days === 1 ? "1 día" : `${count(days)} días`;
}

// ---------- tabla y tarjetas ----------

function trayColumns(onNewTask: ((row: WorkdayApplication) => void) | null) {
  const col = dataColumns<WorkdayApplication>();
  return col.columns([
    col.accessor((r) => r.code, {
      id: "code",
      header: "Código",
      cell: ({ row }) => <CodeLink row={row.original} />,
    }),
    col.accessor((r) => r.client_display_name, {
      id: "client_display_name",
      header: "Cliente",
      cell: ({ row }) => <span className="font-medium">{row.original.client_display_name}</span>,
    }),
    col.display({
      id: "status",
      header: "Etapa y siguiente acción",
      cell: ({ row }) => (
        <span className="grid max-w-[300px] justify-items-start gap-1 py-2 whitespace-normal">
          <StatusBadge
            kind="application"
            code={row.original.status}
            label={row.original.status_label}
          />
          <span className="text-text-secondary text-xs">{row.original.next_action_label}</span>
        </span>
      ),
    }),
    col.accessor((r) => r.days_in_stage, {
      id: "days_in_stage",
      header: "Días en la etapa",
      cell: ({ row }) => (
        <span className="tabular-nums">{daysLabel(row.original.days_in_stage)}</span>
      ),
    }),
    col.display({
      id: "attention",
      header: "Atención",
      cell: ({ row }) => (
        <div className="max-w-[240px] whitespace-normal">
          <AttentionCell row={row.original} />
        </div>
      ),
    }),
    ...(onNewTask
      ? [
          col.display({
            id: "actions",
            header: () => <span className="sr-only">Acciones</span>,
            cell: ({ row }) => (
              <Button
                size="small"
                icon={<PlusIcon />}
                aria-label={`Nueva tarea para ${row.original.code}`}
                title="Nueva tarea"
                onClick={() => onNewTask(row.original)}
              />
            ),
          }),
        ]
      : []),
  ]);
}

function TrayCard({
  row,
  onNewTask,
}: {
  row: WorkdayApplication;
  onNewTask: ((row: WorkdayApplication) => void) | null;
}) {
  return (
    <>
      <div className="flex items-center gap-2">
        <CodeLink row={row} />
        <span className="text-text-tertiary ml-auto text-xs">{daysLabel(row.days_in_stage)}</span>
      </div>
      <b className="font-medium">{row.client_display_name}</b>
      <div>
        <StatusBadge kind="application" code={row.status} label={row.status_label} />
      </div>
      <p className="text-text-secondary m-0 text-sm">{row.next_action_label}</p>
      {(row.attention.length > 0 || row.pending_tasks_count > 0) && <AttentionCell row={row} />}
      {onNewTask && (
        <div>
          <Button size="small" icon={<PlusIcon />} onClick={() => onNewTask(row)}>
            Tarea<span className="sr-only"> para {row.code}</span>
          </Button>
        </div>
      )}
    </>
  );
}

function TraySkeleton() {
  return (
    <div className="p-3">
      <LoadingState label="Cargando la bandeja" blocks={[52, 52, 52, 52]} />
    </div>
  );
}

interface TrayListProps {
  query: UseQueryResult<{ items: WorkdayApplication[]; total: number }>;
  page: number;
  pageSize: number;
  sorting: TableSort | undefined;
  onSort: (sort: TableSort) => void;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  filtered: boolean;
  onClear: () => void;
  /** Sin permiso para crear tareas, no hay botón por fila. */
  onNewTask: ((row: WorkdayApplication) => void) | null;
  mobile: boolean;
}

/** Bandeja: tabla en escritorio, tarjetas en móvil, con su paginación. */
export function TrayList({
  query,
  page,
  pageSize,
  sorting,
  onSort,
  onPage,
  onPageSize,
  filtered,
  onClear,
  onNewTask,
  mobile,
}: TrayListProps) {
  // Columnas estables: si cambian en cada render, las celdas se vuelven a montar.
  const columns = useMemo(() => trayColumns(onNewTask), [onNewTask]);
  if (query.isPending) return <TraySkeleton />;
  if (query.isError) {
    return (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar la bandeja"
          message={query.error.message}
          onRetry={() => void query.refetch()}
          retrying={query.isRefetching}
        />
      </div>
    );
  }
  const rows = query.data.items;
  if (rows.length === 0) {
    return (
      <EmptyState
        title={filtered ? "No hay solicitudes con estos filtros" : "No tienes solicitudes abiertas"}
        description={filtered ? "Prueba con otro segmento o limpia los filtros." : undefined}
        action={
          filtered ? (
            <Button size="small" onClick={onClear}>
              Limpiar filtros
            </Button>
          ) : undefined
        }
      />
    );
  }
  const busy = query.isFetching && query.isPlaceholderData;
  return (
    <>
      {mobile ? (
        <CardList
          ariaLabel="Bandeja de solicitudes"
          rows={rows}
          getRowId={(r) => r.id}
          renderCard={(row) => <TrayCard row={row} onNewTask={onNewTask} />}
          busy={busy}
        />
      ) : (
        <DataTable
          ariaLabel="Bandeja de solicitudes"
          columns={columns}
          rows={rows}
          getRowId={(r) => r.id}
          sorting={sorting}
          sortableFields={SORTABLE_FIELDS}
          onSort={onSort}
          stickyColumn="code"
          busy={busy}
          minWidth={900}
        />
      )}
      <ListPagination
        page={page}
        pageSize={pageSize}
        total={query.data.total}
        itemsLabel="Solicitudes"
        onPage={onPage}
        onPageSize={onPageSize}
        compact={mobile}
        pageSizes={PAGE_SIZES}
      />
    </>
  );
}
