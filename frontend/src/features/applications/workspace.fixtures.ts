// Datos de prueba del expediente (solo para las pruebas con MSW).
import { http, HttpResponse } from "msw";

import type {
  ApplicationDetail,
  BankRuleEvaluation,
  BuyerAccessLink,
  Completeness,
  ConsentRecord,
  DocumentSlot,
  FinancialProfile,
  Financing,
  Participant,
  Property,
  StatusHistoryEntry,
} from "@/features/applications/workspace-queries";
import { apiUrl, server } from "@/test/msw-server";

export const APP_ID = "app-1";
const base = `/applications/${APP_ID}`;

export const ALL_PERMISSIONS = [
  "applications.read",
  "applications.update",
  "applications.transition",
  "applications.withdraw",
  "applications.assign",
  "users.read",
  "buyer_access.read",
  "buyer_access.create",
  "consents.read",
];

export const me = (permissions = ALL_PERMISSIONS) => ({
  id: "u-1",
  name: "Paula Rincón",
  email: "paula@example.com",
  role: "ADVISOR",
  roles: ["ADVISOR"],
  permissions,
  scope: { assigned_applications_only: true, partner_id: null },
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
    application_status: [
      item("DRAFT", "Borrador", 1),
      item("WAITING_DOCUMENTS", "Esperando documentos", 2),
      item("DOCUMENTS_REVIEW", "Documentos en revisión", 3),
      item("READY_TO_FILE", "Lista para radicar", 4),
    ],
    application_transition_reason: [
      item("CLIENT_UNREACHABLE", "No fue posible contactar al cliente", 1),
    ],
    application_withdrawal_reason: [item("OTHER_FINANCING", "Compró con otra entidad", 1)],
    buyer_access_channel: [item("EMAIL", "Correo", 1), item("COPY_LINK", "Copiar enlace", 2)],
  },
};

export const ACTIONS = {
  ready: {
    code: "MARK_READY_TO_FILE",
    label: "Marcar lista para radicar",
    target_status: "READY_TO_FILE",
    guard_code: "APPLICATION_READY_TO_FILE",
  },
  back: {
    code: "RETURN_TO_DOCUMENTS",
    label: "Devolver a carga de documentos",
    target_status: "WAITING_DOCUMENTS",
    guard_code: "",
  },
  cancel: {
    code: "CANCEL_DOCUMENTS_REVIEW",
    label: "Cancelar solicitud",
    target_status: "CANCELLED",
    guard_code: "",
  },
  withdraw: {
    code: "WITHDRAW_DOCUMENTS_REVIEW",
    label: "Desistir",
    target_status: "WITHDRAWN",
    guard_code: "",
  },
} as const;

const BANK = { id: "b-bog", code: "BOG", name: "Banco de Bogotá", short_name: "" };

export function makeDetail(overrides: Partial<ApplicationDetail> = {}): ApplicationDetail {
  return {
    id: APP_ID,
    code: "SOL-000182",
    status: "DOCUMENTS_REVIEW",
    status_label: "Documentos en revisión",
    opportunity_id: "op-1",
    applicant: {
      id: "cl-1",
      full_name: "Sofía Herrera",
      document_type: "CC",
      document_number: "1",
    },
    participants_summary: { co_applicants: 1, solidary_debtors: 0 },
    purpose: { code: "NEW", label: "Vivienda nueva" },
    bank_product: {
      id: "p-1",
      code: "LEASING",
      name: "Leasing",
      product_type: { code: "LEASING", label: "Leasing habitacional" },
      bank: BANK,
    },
    requested_amount_cop: 365_000_000,
    completeness_pct: 81,
    ready_to_file_blocked: null,
    last_buyer_activity_at: "2026-11-10T10:00:00Z",
    buyer_inactive: null,
    assigned_advisor: { id: "u-1", name: "Paula Rincón" },
    origin: { code: "BROKER", label: "Broker" },
    project: null,
    version: 14,
    current_stage_started_at: "2026-11-09T10:00:00Z",
    ready_to_file_at: null,
    withdrawn_at: null,
    withdrawal_reason: null,
    closed_at: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-10T10:00:00Z",
    property: null,
    assignments: [],
    available_actions: [ACTIONS.ready, ACTIONS.back, ACTIONS.cancel, ACTIONS.withdraw],
    ...overrides,
  } as ApplicationDetail;
}

export function makeCompleteness(overrides: Partial<Completeness> = {}): Completeness {
  return {
    percentage: 81,
    data_percentage: 100,
    documents_percentage: 62,
    ready_to_file: true,
    ready_to_file_problems: [],
    items: [
      { code: "property", complete: true, message: "Inmueble registrado.", participant_id: null },
      {
        code: "financial_profile",
        complete: false,
        message: "Registra el perfil financiero de Daniel Mejía.",
        participant_id: "pa-2",
      },
    ],
    documents: {
      verified: false,
      required_total: 16,
      completed_total: 10,
      message: "Faltan 6 de 16 documentos obligatorios.",
      slots: [],
    },
    ...overrides,
  } as Completeness;
}

const client = (id: string, name: string) => ({
  id,
  document_type: { code: "CC", label: "Cédula" },
  document_number: id,
  first_names: name.split(" ")[0]!,
  last_names: name.split(" ")[1]!,
  full_name: name,
  birth_date: null,
  email: `${id}@example.com`,
  phone: "",
  origin: null,
  created_by: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
});

export const PARTICIPANTS: Participant[] = [
  {
    id: "pa-1",
    application_id: APP_ID,
    client: client("cl-1", "Sofía Herrera"),
    role: "PRIMARY",
    contributes_income: true,
    income_share_cop: null,
    is_active: true,
    financial_profile_id: "fp-1",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
  },
  {
    id: "pa-2",
    application_id: APP_ID,
    client: client("cl-2", "Daniel Mejía"),
    role: "CO_APPLICANT",
    contributes_income: true,
    income_share_cop: null,
    is_active: true,
    financial_profile_id: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
  },
];

export const PROFILE: FinancialProfile = {
  id: "fp-1",
  participant_id: "pa-1",
  employment_profile: { code: "EMPLOYEE", label: "Empleada" },
  contract_type: null,
  employer_name: "",
  job_title: "",
  employment_start_date: null,
  monthly_income_cop: 7_800_000,
  income_sources_total_cop: 7_800_000,
  monthly_expenses_cop: 2_350_000,
  assets_cop: 0,
  liabilities_cop: 0,
  funds_origin: null,
  data_confirmed_at: "2026-11-05T10:00:00Z",
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

export const PROPERTY: Property = {
  id: "pr-1",
  project: { id: "pj-1", name: "Torres del Parque" },
  property_type: { code: "APARTMENT", label: "Apartamento" },
  condition: { code: "NEW", label: "Nueva" },
  city: { code: "68276", label: "Floridablanca" },
  address: "",
  unit_reference: "Apartamento 1204",
  estimated_value_cop: 520_000_000,
  is_owned_by_applicant: null,
  ownership_notes: "",
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

export const FINANCING = {
  id: "f-1",
  application_id: APP_ID,
  financing_mode: { code: "BANK_CREDIT", label: "Crédito bancario" },
  bank_product: null,
  requested_amount_cop: 365_000_000,
  term_months: 240,
  currency_mode: null,
  amortization_mode: null,
  own_resources_cop: 0,
  uses_severance_funds: false,
  severance_funds_cop: 0,
  external_approved_amount_cop: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
} as Financing;

export function makeEvaluation(overrides: Partial<BankRuleEvaluation> = {}): BankRuleEvaluation {
  return {
    id: "ev-1",
    bank_product_id: "p-1",
    application_version: 14,
    is_current: true,
    eligible: true,
    blocking: [],
    warnings: [
      {
        rule_code: "INCOME_MIN",
        outcome: "MISSING_DATA",
        message: "Ingreso del hogar cercano al mínimo del producto.",
        field: null,
        unresolved_fields: [],
      },
    ],
    evaluated_at: "2026-11-10T08:00:00Z",
    ...overrides,
  };
}

export const LINK: BuyerAccessLink = {
  id: "l-1",
  application_id: APP_ID,
  client_id: "cl-1",
  status: "CONSUMED",
  delivery_channel: { code: "EMAIL", label: "Correo" },
  created_by: null,
  created_at: "2026-11-08T15:00:00Z",
  expires_at: "2026-11-11T15:00:00Z",
  consumed_at: "2026-11-08T16:00:00Z",
  revoked_at: null,
  session: {
    id: "s-1",
    created_at: "2026-11-08T16:00:00Z",
    expires_at: "2026-11-12T16:00:00Z",
    revoked_at: null,
    last_seen_at: null,
    is_active: true,
  },
};

const consent = (
  id: string,
  definition: string,
  title: string,
  action: "ACCEPTED" | "WITHDRAWN",
  at: string,
): ConsentRecord => ({
  id,
  consent_definition: { id: definition, code: definition, version: 1, title, content_hash: "x" },
  client: { id: "cl-1", full_name: "Sofía Herrera" },
  user: null,
  action,
  ip_address: null,
  user_agent_summary: "",
  buyer_session_id: "s-1",
  created_at: at,
});

export const CONSENTS: ConsentRecord[] = [
  consent("c-3", "d-2", "Autorización de consulta", "WITHDRAWN", "2026-11-09T10:00:00Z"),
  consent("c-2", "d-2", "Autorización de consulta", "ACCEPTED", "2026-11-08T10:00:00Z"),
  consent("c-1", "d-1", "Tratamiento de datos", "ACCEPTED", "2026-11-08T10:00:00Z"),
];

export const HISTORY: StatusHistoryEntry[] = [
  {
    id: "h-3",
    from_status: "WAITING_DOCUMENTS",
    to_status: "DOCUMENTS_REVIEW",
    transition_code: "SUBMIT",
    reason: null,
    comment: "",
    actor: null,
    buyer_session_id: "s-1",
    application_version: 14,
    created_at: "2026-11-09T10:00:00Z",
  },
  {
    id: "h-2",
    from_status: "DRAFT",
    to_status: "WAITING_DOCUMENTS",
    transition_code: "SEND",
    reason: { code: "OTHER", label: "Otro" },
    comment: "Datos completos por teléfono.",
    actor: { id: "u-1", name: "Paula Rincón" },
    buyer_session_id: null,
    application_version: 5,
    created_at: "2026-11-02T10:00:00Z",
  },
  {
    id: "h-1",
    from_status: null,
    to_status: "DRAFT",
    transition_code: null,
    reason: null,
    comment: "",
    actor: { id: "u-1", name: "Paula Rincón" },
    buyer_session_id: null,
    application_version: 1,
    created_at: "2026-11-01T10:00:00Z",
  },
] as StatusHistoryEntry[];

export function makeSlot(n: number, label: string): DocumentSlot {
  return {
    id: `s-${n}`,
    application_id: APP_ID,
    participant: {
      id: "pa-1",
      role: "PRIMARY",
      client_id: "cl-1",
      full_name: "Sofía Herrera",
      is_active: true,
    },
    document_type: {
      id: "dt",
      code: "DOC",
      name: label,
      is_active: true,
      holder_scope: "PARTICIPANT",
      allowed_mime_types: [],
      max_size_bytes: 1,
    },
    label,
    slot_index: 1,
    requirement_id: null,
    requirement_version: null,
    is_required: true,
    is_waivable: false,
    minimum_files: 1,
    alternative_group_code: null,
    validity_days: null,
    sort_order: n,
    status: "UPLOADED",
    waiver_reason: null,
    current_file: {
      id: `f-${n}`,
      version_number: 1,
      status: "UPLOADED",
      client_filename: `archivo-${n}.pdf`,
      document_date: null,
      expires_at: null,
      scan_status: "CLEAN",
      created_at: "2026-11-10T09:00:00Z",
    },
    locked_at: null,
    is_retired: false,
    retired_at: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-10T09:00:00Z",
  } as DocumentSlot;
}

const page = <T>(items: T[], total = items.length) => ({
  items,
  page: 1,
  page_size: 20,
  total,
  next: null,
  previous: null,
});

export interface WorkspaceApi {
  detail: ApplicationDetail;
  completeness: Completeness;
  evaluation: BankRuleEvaluation | null;
  property: Property | null;
  slots: DocumentSlot[];
  slotsTotal: number;
  permissions: string[];
  calls: { detail: number };
}

/** Handlers de todo el expediente; cada prueba cambia lo que necesita. */
export function useWorkspaceApi(overrides: Partial<WorkspaceApi> = {}): WorkspaceApi {
  const state: WorkspaceApi = {
    detail: makeDetail(),
    completeness: makeCompleteness(),
    evaluation: makeEvaluation(),
    property: PROPERTY,
    slots: [makeSlot(1, "Certificado laboral"), makeSlot(2, "Extracto bancario 1 de 3")],
    slotsTotal: 2,
    permissions: ALL_PERMISSIONS,
    calls: { detail: 0 },
    ...overrides,
  };
  const notFound = () =>
    HttpResponse.json(
      { code: "RESOURCE_NOT_FOUND", message: "No existe.", details: [], request_id: "r" },
      { status: 404 },
    );
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(me(state.permissions))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl(base), () => {
      state.calls.detail += 1;
      return HttpResponse.json(state.detail, {
        headers: { ETag: `W/"${state.detail.version + 1}"` },
      });
    }),
    http.get(apiUrl(`${base}/completeness`), () => HttpResponse.json(state.completeness)),
    http.get(apiUrl(`${base}/participants`), () => HttpResponse.json(page(PARTICIPANTS))),
    http.get(apiUrl("/application-participants/pa-1/financial-profile"), () =>
      HttpResponse.json(PROFILE),
    ),
    http.get(apiUrl(`${base}/property`), () =>
      state.property ? HttpResponse.json(state.property) : notFound(),
    ),
    http.get(apiUrl(`${base}/financing`), () => HttpResponse.json(FINANCING)),
    http.get(apiUrl(`${base}/bank-rule-evaluations/latest`), () =>
      state.evaluation ? HttpResponse.json(state.evaluation) : notFound(),
    ),
    http.get(apiUrl(`${base}/buyer-access-links`), () => HttpResponse.json(page([LINK]))),
    http.get(apiUrl(`${base}/consents`), () => HttpResponse.json(page(CONSENTS))),
    http.get(apiUrl(`${base}/status-history`), () => HttpResponse.json(page(HISTORY))),
    http.get(apiUrl(`${base}/document-slots`), () =>
      HttpResponse.json(page(state.slots, state.slotsTotal)),
    ),
  );
  return state;
}
