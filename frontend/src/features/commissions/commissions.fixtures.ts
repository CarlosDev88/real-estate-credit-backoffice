import type {
  CommissionPlan,
  CommissionSettlement,
  CommissionShare,
  MyCommission,
} from "@/features/commissions/queries";

// Respuestas de ejemplo con la forma del contrato (módulo 16). Datos inventados.

const BASE_ME = {
  email: "persona@example.com",
  scope: { assigned_applications_only: false, partner_id: null },
};

export const ADMIN_ME = {
  ...BASE_ME,
  id: "u-admin",
  name: "Adriana Mejía",
  role: "ADMIN",
  role_label: "Administrador",
  roles: ["ADMIN"],
  permissions: [
    "applications.read",
    "banks.read",
    "users.read",
    "commissions.read",
    "commissions.manage",
    "commission_plans.read",
    "commission_plans.manage",
  ],
};

/** Solo consulta: ve liquidaciones, sin pagar ni anular ni planes. */
export const READER_ME = {
  ...ADMIN_ME,
  id: "u-reader",
  permissions: ["commissions.read"],
};

export const ADVISOR_ME = {
  ...BASE_ME,
  id: "u-lucia",
  name: "Lucía Rojas",
  role: "ADVISOR",
  role_label: "Asesor",
  roles: ["ADVISOR"],
  permissions: ["applications.read", "commissions.read_own"],
  scope: { assigned_applications_only: true, partner_id: null },
};

export const ADVISOR_SHARE: CommissionShare = {
  id: "sh-adv",
  beneficiary: { id: "u-lucia", name: "Lucía Rojas" },
  beneficiary_role: "ADVISOR",
  beneficiary_role_label: "Asesor",
  share_pct: "70.0000",
  amount_cop: 1_960_000,
  status: "PENDING",
  status_label: "Pendiente de pago",
  paid_at: null,
  paid_by: null,
  payment_reference: "",
};

export const BROKER_SHARE: CommissionShare = {
  id: "sh-bro",
  beneficiary: { id: "u-bruno", name: "Bruno Salas" },
  beneficiary_role: "INDEPENDENT_BROKER",
  beneficiary_role_label: "Broker independiente",
  share_pct: "30.0000",
  amount_cop: 840_000,
  status: "PAID",
  status_label: "Pagada",
  paid_at: "2026-11-10",
  paid_by: { id: "u-admin", name: "Adriana Mejía" },
  payment_reference: "TRF-1029",
};

export const SETTLEMENT: CommissionSettlement = {
  id: "st-1",
  application: { id: "app-8", code: "SOL-000008" },
  filing_response_id: "fr-1",
  plan_id: "pl-1",
  lead_origin_code: "BROKER",
  lead_origin_label: "Broker",
  disbursed_on: "2026-11-05",
  base_amount_cop: 280_000_000,
  rate_pct: "1.0000",
  total_amount_cop: 2_800_000,
  status: "ACTIVE",
  status_label: "Vigente",
  needs_review: false,
  voided_at: null,
  voided_by: null,
  void_reason: "",
  shares: [
    ADVISOR_SHARE,
    {
      ...BROKER_SHARE,
      status: "PENDING",
      status_label: "Pendiente de pago",
      paid_at: null,
      paid_by: null,
      payment_reference: "",
    },
  ],
  created_at: "2026-11-05T15:00:00-05:00",
  updated_at: "2026-11-05T15:00:00-05:00",
};

/** Con una parte pagada y marcada para revisión: no se puede anular. */
export const PAID_SETTLEMENT: CommissionSettlement = {
  ...SETTLEMENT,
  id: "st-2",
  application: { id: "app-9", code: "SOL-000009" },
  needs_review: true,
  shares: [ADVISOR_SHARE, BROKER_SHARE],
};

export const VOIDED_SETTLEMENT: CommissionSettlement = {
  ...SETTLEMENT,
  id: "st-3",
  application: { id: "app-10", code: "SOL-000010" },
  status: "VOIDED",
  status_label: "Anulada",
  voided_at: "2026-11-06T10:00:00-05:00",
  voided_by: { id: "u-admin", name: "Adriana Mejía" },
  void_reason: "Desembolso corregido",
  shares: [{ ...ADVISOR_SHARE, status: "VOIDED", status_label: "Anulada" }],
};

export const PLAN: CommissionPlan = {
  id: "pl-1",
  bank_product: {
    id: "bp-1",
    code: "HIP-BC",
    name: "Hipotecario vivienda",
    bank: { id: "b-1", code: "BC", name: "Bancolombia", short_name: "" },
  },
  rate_pct: "1.0000",
  advisor_share_pct: "70.0000",
  broker_share_pct: "30.0000",
  valid_from: "2026-01-01",
  valid_until: null,
  notes: "Plan de demo",
  in_use: true,
  version: 1,
  created_by: { id: "u-admin", name: "Adriana Mejía" },
  created_at: "2026-01-01T08:00:00-05:00",
  updated_at: "2026-01-01T08:00:00-05:00",
};

export const UNUSED_PLAN: CommissionPlan = {
  ...PLAN,
  id: "pl-2",
  bank_product: {
    id: "bp-2",
    code: "LEA-DV",
    name: "Leasing habitacional",
    bank: { id: "b-2", code: "DV", name: "Banco Davivienda", short_name: "Davivienda" },
  },
  rate_pct: "0.7500",
  valid_from: "2027-01-01",
  notes: "",
  in_use: false,
  version: 4,
};

export const BANK_PRODUCTS = {
  items: [
    {
      id: "bp-1",
      code: "HIP-BC",
      name: "Hipotecario vivienda",
      bank: { id: "b-1", code: "BC", name: "Bancolombia", short_name: "" },
      product_type: { code: "MORTGAGE", label: "Hipotecario" },
      status: "ACTIVE",
      min_amount_cop: 0,
      max_amount_cop: 0,
      min_term_months: 60,
      max_term_months: 240,
      valid_from: "2026-01-01",
      valid_to: null,
      purposes: [],
      created_at: "2026-01-01T08:00:00-05:00",
      updated_at: "2026-01-01T08:00:00-05:00",
    },
  ],
  page: 1,
  page_size: 100,
  total: 1,
  next: null,
  previous: null,
};

export const MY_COMMISSION: MyCommission = {
  id: "sh-adv",
  application_code: "SOL-000008",
  client_display_name: "Mariana Cárdenas Ríos",
  disbursed_on: "2026-11-05",
  share_pct: "70.0000",
  amount_cop: 1_960_000,
  status: "PAID",
  status_label: "Pagada",
  paid_at: "2026-11-12",
};

export function page<T>(items: T[], total = items.length) {
  return { items, page: 1, page_size: 20, total, next: null, previous: null };
}

export const BOOTSTRAP = {
  metadata_version: 1,
  actor: "internal",
  permissions: [],
  catalogs: {},
  on_demand_catalogs: [],
  features: {},
};

export const BANKS = page([
  { id: "b-1", code: "BC", name: "Bancolombia", short_name: "", status: "ACTIVE" },
]);
export const ADVISORS = page([{ id: "u-lucia", name: "Lucía Rojas", email: "lucia@example.com" }]);
export const BROKERS = page([{ id: "u-bruno", name: "Bruno Salas", email: "bruno@example.com" }]);
