import type {
  DashboardBankResults,
  DashboardFunnel,
  DashboardSummary,
  DashboardWorkload,
} from "@/features/dashboard/queries";

// Respuestas de ejemplo con la forma del contrato (módulo 15).

export const PERIOD = { date_from: "2026-11-01", date_to: "2026-11-18" };

export const ADMIN_ME = {
  id: "u-admin",
  name: "Adriana Mejía",
  email: "admin@example.com",
  role: "ADMIN",
  role_label: "Administrador",
  roles: ["ADMIN"],
  permissions: [
    "dashboard.read",
    "applications.read",
    "users.read",
    "banks.read",
    "tasks.read",
    "workday.read",
  ],
  scope: { assigned_applications_only: false, partner_id: null },
};

export const BROKER_ME = {
  ...ADMIN_ME,
  id: "u-broker",
  name: "Camilo Ortiz",
  role: "INDEPENDENT_BROKER",
  role_label: "Broker independiente",
  roles: ["INDEPENDENT_BROKER"],
  permissions: ["dashboard.read", "applications.read"],
  scope: { assigned_applications_only: false, partner_id: "p-1" },
};

export const SUMMARY: DashboardSummary = {
  period: PERIOD,
  clients_created: 45,
  applications_created: 1234,
  snapshot: [
    { status: "DRAFT", status_label: "Borrador", count: 9 },
    { status: "READY_TO_FILE", status_label: "Lista para radicar", count: 5 },
    { status: "FILED", status_label: "Radicada", count: 0 },
    { status: "APPROVED", status_label: "Aprobada", count: 1 },
  ],
  tasks: { overdue: 3, due_today: 2 },
  amounts: {
    requested_total: "7938000000.00",
    approved_total: "189000000.00",
    disbursed_total: "0.00",
  },
};

export const BROKER_SUMMARY: DashboardSummary = {
  period: PERIOD,
  clients_created: 3,
  applications_created: 3,
  snapshot: [{ status: "DRAFT", status_label: "Borrador", count: 1 }],
  tasks: { overdue: 0, due_today: 0 },
};

export const FUNNEL: DashboardFunnel = {
  period: PERIOD,
  stages: [
    { code: "CREATED", label: "Creadas", count: 35, conversion: "1.0000", step_conversion: null },
    {
      code: "DOCUMENTS_COMPLETE",
      label: "Documentos completos",
      count: 17,
      conversion: "0.4857",
      step_conversion: "0.4857",
    },
    {
      code: "READY_TO_FILE",
      label: "Listas para radicar",
      count: 9,
      conversion: "0.2571",
      step_conversion: "0.5294",
    },
    {
      code: "FILED",
      label: "Radicadas",
      count: 4,
      conversion: "0.1143",
      step_conversion: "0.4444",
    },
    {
      code: "APPROVED",
      label: "Aprobadas",
      count: 1,
      conversion: "0.0286",
      step_conversion: "0.2500",
    },
    {
      code: "DISBURSED",
      label: "Desembolsadas",
      count: 0,
      conversion: "0.0000",
      step_conversion: "0.0000",
    },
  ],
};

export const EMPTY_FUNNEL: DashboardFunnel = {
  period: PERIOD,
  stages: FUNNEL.stages.map((s) => ({ ...s, count: 0, conversion: null, step_conversion: null })),
};

export const WORKLOAD: DashboardWorkload = {
  advisors: [
    {
      advisor_id: "a-1",
      advisor_name: "Andrés Patiño",
      open_applications: 10,
      overdue_tasks: 1,
      due_today_tasks: 2,
      waiting_buyer: 3,
      ready_to_file: 4,
    },
    {
      advisor_id: "a-2",
      advisor_name: "Lucía Rojas",
      open_applications: 7,
      overdue_tasks: 0,
      due_today_tasks: 0,
      waiting_buyer: 1,
      ready_to_file: 2,
    },
  ],
};

export const BANK_RESULTS: DashboardBankResults = {
  period: PERIOD,
  banks: [
    {
      bank_id: "b-1",
      bank_name: "Bancolombia",
      filings: 4,
      returned: 1,
      approved: 1,
      rejected: 0,
      disbursed: 0,
      avg_days_to_response: "0.8",
    },
    {
      bank_id: "b-2",
      bank_name: "Banco de Bogotá",
      filings: 2,
      returned: 0,
      approved: 0,
      rejected: 0,
      disbursed: 0,
      avg_days_to_response: null,
    },
  ],
};

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
    loan_purpose: [item("USED", "Vivienda usada", 2), item("NEW", "Vivienda nueva", 1)],
  },
};

export const BANKS = {
  count: 1,
  page: 1,
  page_size: 100,
  total_pages: 1,
  next: null,
  previous: null,
  items: [{ id: "b-1", code: "BCO", name: "Bancolombia S.A.", short_name: "Bancolombia" }],
};

const user = (id: string, name: string) => ({
  id,
  email: `${id}@example.com`,
  first_name: name,
  last_name: "",
  name,
  phone: "",
  status: "ACTIVE",
  roles: ["ADVISOR"],
  partner: null,
  last_login: null,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
});

export const ADVISORS = {
  count: 2,
  page: 1,
  page_size: 100,
  total_pages: 1,
  next: null,
  previous: null,
  items: [user("a-2", "Lucía Rojas"), user("a-1", "Andrés Patiño")],
};

export const FILTER_OUT_OF_SCOPE = {
  code: "FILTER_OUT_OF_SCOPE",
  message: "Uno de los filtros está fuera de tu alcance.",
  details: [
    {
      field: "advisor_id",
      code: "FILTER_OUT_OF_SCOPE",
      message: "Este filtro está fuera de tu alcance.",
    },
  ],
  request_id: "req-1",
};

export const PERMISSION_DENIED = {
  code: "PERMISSION_DENIED",
  message: "No tienes permiso para realizar esta acción.",
  details: [],
  request_id: "req-2",
};
