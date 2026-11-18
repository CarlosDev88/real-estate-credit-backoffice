import { http, HttpResponse } from "msw";

import type {
  BuyerApplicationDetail as Detail,
  BuyerConsent,
  BuyerDocumentSlot as Slot,
  BuyerSession,
} from "@/features/buyer-portal/queries";
import { apiUrl } from "@/test/msw-server";

export const APP_ID = "0b8e6a52-1f7e-4c55-9d6a-3f2c4a1b2c3d";

export function sessionFixture(overrides: Partial<BuyerSession> = {}): BuyerSession {
  return {
    session: {
      id: "s-1",
      created_at: "2026-11-17T10:00:00Z",
      expires_at: new Date(Date.now() + 21 * 3_600_000 + 60_000).toISOString(),
    },
    buyer: { display_name: "Sofía Herrera" },
    application: {
      id: APP_ID,
      code: "SOL-000182",
      public_status: "WAITING_DOCUMENTS",
      public_status_label: "Estamos revisando tus documentos",
      is_editable: true,
      is_closed: false,
    },
    pending_consents: [],
    ...overrides,
  };
}

export function consentFixture(overrides: Partial<BuyerConsent> = {}): BuyerConsent {
  return {
    id: "c-data",
    code: "DATA_PROCESSING",
    version: 1,
    title: "Tratamiento de datos personales",
    body: "Autorizo el tratamiento de mis datos.",
    content_hash: "h",
    effective_from: "2026-01-01T00:00:00Z",
    required: true,
    status: "PENDING",
    accepted_at: null,
    ...overrides,
  };
}

export function apiError(status: number, code: string, message = "Error de prueba.") {
  return HttpResponse.json({ code, message, details: [], request_id: "req-1" }, { status });
}

/** Sesión y slots vacíos: lo mínimo para pintar el marco del portal. */
export function portalHandlers(session: BuyerSession = sessionFixture()) {
  return [
    http.get(apiUrl("/buyer/session"), () => HttpResponse.json(session)),
    http.get(apiUrl(`/buyer/applications/${session.application.id}/document-slots`), () =>
      HttpResponse.json({
        items: [],
        page: 1,
        page_size: 100,
        total: 0,
        next: null,
        previous: null,
      }),
    ),
    // F5: el número de avisos sin leer de la navegación.
    http.get(apiUrl("/buyer/notifications/unread-count"), () => HttpResponse.json({ count: 0 })),
  ];
}

const BANK = {
  id: "b-1",
  code: "BOG",
  name: "Banco de Bogotá S.A.",
  short_name: "Banco de Bogotá",
};

export const PRIMARY_ID = "p-1";
export const CO_ID = "p-2";

export function detailFixture(overrides: Partial<Detail> = {}): Detail {
  return {
    id: APP_ID,
    code: "SOL-000182",
    public_status: "WAITING_DOCUMENTS",
    public_status_label: "Estamos revisando tus documentos",
    is_editable: true,
    is_closed: false,
    purpose: { code: "HOUSING", label: "Vivienda" },
    next_action: "Sube los documentos que te faltan.",
    progress_percentage: 62,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-17T10:00:00Z",
    version: 7,
    progress: {
      percentage: 62,
      data_percentage: 100,
      documents_percentage: 62,
      documents_required_total: 16,
      documents_completed_total: 10,
      items: [
        { code: "DOCS", complete: false, message: "Faltan 3 documentos.", participant_id: null },
        { code: "DATA", complete: true, message: "Datos completos.", participant_id: null },
      ],
    },
    advisor: { full_name: "Paula Rincón", email: "paula@example.com", phone: "3001234567" },
    stages: [
      { code: "DATA", label: "Tus datos", state: "done", state_label: "Completos" },
      { code: "DOCS", label: "Documentos", state: "current", state_label: "En curso" },
      { code: "BANK", label: "Respuesta del banco", state: "pending", state_label: "Pendiente" },
    ],
    participants: [
      {
        id: PRIMARY_ID,
        role: "PRIMARY",
        role_label: "Titular",
        full_name: "Sofía Herrera",
        contributes_income: true,
      },
      {
        id: CO_ID,
        role: "CO_APPLICANT",
        role_label: "Segundo solicitante",
        full_name: "Daniel Mejía",
        contributes_income: true,
      },
    ],
    property: {
      project: { id: "pr-1", name: "Torres del Parque" },
      property_type: { code: "APT", label: "Apartamento" },
      condition: { code: "NEW", label: "Nuevo" },
      city: { code: "11001", label: "Bogotá" },
      address: "Calle 1 # 2-3",
      unit_reference: "Apto 1204",
      estimated_value_cop: 500_000_000,
      is_owned_by_applicant: false,
      updated_at: "2026-11-10T10:00:00Z",
    },
    financing: {
      financing_mode: { code: "BANK", label: "Crédito bancario" },
      bank_product: {
        id: "bp-1",
        code: "HIP",
        name: "Hipotecario",
        product_type: { code: "MORTGAGE", label: "Hipotecario" },
        bank: BANK,
      },
      requested_amount_cop: 365_000_000,
      term_months: 240,
      currency_mode: null,
      amortization_mode: null,
      own_resources_cop: 135_000_000,
      uses_severance_funds: false,
      severance_funds_cop: 0,
      external_approved_amount_cop: null,
      updated_at: "2026-11-10T10:00:00Z",
    },
    latest_bank_update: {
      response_type: "OBSERVATION",
      response_type_label: "Observación del banco",
      received_at: "2026-11-16T15:00:00Z",
      public_message: "El banco pide un extracto más reciente.",
    },
    ...overrides,
  } as Detail;
}

export function slotFixture(overrides: Partial<Slot> = {}): Slot {
  return {
    id: "slot-1",
    participant: {
      id: PRIMARY_ID,
      role: "PRIMARY",
      role_label: "Titular",
      full_name: "Sofía Herrera",
    },
    document_type: {
      code: "PAYSLIP",
      name: "Desprendible",
      description: "Últimos 3 meses.",
      holder_scope: "PARTICIPANT",
    },
    label: "Desprendible de nómina 1 de 3",
    slot_index: 1,
    is_required: true,
    minimum_files: 1,
    alternative_group_code: null,
    validity_days: null,
    allowed_mime_types: ["application/pdf", "image/jpeg", "image/png"],
    max_size_bytes: 10 * 1024 * 1024,
    status: "PENDING",
    public_status: "TO_UPLOAD",
    public_status_label: "Te falta",
    can_upload: true,
    needs_action: true,
    current_file: null,
    rejection: null,
    updated_at: "2026-11-15T10:00:00Z",
    ...overrides,
  } as Slot;
}

export function slotsPage(items: Slot[]) {
  return HttpResponse.json({
    items,
    page: 1,
    page_size: 100,
    total: items.length,
    next: null,
    previous: null,
  });
}
