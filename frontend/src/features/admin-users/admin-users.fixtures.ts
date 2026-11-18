import type { Invitation, Role, User } from "@/features/admin-users/queries";

// Datos de prueba de `/admin/usuarios` con la forma del contrato.

export const ADMIN_PERMISSIONS = [
  "users.read",
  "users.create",
  "users.update",
  "users.manage_status",
  "roles.read",
  "roles.assign",
  "invitations.read",
  "invitations.create",
  "invitations.revoke",
  "partners.read",
];

export const ADMIN_ME = {
  id: "00000000-0000-4000-8000-000000000999",
  name: "Admin Principal",
  email: "admin@example.com",
  role: "ADMIN",
  role_label: "Administrador",
  roles: ["ADMIN"],
  permissions: ADMIN_PERMISSIONS,
  scope: { assigned_applications_only: false, partner_id: null },
};

const role = (code: string, name: string, is_active = true): Role => ({
  id: `role-${code}`,
  code,
  name,
  description: `Descripción de ${name}`,
  is_active,
  permissions: [],
});

export const ROLES: Role[] = [
  role("ADMIN", "Administrador"),
  role("ADVISOR", "Asesor"),
  role("BROKER", "Broker"),
  role("CONSTRUCTION_PARTNER", "Constructora"),
  role("LEGACY", "Rol antiguo", false),
];

export function makeUser(n: number, overrides: Partial<User> = {}): User {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    email: `usuario${n}@example.com`,
    first_name: "Usuario",
    last_name: `Número ${n}`,
    name: `Usuario Número ${n}`,
    phone: "",
    status: "ACTIVE",
    roles: ["ADVISOR"],
    partner: null,
    last_login: null,
    created_at: "2026-11-10T15:00:00Z",
    updated_at: "2026-11-10T15:00:00Z",
    ...overrides,
  };
}

export function makeInvitation(n: number, overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: `10000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    email: `invitado${n}@example.com`,
    role: "ADVISOR",
    partner: null,
    invited_by: { id: "00000000-0000-4000-8000-000000000999", name: "Admin Principal" },
    status: "PENDING",
    expires_at: "2026-11-20T15:00:00Z",
    consumed_at: null,
    revoked_at: null,
    created_at: "2026-11-13T15:00:00Z",
    updated_at: "2026-11-13T15:00:00Z",
    ...overrides,
  };
}

export const PARTNERS = [
  {
    id: "20000000-0000-4000-8000-000000000001",
    legal_name: "Constructora Andina S.A.S.",
    trade_name: "Andina",
    tax_id: "900123456",
    status: "ACTIVE",
    contact_name: "",
    contact_email: "contacto@andina.example.com",
    contact_phone: "",
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
  },
];

export function page<T>(items: T[], query: URLSearchParams) {
  const number = Number(query.get("page") ?? 1);
  const size = Number(query.get("page_size") ?? 25);
  return {
    items: items.slice((number - 1) * size, number * size),
    page: number,
    page_size: size,
    total: items.length,
    next: null,
    previous: null,
  };
}

export function apiError(code: string, message: string, details: unknown[] = []) {
  return { code, message, details, request_id: "req-1" };
}
