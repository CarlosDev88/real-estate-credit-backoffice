import type {
  Address,
  ClientApplication,
  OpportunityDetail,
} from "@/features/clients/detail-queries";
import type { Client, ClientDetail } from "@/features/clients/queries";

// Datos de prueba de clientes, compartidos por las pruebas de la feature.

export const CLIENTS_ME = {
  id: "u-1",
  name: "Asesora",
  email: "asesor@example.com",
  role: "ADVISOR",
  role_label: "Asesor",
  roles: ["ADVISOR"],
  permissions: ["applications.read", "clients.read", "clients.create", "clients.update"],
  scope: { assigned_applications_only: true, partner_id: null },
};

const item = (code: string, label: string, order: number, active = true) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active,
  parent_id: null,
  parent_code: null,
  metadata: {},
});

export const CLIENTS_BOOTSTRAP = {
  metadata_version: 1,
  actor: "INTERNAL",
  permissions: [],
  on_demand_catalogs: [],
  features: {},
  catalogs: {
    identity_document_type: [
      item("CE", "Cédula de extranjería", 2),
      item("CC", "Cédula de ciudadanía", 1),
      item("OLD", "Tipo retirado", 3, false),
    ],
    lead_origin: [
      item("DIRECT", "Directo", 1),
      item("BROKER", "Broker", 2),
      item("RETIRED", "Origen retirado", 3, false),
    ],
    opportunity_status: [
      item("NEW", "Nueva", 1),
      item("ASSIGNED", "Asignada", 2),
      item("CONVERTED", "Convertida", 3),
      item("LOST", "Perdida", 4, false),
    ],
    loan_purpose: [item("NEW_HOME", "Vivienda nueva", 1), item("USED_HOME", "Vivienda usada", 2)],
    opportunity_lost_reason: [
      item("NO_RESPONSE", "No responde", 1),
      item("OTHER_BANK", "Eligió otro banco", 2),
    ],
    address_type: [item("RESIDENCE", "Residencia", 1), item("WORK", "Trabajo", 2)],
  },
};

export const MUNICIPALITIES = {
  catalog: "municipality",
  name: "Municipio",
  version: 1,
  items: [item("11001", "Bogotá D.C.", 1), item("05001", "Medellín", 2)],
};

export function makeAddress(n: number, overrides: Partial<Address> = {}): Address {
  return {
    id: `ad-${n}`,
    client_id: "cl-1",
    address_type: { code: "RESIDENCE", label: "Residencia" },
    city: { code: "11001", label: "Bogotá D.C." },
    line1: `Calle ${n} # 10-20`,
    line2: "",
    postal_code: "",
    is_primary: n === 1,
    created_at: "2026-11-10T15:00:00Z",
    updated_at: "2026-11-10T15:00:00Z",
    ...overrides,
  };
}

type OpportunityAction = OpportunityDetail["available_actions"][number];

export function action(
  code: string,
  label: string,
  kind: OpportunityAction["kind"],
  target_status: OpportunityAction["target_status"],
  target_status_label: string,
  reason_required = false,
): OpportunityAction {
  return { code, label, kind, target_status, target_status_label, reason_required };
}

export function makeOpportunity(n: number, overrides: Partial<OpportunityDetail> = {}) {
  const base: OpportunityDetail = {
    id: `op-${n}`,
    client: { id: "cl-1", full_name: "Laura Gómez Vélez" },
    project: { id: "pr-1", name: "Torres del Parque", partner_name: "Constructora Andes" },
    status: "ASSIGNED",
    status_label: "Asignada",
    origin: { code: "DIRECT", label: "Directo" },
    origin_user: { id: "u-1", name: "Asesora" },
    assigned_advisor: { id: "u-1", name: "Asesora" },
    lost_reason: null,
    converted_at: null,
    created_at: "2026-11-12T15:00:00Z",
    updated_at: "2026-11-12T15:00:00Z",
    // Las de una oportunidad `ASSIGNED` (contrato: primaria, secundarias, destructivas).
    available_actions: [
      action("CONVERT_ASSIGNED", "Convertir en solicitud", "primary", "CONVERTED", "Convertida"),
      action("MARK_CONTACTED", "Marcar como contactada", "secondary", "CONTACTED", "Contactada"),
      action("MARK_LOST_ASSIGNED", "Marcar como perdida", "destructive", "LOST", "Perdida", true),
      action("CANCEL_ASSIGNED", "Cancelar", "destructive", "CANCELLED", "Cancelada"),
    ],
    assignments: [
      {
        id: "as-1",
        advisor: { id: "u-1", name: "Asesora" },
        assigned_by: { id: "u-9", name: "Admin" },
        reason: "Zona norte",
        created_at: "2026-11-12T16:00:00Z",
        ended_at: null,
      },
    ],
  };
  return { ...base, ...overrides };
}

export function page<T>(items: T[]) {
  return { items, page: 1, page_size: 100, total: items.length, next: null, previous: null };
}

export function makeClientApplication(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `app-${n}`,
    code: `SOL-00000${n}`,
    status: "DRAFT",
    status_label: "Borrador",
    purpose: { code: "NEW_HOME", label: "Vivienda nueva" },
    bank_product: null,
    requested_amount_cop: null,
    completeness_pct: null,
    ready_to_file_blocked: null,
    last_buyer_activity_at: null,
    buyer_inactive: null,
    updated_at: "2026-11-15T15:00:00Z",
    ...overrides,
  } as unknown as ClientApplication;
}

export function makeClient(n: number, overrides: Partial<Client> = {}): Client {
  return {
    id: `cl-${n}`,
    document_type: { code: "CC", label: "Cédula de ciudadanía" },
    document_number: String(1_000_000 + n),
    first_names: `Persona`,
    last_names: `Número ${n}`,
    full_name: `Persona Número ${n}`,
    birth_date: null,
    email: `persona${n}@example.com`,
    phone: "+573001234567",
    origin: { code: "DIRECT", label: "Directo" },
    created_by: { id: "u-1", name: "Asesora" },
    applications_count: 2,
    created_at: "2026-11-10T15:00:00Z",
    updated_at: "2026-11-10T15:00:00Z",
    ...overrides,
  };
}

export function makeClientDetail(overrides: Partial<ClientDetail> = {}): ClientDetail {
  return {
    ...makeClient(1, {
      first_names: "Laura",
      last_names: "Gómez Vélez",
      full_name: "Laura Gómez Vélez",
      document_number: "1032445908",
      email: "laura.gomez@email.com",
      phone: "+573104458821",
      birth_date: "1990-04-12",
    }),
    addresses: [],
    ...overrides,
  };
}

export function apiError(code: string, message: string, details: unknown[] = []) {
  return { code, message, details, request_id: "req-1" };
}
