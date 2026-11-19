import type { BankDetail, BankProduct, Rule } from "@/features/admin-banks/queries";

// Datos de prueba de `/admin/bancos` con la forma del contrato.

export const BANKS_ADMIN = [
  "banks.read",
  "banks.create",
  "banks.update",
  "bank_rules.read",
  "bank_rules.create",
  "bank_rules.update",
  "bank_rules.publish",
];

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

export const BANKS_BOOTSTRAP = {
  metadata_version: 1,
  actor: "ADMIN",
  permissions: [],
  catalogs: {
    bank_product_type: [
      item("MORTGAGE", "Crédito hipotecario", 1),
      item("LEASING", "Leasing habitacional", 2),
    ],
    loan_purpose: [
      item("PURCHASE_NEW", "Compra de vivienda nueva", 1),
      item("REMODEL", "Remodelación", 2),
    ],
  },
  on_demand_catalogs: ["municipality"],
  features: {},
};

export const BANK_ID = "50000000-0000-4000-8000-000000000001";
export const PRODUCT_ID = "60000000-0000-4000-8000-000000000001";

export function makeBank(n: number, overrides: Partial<BankDetail> = {}): BankDetail {
  return {
    id: `50000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    code: `BANCO_${n}`,
    name: `Banco Número ${n}`,
    short_name: n === 1 ? "BN1" : "",
    tax_id: n === 1 ? "860000001-1" : "",
    status: "ACTIVE",
    operational_notes: "",
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-10T15:00:00Z",
    products:
      n === 1
        ? [{ id: PRODUCT_ID, code: "HIPO_VIS", name: "Hipotecario VIS", status: "ACTIVE" }]
        : [],
    ...overrides,
  };
}

export const PRODUCT: BankProduct = {
  id: PRODUCT_ID,
  bank: { id: BANK_ID, code: "BANCO_1", name: "Banco Número 1", short_name: "BN1" },
  code: "HIPO_VIS",
  name: "Hipotecario VIS",
  product_type: { code: "MORTGAGE", label: "Crédito hipotecario" },
  status: "ACTIVE",
  min_amount_cop: 30000000,
  max_amount_cop: 500000000,
  min_term_months: 60,
  max_term_months: 360,
  valid_from: "2026-01-01",
  valid_to: null,
  purposes: [{ code: "PURCHASE_NEW", label: "Compra de vivienda nueva" }],
  created_at: "2026-11-01T15:00:00Z",
  updated_at: "2026-11-10T15:00:00Z",
};

export const CONDITION = {
  operator: "lte",
  left: { field: "financing.term_months" },
  right: 240,
};

export function makeRule(version: number, overrides: Partial<Rule> = {}): Rule {
  return {
    id: `70000000-0000-4000-8000-${String(version).padStart(12, "0")}`,
    bank_product: { id: PRODUCT_ID, code: "HIPO_VIS", name: "Hipotecario VIS", bank: PRODUCT.bank },
    purpose: null,
    code: "PLAZO_MAXIMO",
    version,
    severity: "BLOCKING",
    condition: CONDITION,
    message: "El plazo supera 20 años.",
    status: version === 1 ? "ACTIVE" : "DRAFT",
    valid_from: "2026-11-01T15:00:00Z",
    valid_to: null,
    created_by: { id: "u-1", name: "Adriana Mejía" },
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
    ...overrides,
  };
}
