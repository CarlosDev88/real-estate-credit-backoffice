import { existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { request, test as base, type Page } from "@playwright/test";

import { BASE_URL } from "../../playwright.config";

// Sesión del administrador para las pantallas de administración (F6). El usuario sale de
// `.env.local` (E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD; Playwright lo carga). Al empezar la
// corrida se renueva la sesión guardada (`/auth/refresh`); solo si no sirve se inicia sesión
// por la API: el login tiene límite de intentos (5 cada 15 min por correo).

const PORT = new URL(BASE_URL).port || "3000";
export const ADMIN_AUTH_FILE = `test-results/.auth/admin-${PORT}.json`;
export const NO_ADMIN =
  "Sin sesión del administrador: falta E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD en frontend/.env.local.";

/**
 * Renueva la sesión guardada (`POST /auth/refresh`, con su `X-CSRFToken`) sin gastar un
 * intento de login. `false` si no hay archivo o el refresh ya no sirve.
 */
async function refreshSaved(): Promise<boolean> {
  if (!existsSync(ADMIN_AUTH_FILE)) return false;
  const context = await request.newContext({ baseURL: BASE_URL, storageState: ADMIN_AUTH_FILE });
  try {
    const { cookies } = await context.storageState();
    const csrf = cookies.find((cookie) => cookie.name === "app_csrf")?.value ?? "";
    const response = await context.post("/api/v1/auth/refresh", {
      headers: { "X-CSRFToken": csrf, Referer: BASE_URL },
    });
    if (!response.ok()) return false;
    await context.storageState({ path: ADMIN_AUTH_FILE });
    return true;
  } finally {
    await context.dispose();
  }
}

async function loginAsAdmin(): Promise<string | null> {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) return null;
  if (await refreshSaved()) return ADMIN_AUTH_FILE;
  const context = await request.newContext({ baseURL: BASE_URL });
  const response = await context.post("/api/v1/auth/login", { data: { email, password } });
  if (!response.ok()) {
    const body = await response.text();
    await context.dispose();
    throw new Error(`Login del administrador: ${response.status()} ${body}`);
  }
  mkdirSync(dirname(ADMIN_AUTH_FILE), { recursive: true });
  await context.storageState({ path: ADMIN_AUTH_FILE });
  await context.dispose();
  return ADMIN_AUTH_FILE;
}

/**
 * Escritura en la API con la sesión de la página (cookies) y su `X-CSRFToken`, como hace
 * el front. Para preparar datos de prueba sin pasar por la pantalla.
 */
export async function apiWrite(
  page: Page,
  method: "POST" | "PATCH",
  path: string,
  data: unknown,
): Promise<unknown> {
  const cookies = await page.context().cookies(BASE_URL);
  const csrf = cookies.find((cookie) => cookie.name === "app_csrf")?.value ?? "";
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: { "X-CSRFToken": csrf, Referer: BASE_URL },
  });
  if (!response.ok())
    throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

/** Primer resultado de un listado (`items[0]`) o `null`. */
export async function firstItem<T>(page: Page, path: string): Promise<T | null> {
  const response = await page.request.get(path);
  if (!response.ok()) return null;
  return (((await response.json()) as { items: T[] }).items[0] ?? null) as T | null;
}

/** Nombre de los datos que crean las pruebas de administración (fácil de reconocer y borrar). */
export const E2E_PARTNER = {
  legal_name: "Constructora E2E Capturas S.A.S.",
  tax_id: "900999001-1",
};
export const E2E_PROJECT = "Proyecto E2E Capturas";

/**
 * Deja una constructora y un proyecto de prueba (si no existen ya), para que los paneles
 * tengan qué mostrar en una base sin datos de constructoras. No toca los datos existentes.
 */
export async function ensurePartnerAndProject(page: Page): Promise<void> {
  type Item = { id: string };
  let partner = await firstItem<Item>(page, `/api/v1/partners?search=900999001`);
  if (!partner) {
    partner = (await apiWrite(page, "POST", "/api/v1/partners", {
      ...E2E_PARTNER,
      trade_name: "E2E Capturas",
      contact_name: "Contacto de prueba",
      contact_email: "contacto.e2e@example.com",
    })) as Item;
  }
  const project = await firstItem<Item>(
    page,
    `/api/v1/projects?search=${encodeURIComponent(E2E_PROJECT)}`,
  );
  if (!project) {
    await apiWrite(page, "POST", "/api/v1/projects", {
      name: E2E_PROJECT,
      partner_id: partner.id,
      city_code: "05001",
      address: "Calle 10 # 43-20",
      description: "Datos de prueba de las capturas de administración.",
    });
  }
}

/** Pruebas con la sesión del administrador; sin usuario configurado, se saltan. */
export const adminTest = base.extend<object, { adminState: string | null }>({
  adminState: [
    // `provide` es el `use` de Playwright (con ese nombre, la regla de hooks de React lo marca).
    async ({}, provide) => {
      await provide(await loginAsAdmin());
    },
    { scope: "worker" },
  ],
  storageState: async ({ adminState }, provide, testInfo) => {
    if (!adminState) testInfo.skip(true, NO_ADMIN);
    await provide(adminState ?? undefined);
  },
});
