import type { Task, WorkdayApplication, WorkdaySummary } from "@/features/workday/queries";

// Respuestas de ejemplo con la forma del contrato (módulo 12).

export const ADVISOR_ME = {
  id: "u-lucia",
  name: "Lucía Rojas",
  email: "lucia@example.com",
  role: "ADVISOR",
  role_label: "Asesor",
  roles: ["ADVISOR"],
  permissions: [
    "workday.read",
    "applications.read",
    "banks.read",
    "tasks.read",
    "tasks.create",
    "tasks.update",
    "tasks.complete",
    "tasks.cancel",
  ],
  scope: { assigned_applications_only: true, partner_id: null },
};

export const ADMIN_ME = {
  ...ADVISOR_ME,
  id: "u-admin",
  name: "Adriana Mejía",
  email: "admin@example.com",
  role: "ADMIN",
  role_label: "Administrador",
  roles: ["ADMIN"],
  permissions: [...ADVISOR_ME.permissions, "users.read"],
  scope: { assigned_applications_only: false, partner_id: null },
};

export const SUMMARY: WorkdaySummary = {
  total: 35,
  segments: [
    { code: "REVIEW_DOCUMENTS", label: "Documentos por revisar", count: 11 },
    { code: "READY_TO_FILE", label: "Listas para radicar", count: 5 },
    { code: "TASKS_DUE", label: "Con tareas vencidas o de hoy", count: 1 },
  ],
};

export const APPLICATION: WorkdayApplication = {
  id: "app-8",
  code: "SOL-000008",
  client_display_name: "Mariana Cárdenas Ríos",
  bank: { id: "b-1", name: "Bancolombia", short_name: "" },
  bank_product: { id: "p-1", name: "Crédito hipotecario" },
  status: "WAITING_BUYER_DATA",
  status_label: "Esperando datos del comprador",
  next_action: "FOLLOW_UP_BUYER_DATA",
  next_action_label: "Hacer seguimiento a los datos del comprador",
  days_in_stage: 11,
  attention: [{ code: "BUYER_INACTIVE", label: "Comprador sin actividad" }],
  pending_tasks_count: 3,
  updated_at: "2026-11-12T16:38:38-05:00",
};

export const APPLICATION_2: WorkdayApplication = {
  ...APPLICATION,
  id: "app-1",
  code: "SOL-000001",
  client_display_name: "Laura Rincón Castaño",
  status: "DRAFT",
  status_label: "Borrador",
  next_action: "COMPLETE_DRAFT",
  next_action_label: "Completar el borrador",
  days_in_stage: 1,
  attention: [],
  pending_tasks_count: 1,
};

export const trayPage = (items: WorkdayApplication[], total = items.length) => ({
  items,
  page: 1,
  page_size: 20,
  total,
  next: null,
  previous: null,
});

export const TASK: Task = {
  id: "t-1",
  title: "Llamar a Mariana",
  description: "Confirmar ingresos.",
  status: "PENDING",
  status_label: "Pendiente",
  priority: { code: "HIGH", label: "Alta" },
  source: "MANUAL",
  source_label: "Manual",
  assigned_to: { id: "u-lucia", name: "Lucía Rojas" },
  created_by: { id: "u-lucia", name: "Lucía Rojas" },
  parent: {
    type: "APPLICATION",
    type_label: "Solicitud",
    id: "app-8",
    code: "SOL-000008",
    client_display_name: "Mariana Cárdenas Ríos",
  },
  due_at: "2026-11-17T20:00:00Z",
  is_overdue: true,
  completed_at: null,
  cancelled_at: null,
  cancel_reason: "",
  created_at: "2026-11-10T12:00:00Z",
  updated_at: "2026-11-10T12:00:00Z",
};

export const OPPORTUNITY_TASK: Task = {
  ...TASK,
  id: "t-2",
  title: "Enviar simulación",
  description: "",
  priority: { code: "LOW", label: "Baja" },
  parent: {
    type: "OPPORTUNITY",
    type_label: "Oportunidad",
    id: "op-1",
    code: null,
    client_display_name: "Pedro Gil",
  },
  due_at: null,
  is_overdue: false,
};

export const COMPLETED_TASK: Task = {
  ...TASK,
  id: "t-3",
  title: "Tarea hecha",
  status: "COMPLETED",
  status_label: "Completada",
  is_overdue: false,
};

export const taskPage = (items: Task[], total = items.length) => ({
  items,
  page: 1,
  page_size: 20,
  total,
  next: null,
  previous: null,
});

const item = (code: string, label: string, order: number) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active: true,
  parent_id: null,
  parent_code: null,
  metadata: {},
});

export const BOOTSTRAP = {
  metadata_version: 1,
  actor: "INTERNAL",
  permissions: [],
  on_demand_catalogs: [],
  features: {},
  catalogs: {
    loan_purpose: [item("NEW", "Vivienda nueva", 1)],
    task_priority: [item("LOW", "Baja", 10), item("MEDIUM", "Media", 20), item("HIGH", "Alta", 30)],
    application_status: [
      item("DRAFT", "Borrador", 10),
      item("WAITING_BUYER_DATA", "Esperando datos del comprador", 20),
      item("DISBURSED", "Desembolsada", 110),
    ],
  },
};

export const BANKS = {
  items: [{ id: "b-1", code: "BCO", name: "Bancolombia", short_name: "" }],
  page: 1,
  page_size: 100,
  total: 1,
  next: null,
  previous: null,
};

export const ADVISORS = {
  items: [
    {
      id: "u-lucia",
      email: "lucia@example.com",
      first_name: "Lucía",
      last_name: "Rojas",
      name: "Lucía Rojas",
      phone: "",
      status: "ACTIVE",
      roles: ["ADVISOR"],
      partner: null,
      last_login: null,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
  ],
  page: 1,
  page_size: 100,
  total: 1,
  next: null,
  previous: null,
};
