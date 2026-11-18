"use client";

import { Button } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PlusIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { bankLabel, useActiveBanks, useAdvisors, useCatalog } from "@/features/dashboard/queries";
import { FilterToolbar, type ToolbarSelect } from "@/features/workday/filter-toolbar";
import {
  tasksQuery,
  usePendingTasksCount,
  useTasks,
  useWorkdayApplications,
  useWorkdaySummary,
  WORKDAY_STAGES,
  type Task,
} from "@/features/workday/queries";
import {
  CancelTaskModal,
  CompleteTaskModal,
  TaskFormModal,
  type Assignee,
  type TaskTarget,
} from "@/features/workday/task-modals";
import { TaskList, type TaskActions } from "@/features/workday/tasks-panel";
import { AttentionSegments, TrayList } from "@/features/workday/tray";
import {
  ALL,
  DEFAULT_TASK_STATUS,
  trayOf,
  tasksOf,
  useMyDayParams,
  type MyDayParams,
  type Tab,
} from "@/features/workday/workday-params";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const MOBILE_QUERY = "(max-width: 860px)";

const TRAY_CLEARED: Partial<MyDayParams> = {
  search: "",
  stage: "",
  bank_id: "",
  purpose: "",
  attention: "",
  advisor_id: "",
};
const TASKS_CLEARED: Partial<MyDayParams> = {
  due: "",
  task_status: DEFAULT_TASK_STATUS,
  priority: "",
  assigned_to_id: "",
};

/** Opciones de orden de la bandeja (`ordering_fields` de la API). */
const ORDER_OPTIONS = [
  { value: "-days_in_stage", label: "más días en la etapa" },
  { value: "days_in_stage", label: "menos días en la etapa" },
  { value: "-updated_at", label: "actualizadas hace poco" },
  { value: "code", label: "código" },
];

/**
 * Filtros de las tareas. El contrato fija estos valores (`due` y `status` de `GET /tasks`)
 * y no trae un catálogo con sus textos: los nombres de las opciones van aquí; el estado de
 * cada tarea se muestra con `status_label`.
 */
const DUE_OPTIONS = [
  { value: "overdue", label: "vencidas" },
  { value: "today", label: "hoy" },
  { value: "upcoming", label: "próximas" },
];
const STATUS_OPTIONS = [
  { value: "PENDING", label: "pendientes" },
  { value: "COMPLETED", label: "completadas" },
  { value: "CANCELLED", label: "canceladas" },
  { value: ALL, label: "todas" },
];

/** "Mi día" (`/mi-dia`, vista 3): la bandeja de atención y las tareas del usuario. */
export function MyDayScreen() {
  const me = useMe();
  const meId = me.data?.id ?? "";
  const permissions = useMemo(() => me.data?.permissions ?? [], [me.data]);
  const can = (p: string) => permissions.includes(p);
  const isAdmin = can("users.read");
  const canTasks = can("tasks.read");

  const { params, update } = useMyDayParams();
  const tab: Tab = canTasks ? params.tab : "bandeja";
  const mobile = useMediaQuery(MOBILE_QUERY);

  const tray = trayOf(params);
  const summary = useWorkdaySummary(tray);
  const applications = useWorkdayApplications(tray);
  const taskParams = tasksOf(params);
  const tasks = useTasks(tasksQuery(taskParams, meId), canTasks && !!meId && tab === "tareas");
  const pending = usePendingTasksCount(canTasks ? meId : undefined);

  // Opciones de los filtros (catálogos, bancos y asesores).
  const statuses = useCatalog("application_status");
  const purposes = useCatalog("loan_purpose");
  const priorities = useCatalog("task_priority");
  const banks = useActiveBanks(can("banks.read"));
  const advisors = useAdvisors(isAdmin);

  // Una página que ya no existe (la API responde 404) vuelve a la primera.
  const trayGone =
    isApiError(applications.error) && applications.error.status === 404 && params.page > 1;
  const tasksGone = isApiError(tasks.error) && tasks.error.status === 404 && params.task_page > 1;
  useEffect(() => {
    if (trayGone) update({ page: 1 });
    else if (tasksGone) update({ task_page: 1 });
  }, [trayGone, tasksGone, update]);

  // Modales de las tareas.
  const [creating, setCreating] = useState<{ target: TaskTarget | null } | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [completing, setCompleting] = useState<Task | null>(null);
  const [cancelling, setCancelling] = useState<Task | null>(null);

  const assignees: Assignee[] = useMemo(() => {
    if (!isAdmin || !me.data) return [];
    const self = { id: me.data.id, name: `${me.data.name || me.data.email} (yo)` };
    return [
      self,
      ...(advisors.data ?? [])
        .filter((u) => u.id !== self.id)
        .map((u) => ({ id: u.id, name: u.name || u.email })),
    ];
  }, [isAdmin, me.data, advisors.data]);

  const traySelects: ToolbarSelect[] = [
    {
      key: "stage",
      label: "Etapa",
      allLabel: "todas",
      value: params.stage,
      options: statuses.items
        .filter((s) => (WORKDAY_STAGES as readonly string[]).includes(s.code))
        .map((s) => ({ value: s.code, label: s.label })),
      loading: statuses.isPending,
      width: 210,
    },
    ...(can("banks.read")
      ? [
          {
            key: "bank_id",
            label: "Banco",
            allLabel: "todos",
            value: params.bank_id,
            options: (banks.data ?? []).map((b) => ({ value: b.id, label: bankLabel(b) })),
            loading: banks.isPending,
            width: 150,
          },
        ]
      : []),
    {
      key: "purpose",
      label: "Finalidad",
      allLabel: "todas",
      value: params.purpose,
      options: purposes.items.map((p) => ({ value: p.code, label: p.label })),
      loading: purposes.isPending,
      width: 170,
    },
    ...(isAdmin
      ? [
          {
            key: "advisor_id",
            label: "Asesor",
            allLabel: "todos",
            value: params.advisor_id,
            options: (advisors.data ?? []).map((u) => ({ value: u.id, label: u.name || u.email })),
            loading: advisors.isPending,
            width: 170,
          },
        ]
      : []),
    {
      key: "ordering",
      label: "Orden",
      allLabel: "prioridad de atención",
      value: params.ordering,
      options: ORDER_OPTIONS,
      width: 250,
    },
  ];

  const taskSelects: ToolbarSelect[] = [
    {
      key: "due",
      label: "Vencimiento",
      allLabel: "todas",
      value: params.due,
      options: DUE_OPTIONS,
      width: 190,
    },
    {
      key: "task_status",
      label: "Estado",
      allLabel: "pendientes",
      value: params.task_status,
      defaultValue: DEFAULT_TASK_STATUS,
      options: STATUS_OPTIONS,
      width: 190,
    },
    {
      key: "priority",
      label: "Prioridad",
      allLabel: "todas",
      value: params.priority,
      options: priorities.items.map((p) => ({ value: p.code, label: p.label })),
      loading: priorities.isPending,
      width: 160,
    },
    ...(isAdmin
      ? [
          {
            key: "assigned_to_id",
            label: "Responsable",
            allLabel: "yo",
            value: params.assigned_to_id,
            options: [
              ...(advisors.data ?? [])
                .filter((u) => u.id !== meId)
                .map((u) => ({ value: u.id, label: u.name || u.email })),
              { value: ALL, label: "todos" },
            ],
            loading: advisors.isPending,
            width: 210,
          },
        ]
      : []),
  ];

  const onSearch = useCallback((search: string) => update({ search }), [update]);

  const trayFiltered = Object.keys(TRAY_CLEARED).some((k) => params[k as keyof MyDayParams] !== "");
  const tasksFiltered =
    params.due !== "" ||
    params.priority !== "" ||
    params.assigned_to_id !== "" ||
    params.task_status !== DEFAULT_TASK_STATUS;

  const canUpdate = can("tasks.update");
  const canComplete = can("tasks.complete");
  const canCancel = can("tasks.cancel");
  const actions: TaskActions = useMemo(
    () => ({
      canUpdate,
      canComplete,
      canCancel,
      onEdit: setEditing,
      onComplete: setCompleting,
      onCancel: setCancelling,
    }),
    [canUpdate, canComplete, canCancel],
  );
  const canCreate = can("tasks.create");
  const newTaskFor = useCallback((row: TaskTarget) => setCreating({ target: row }), []);

  const sortField = params.ordering.replace(/^-/, "");
  const sorting = params.ordering
    ? { field: sortField, desc: params.ordering.startsWith("-") }
    : undefined;

  const tabs = [
    { key: "bandeja", label: "Bandeja", count: summary.data?.total ?? null },
    ...(canTasks ? [{ key: "tareas", label: "Mis tareas", count: pending.data ?? null }] : []),
  ];

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Mi día"
        description="Las solicitudes que piden tu atención hoy y tus tareas."
        actions={
          canCreate ? (
            <Button
              type="primary"
              icon={<PlusIcon />}
              onClick={() => setCreating({ target: null })}
            >
              Nueva tarea
            </Button>
          ) : undefined
        }
      />

      <ScrollTabs
        ariaLabel="Secciones de Mi día"
        items={tabs}
        value={tab}
        onChange={(key) => update({ tab: key as Tab })}
      />

      {tab === "bandeja" ? (
        <>
          <AttentionSegments
            query={summary}
            value={params.attention}
            onChange={(attention) => update({ attention })}
          />
          <section
            aria-label="Bandeja"
            className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
          >
            <FilterToolbar
              search={{
                value: params.search,
                onChange: onSearch,
                placeholder: "Código, nombre o cédula",
                ariaLabel: "Buscar en la bandeja por código, nombre o cédula",
              }}
              selects={traySelects}
              onSelect={(key, value) => update({ [key]: value })}
              onClear={() => update(TRAY_CLEARED)}
              mobile={mobile}
            />
            <TrayList
              query={applications}
              page={params.page}
              pageSize={params.page_size}
              sorting={sorting}
              onSort={(s) => update({ ordering: `${s.desc ? "-" : ""}${s.field}` })}
              onPage={(page) => update({ page })}
              onPageSize={(page_size) => update({ page_size })}
              filtered={trayFiltered}
              onClear={() => update(TRAY_CLEARED)}
              onNewTask={canCreate ? newTaskFor : null}
              mobile={mobile}
            />
          </section>
        </>
      ) : (
        <section
          aria-label="Mis tareas"
          className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
        >
          <FilterToolbar
            selects={taskSelects}
            onSelect={(key, value) => update({ [key]: value })}
            onClear={() => update(TASKS_CLEARED)}
            mobile={mobile}
          />
          <TaskList
            query={tasks}
            page={params.task_page}
            pageSize={params.task_page_size}
            onPage={(task_page) => update({ task_page })}
            onPageSize={(task_page_size) => update({ task_page_size })}
            actions={actions}
            showAssignee={isAdmin && params.assigned_to_id !== ""}
            filtered={tasksFiltered}
            onClear={() => update(TASKS_CLEARED)}
            mobile={mobile}
          />
        </section>
      )}

      <TaskFormModal
        open={!!creating || !!editing}
        onClose={() => {
          setCreating(null);
          setEditing(null);
        }}
        task={editing}
        target={creating?.target ?? null}
        assignees={assignees}
        meId={meId}
      />
      <CompleteTaskModal task={completing} onClose={() => setCompleting(null)} />
      <CancelTaskModal task={cancelling} onClose={() => setCancelling(null)} />
    </div>
  );
}
