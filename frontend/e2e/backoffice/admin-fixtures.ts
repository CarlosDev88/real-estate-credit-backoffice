import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { request, test as base, type Page } from "@playwright/test";

import { AUTH_FILE, BASE_URL } from "../../playwright.config";

// Sesión del administrador para las pantallas de administración (F6). El usuario sale de
// `.env.local` (E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD; Playwright lo carga). Al empezar la
// corrida se renueva la sesión guardada (`/auth/refresh`); solo si no sirve se inicia sesión
// por la API: el login tiene límite de intentos (5 cada 15 min por correo).

const PORT = new URL(BASE_URL).port || "3000";
export const ADMIN_AUTH_FILE = `test-results/.auth/admin-${PORT}.json`;
export const NO_ADMIN =
  "Sin sesión del administrador: falta E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD en frontend/.env.local.";

/**
 * Renueva una sesión guardada (`POST /auth/refresh`, con su `X-CSRFToken`) sin gastar un
 * intento de login. `false` si no hay archivo o el refresh ya no sirve.
 */
async function refreshSaved(file: string): Promise<boolean> {
  if (!existsSync(file)) return false;
  const context = await request.newContext({ baseURL: BASE_URL, storageState: file });
  try {
    const { cookies } = await context.storageState();
    const csrf = cookies.find((cookie) => cookie.name === "app_csrf")?.value ?? "";
    const response = await context.post("/api/v1/auth/refresh", {
      headers: { "X-CSRFToken": csrf, Referer: BASE_URL },
    });
    if (!response.ok()) return false;
    await context.storageState({ path: file });
    return true;
  } finally {
    await context.dispose();
  }
}

/**
 * Sesión de un usuario en `file`: renueva la guardada y, si no sirve, inicia sesión por la
 * API (un intento de login). Devuelve el archivo para `storageState`.
 */
export async function ensureSession(
  file: string,
  email: string,
  password: string,
): Promise<string> {
  if (await refreshSaved(file)) return file;
  const context = await request.newContext({ baseURL: BASE_URL });
  try {
    const response = await context.post("/api/v1/auth/login", { data: { email, password } });
    if (!response.ok()) {
      throw new Error(`Login de ${email}: ${response.status()} ${await response.text()}`);
    }
    mkdirSync(dirname(file), { recursive: true });
    await context.storageState({ path: file });
    return file;
  } finally {
    await context.dispose();
  }
}

async function loginAsAdmin(): Promise<string | null> {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) return null;
  return ensureSession(ADMIN_AUTH_FILE, email, password);
}

/** Sesión del asesor de `.env.local` (la misma que guarda `auth.setup`), o `null`. */
export async function advisorSession(): Promise<string | null> {
  const email = process.env.E2E_USER_EMAIL;
  const password = process.env.E2E_USER_PASSWORD;
  if (!email || !password) return null;
  return ensureSession(AUTH_FILE, email, password);
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

export const E2E_PRODUCT = { code: "E2E_CAPTURAS", name: "Producto E2E Capturas" };
export const E2E_RULE = "E2E_CAPTURAS_PLAZO";

/**
 * Deja un producto de prueba (en el primer banco) con una regla en borrador, si no existen,
 * para las capturas de bancos y reglas. Devuelve el id del producto.
 */
export async function ensureProductAndRule(page: Page): Promise<string> {
  type Item = { id: string };
  let product = await firstItem<Item>(page, `/api/v1/bank-products?search=${E2E_PRODUCT.code}`);
  if (!product) {
    const bank = await firstItem<Item>(page, "/api/v1/banks?ordering=name");
    if (!bank) throw new Error("La base no tiene bancos.");
    const types = (await (await page.request.get("/api/v1/metadata/bootstrap")).json()) as {
      catalogs: Record<string, { code: string }[]>;
    };
    product = (await apiWrite(page, "POST", "/api/v1/bank-products", {
      ...E2E_PRODUCT,
      bank_id: bank.id,
      product_type_code: types.catalogs.bank_product_type?.[0]?.code,
      min_term_months: 60,
      max_term_months: 360,
    })) as Item;
  }
  const rule = await firstItem<Item>(
    page,
    `/api/v1/bank-policy-rules?bank_product_id=${product.id}&code=${E2E_RULE}`,
  );
  if (!rule) {
    await apiWrite(page, "POST", "/api/v1/bank-policy-rules", {
      bank_product_id: product.id,
      code: E2E_RULE,
      severity: "WARNING",
      message: "Datos de prueba de las capturas: plazo de hasta 20 años.",
      condition: { operator: "lte", left: { field: "financing.term_months" }, right: 240 },
    });
  }
  return product.id;
}

/**
 * Oculta el botón flotante de `next dev` (solo existe en desarrollo): en 390 px tapa los
 * botones del pie de los paneles y sale en las capturas.
 */
export async function hideDevOverlay(page: Page): Promise<void> {
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = "nextjs-portal { display: none !important; }";
      document.head.append(style);
    });
  });
}

/** Contenedor del backend local; su correo sale por consola (`EMAIL_BACKEND` de `local.py`). */
const BACKEND_CONTAINER = process.env.E2E_BACKEND_CONTAINER || "mvp-credit-backend-backend-1";

/**
 * Token de la última invitación enviada a `email`, leído del correo que el backend local
 * imprime en su log (`docker logs`). `null` si todavía no aparece.
 */
export function invitationToken(email: string): string | null {
  let logs = "";
  try {
    logs = execFileSync("docker", ["logs", "--since", "10m", BACKEND_CONTAINER], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (error) {
    const out = error as { stdout?: string; stderr?: string };
    logs = `${out.stdout ?? ""}${out.stderr ?? ""}`;
  }
  const start = logs.lastIndexOf(`To: ${email}`);
  if (start < 0) return null;
  const match = /aceptar-invitacion\?token=([A-Za-z0-9_\-]+)/.exec(logs.slice(start));
  return match?.[1] ?? null;
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
