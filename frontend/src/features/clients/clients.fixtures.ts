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
  },
};

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
