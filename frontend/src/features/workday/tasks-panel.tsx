"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "antd";
import Link from "next/link";
import { useMemo } from "react";

import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { TONE_CLASS } from "@/components/ui/status-badge";
import type { Task } from "@/features/workday/queries";
import { applicationHref } from "@/features/workday/tray";
import { PAGE_SIZES } from "@/features/workday/workday-params";
import { formatDateTime } from "@/lib/format";

/** Qué puede hacer el usuario con las tareas (permisos de `/auth/me`). */
export interface TaskActions {
  canUpdate: boolean;
  canComplete: boolean;
  canCancel: boolean;
  onEdit: (task: Task) => void;
  onComplete: (task: Task) => void;
  onCancel: (task: Task) => void;
}

/** Solicitud o oportunidad de la tarea. La solicitud enlaza al expediente. */
function ParentCell({ task }: { task: Task }) {
  const parent = task.parent;
  const name = (
    <span className="text-text-tertiary block text-xs">{parent.client_display_name}</span>
  );
  if (parent.type === "APPLICATION" && parent.code) {
    return (
      <span className="block">
        <Link
          href={applicationHref(parent.id)}
          className="text-text-link font-mono text-sm font-medium no-underline hover:underline"
        >
          {parent.code}
        </Link>
        {name}
      </span>
    );
  }
  return (
    <span className="block text-sm">
      {parent.type_label}
      {parent.code ? ` ${parent.code}` : ""}
      {name}
    </span>
  );
}

/** Vencimiento; si está vencida, lo dice con texto (no solo con el color). */
function DueCell({ task }: { task: Task }) {
  if (!task.due_at) return <span className="text-text-tertiary">Sin fecha</span>;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span className="tabular-nums">{formatDateTime(task.due_at)}</span>
      {task.is_overdue && (
        <span
          className={`inline-flex h-[22px] items-center rounded-full border px-2 text-xs font-medium ${TONE_CLASS.danger}`}
        >
          Vencida
        </span>
      )}
    </span>
  );
}

function ActionButtons({ task, actions }: { task: Task; actions: TaskActions }) {
  if (task.status !== "PENDING") return null;
  const name = <span className="sr-only"> {task.title}</span>;
  return (
    <span className="flex gap-1">
      {actions.canComplete && (
        <Button size="small" onClick={() => actions.onComplete(task)}>
          Completar{name}
        </Button>
      )}
      {actions.canUpdate && (
        <Button size="small" type="text" onClick={() => actions.onEdit(task)}>
          Editar{name}
        </Button>
      )}
      {actions.canCancel && (
        <Button size="small" type="text" onClick={() => actions.onCancel(task)}>
          Cancelar{name}
        </Button>
      )}
    </span>
  );
}

function taskColumns(actions: TaskActions, showAssignee: boolean) {
  const col = dataColumns<Task>();
  return col.columns([
    col.accessor((t) => t.title, {
      id: "title",
      header: "Tarea",
      cell: ({ row }) => (
        <span className="block max-w-[320px] whitespace-normal">
          <span className="block font-medium">{row.original.title}</span>
          {row.original.description && (
            <span className="text-text-tertiary line-clamp-1 text-xs">
              {row.original.description}
            </span>
          )}
        </span>
      ),
    }),
    col.display({
      id: "parent",
      header: "Vinculada a",
      cell: ({ row }) => <ParentCell task={row.original} />,
    }),
    col.display({
      id: "due_at",
      header: "Vence",
      cell: ({ row }) => <DueCell task={row.original} />,
    }),
    col.display({
      id: "priority",
      header: "Prioridad",
      cell: ({ row }) => row.original.priority.label,
    }),
    col.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => row.original.status_label,
    }),
    ...(showAssignee
      ? [
          col.display({
            id: "assigned_to",
            header: "Responsable",
            cell: ({ row }) => row.original.assigned_to.name,
          }),
        ]
      : []),
    col.display({
      id: "actions",
      header: () => <span className="sr-only">Acciones</span>,
      cell: ({ row }) => <ActionButtons task={row.original} actions={actions} />,
    }),
  ]);
}

function TaskCard({
  task,
  actions,
  showAssignee,
}: {
  task: Task;
  actions: TaskActions;
  showAssignee: boolean;
}) {
  return (
    <>
      <b className="font-medium">{task.title}</b>
      {task.description && (
        <p className="text-text-tertiary m-0 line-clamp-2 text-xs">{task.description}</p>
      )}
      <ParentCell task={task} />
      <div className="text-sm">
        <DueCell task={task} />
      </div>
      <p className="text-text-secondary m-0 text-xs">
        {[task.priority.label, task.status_label, showAssignee ? task.assigned_to.name : null]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <ActionButtons task={task} actions={actions} />
    </>
  );
}

interface TaskListProps {
  query: UseQueryResult<{ items: Task[]; total: number }>;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  actions: TaskActions;
  showAssignee: boolean;
  filtered: boolean;
  onClear: () => void;
  mobile: boolean;
}

export function TaskList({
  query,
  page,
  pageSize,
  onPage,
  onPageSize,
  actions,
  showAssignee,
  filtered,
  onClear,
  mobile,
}: TaskListProps) {
  // Columnas estables: si cambian en cada render, las celdas se vuelven a montar.
  const columns = useMemo(() => taskColumns(actions, showAssignee), [actions, showAssignee]);
  if (query.isPending) {
    return (
      <div className="p-3">
        <LoadingState label="Cargando las tareas" blocks={[52, 52, 52]} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las tareas"
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
        title={filtered ? "No hay tareas con estos filtros" : "No tienes tareas pendientes"}
        description={
          filtered
            ? "Prueba con otro filtro o límpialos."
            : "Crea una con “Nueva tarea” o desde una solicitud de la bandeja."
        }
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
          ariaLabel="Tareas"
          rows={rows}
          getRowId={(t) => t.id}
          renderCard={(task) => (
            <TaskCard task={task} actions={actions} showAssignee={showAssignee} />
          )}
          busy={busy}
        />
      ) : (
        <DataTable
          ariaLabel="Tareas"
          columns={columns}
          rows={rows}
          getRowId={(t) => t.id}
          busy={busy}
          minWidth={960}
        />
      )}
      <ListPagination
        page={page}
        pageSize={pageSize}
        total={query.data.total}
        itemsLabel="Tareas"
        onPage={onPage}
        onPageSize={onPageSize}
        compact={mobile}
        pageSizes={PAGE_SIZES}
      />
    </>
  );
}
