import { screen, waitFor, within } from "@testing-library/react";
import { expect, vi } from "vitest";

// Ayudas de las pruebas de administración (no es código de la app).

/** Router de prueba: `replace` escribe en la URL de jsdom y avisa a `useSearchParams`. */
export function makeTestRouter() {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
    notify,
    push: vi.fn(),
    replace: vi.fn((href: string) => {
      window.history.replaceState(null, "", href);
      notify();
    }),
  };
}

export function setMobile(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matches && query.includes("max-width: 860px"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

/**
 * Diálogo por su título. En las pruebas, Ant Design le da `id="test-id"` a todos sus
 * componentes, así que el nombre accesible (`aria-labelledby`) no sirve para buscarlo.
 */
export async function dialog(name: string): Promise<HTMLElement> {
  const find = () =>
    screen
      .queryAllByRole("dialog")
      .find((d) =>
        within(d).queryByText(name, { selector: ".ant-modal-title, .ant-drawer-title, h2" }),
      );
  await waitFor(() => expect(find()).toBeDefined());
  return find()!;
}

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

const item = (code: string, label: string, order: number, parent_code: string | null = null) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active: true,
  parent_id: null,
  parent_code,
  metadata: {},
});

export const ADMIN_BOOTSTRAP = {
  metadata_version: 1,
  actor: "ADMIN",
  permissions: [],
  catalogs: {
    project_status: [
      item("DRAFT", "Borrador", 1),
      item("PENDING_REVIEW", "En validación", 2),
      item("ACTIVE", "Activo", 3),
      item("ARCHIVED", "Archivado", 4),
    ],
    department: [item("05", "Antioquia", 1), item("11", "Bogotá D.C.", 2)],
  },
  on_demand_catalogs: ["municipality"],
  features: {},
};

export const MUNICIPALITIES = {
  catalog: "municipality",
  name: "Municipios",
  version: 1,
  items: [item("05001", "Medellín", 1, "05"), item("11001", "Bogotá", 2, "11")],
};

export function meWith(permissions: string[], partnerId: string | null = null) {
  return {
    id: "00000000-0000-4000-8000-000000000999",
    name: "Persona de prueba",
    email: "persona@example.com",
    role: partnerId ? "CONSTRUCTION_PARTNER" : "ADMIN",
    role_label: partnerId ? "Constructora" : "Administrador",
    roles: [partnerId ? "CONSTRUCTION_PARTNER" : "ADMIN"],
    permissions,
    scope: { assigned_applications_only: false, partner_id: partnerId },
  };
}

/** Registra el cuerpo de cada escritura (método, ruta y JSON). */
export interface WriteCall {
  method: string;
  path: string;
  body: unknown;
}
export async function recordWrite(calls: WriteCall[], request: Request) {
  const text = await request.clone().text();
  calls.push({
    method: request.method,
    path: new URL(request.url).pathname,
    body: text ? JSON.parse(text) : null,
  });
}
