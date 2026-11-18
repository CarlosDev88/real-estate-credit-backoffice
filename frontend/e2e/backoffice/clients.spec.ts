import type { Locator, Page } from "@playwright/test";

import { expect, expectNoSeriousA11yViolations, test, useTheme, type Theme } from "./fixtures";

// Clientes (F4) contra el backend. Cambia los datos: crea un cliente nuevo (documento
// único por corrida), su oportunidad y una solicitud. Se corre en :3001 con
// `E2E_PORT=3001 pnpm exec playwright test clients.spec`.

/** Elige la primera opción de un `Select` (las opciones vienen de los catálogos de la API). */
async function chooseFirst(page: Page, scope: Locator | Page, label: string | RegExp) {
  await scope.getByLabel(label).click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option").first().click();
}

/** Diálogo de Ant Design que contiene ese título (el panel lateral también es un diálogo). */
function dialogWith(page: Page, title: string): Locator {
  return page.getByRole("dialog").filter({ has: page.getByText(title, { exact: true }) });
}

/**
 * Cierra los avisos abiertos: arriba a la derecha tapan las acciones del panel lateral
 * mientras duran (5 s).
 */
async function dismissToasts(page: Page) {
  // Al cerrarse se animan: se pide cerrar cada uno una vez y se espera a que se vayan.
  for (const close of await page.getByRole("button", { name: "Cerrar aviso" }).all()) {
    await close.click({ timeout: 2_000 }).catch(() => undefined);
  }
  await expect(page.locator(".ant-notification-notice")).toHaveCount(0, { timeout: 10_000 });
}

/** Número de documento solo de dígitos, válido para cualquier tipo, distinto en cada corrida. */
function uniqueDocument(): string {
  return `7${String(Date.now()).slice(-9)}`;
}

test.describe.configure({ mode: "serial" });

test("crea un cliente, ve el duplicado, crea la oportunidad y la solicitud", async ({ page }) => {
  test.setTimeout(120_000);
  const document = uniqueDocument();
  const lastNames = `Prueba ${document.slice(-4)}`;

  // 1. Crear el cliente: va a su detalle.
  await page.goto("/clientes");
  await page.getByRole("button", { name: "Nuevo cliente" }).click();
  await expect(page).toHaveURL(/\/clientes\/nuevo$/);
  const form = page.getByRole("form", { name: "Nuevo cliente" });
  await chooseFirst(page, form, "Tipo de documento");
  await form.getByLabel("Número de documento").fill(document);
  await form.getByLabel("Nombres").fill("Cliente E2E");
  await form.getByLabel("Apellidos").fill(lastNames);
  await form.getByLabel(/^Correo/).fill(`cliente.${document}@example.com`);
  await form.getByLabel(/^Teléfono/).fill("+57 300 123 4567");
  await form.getByRole("button", { name: "Crear cliente" }).click();

  await expect(page).toHaveURL(/\/clientes\/[0-9a-f-]{36}$/);
  const clientPath = new URL(page.url()).pathname;
  await expect(
    page.getByRole("heading", { name: `Cliente E2E ${lastNames}`, level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("Cliente creado")).toBeVisible();

  // 2. El mismo documento otra vez: el error va al campo, con enlace al existente.
  await page.goto("/clientes/nuevo");
  const again = page.getByRole("form", { name: "Nuevo cliente" });
  await chooseFirst(page, again, "Tipo de documento");
  await again.getByLabel("Número de documento").fill(document);
  await again.getByLabel("Nombres").fill("Otro");
  await again.getByLabel("Apellidos").fill("Duplicado");
  await again.getByRole("button", { name: "Crear cliente" }).click();
  const number = again.getByLabel("Número de documento");
  await expect(number).toHaveAttribute("aria-invalid", "true");
  await expect(number).toHaveAccessibleDescription(/Ya existe un cliente/);
  await expect(again.getByRole("link", { name: "Ver el cliente existente" })).toHaveAttribute(
    "href",
    clientPath,
  );
  await expect(page).toHaveURL(/\/clientes\/nuevo$/);

  // 3. Crear la oportunidad: abre su panel.
  await page.goto(`${clientPath}?tab=oportunidades`);
  await expect(page.getByText("Este cliente no tiene oportunidades")).toBeVisible();
  await page.getByRole("button", { name: "Nueva oportunidad" }).click();
  const newOpportunity = dialogWith(page, "Nueva oportunidad");
  await chooseFirst(page, newOpportunity, "Origen");
  await newOpportunity.getByRole("button", { name: "Crear oportunidad" }).click();
  await expect(page.getByText("Oportunidad creada")).toBeVisible();
  await dismissToasts(page);
  await expect(page).toHaveURL(/[?&]oportunidad=[0-9a-f-]{36}/);

  // La oportunidad nace sin asesor: el asesor de prueba se la asigna.
  const panel = dialogWith(page, "Oportunidad");
  await panel.getByRole("button", { name: "Asignarme" }).click();
  await expect(page.getByText("Te asignaste la oportunidad")).toBeVisible();
  await dismissToasts(page);
  await expect(panel.getByRole("button", { name: "Asignarme" })).toBeHidden();

  // 4. Crear la solicitud desde la oportunidad: llega al expediente nuevo.
  await panel.getByRole("button", { name: "Crear solicitud de crédito" }).click();
  const create = dialogWith(page, "Finalidad del crédito");
  await chooseFirst(page, create, "Finalidad del crédito");
  await create.getByRole("button", { name: "Crear solicitud" }).click();

  await expect(page).toHaveURL(/\/solicitudes\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("link", { name: "Volver a solicitudes" })).toBeVisible();
  await expect(page.getByText(`Cliente E2E ${lastNames}`).first()).toBeVisible();

  // 5. El cliente muestra la solicitud y la oportunidad convertida.
  await page.goto(`${clientPath}?tab=solicitudes`);
  await expect(
    page.getByRole("list", { name: "Solicitudes del cliente" }).getByRole("link"),
  ).toHaveCount(1);
});

const THEMES: Theme[] = ["light", "dark"];

for (const theme of THEMES) {
  test(`axe en el listado, el formulario y el detalle (${theme})`, async ({ page }) => {
    await useTheme(page, theme);

    await page.goto("/clientes");
    const link = page.locator("table tbody tr td:first-child a").first();
    await expect(link).toBeVisible();
    await expectNoSeriousA11yViolations(page, `listado ${theme}`);
    const detail = await link.getAttribute("href");

    await page.goto("/clientes/nuevo");
    await page.getByRole("button", { name: "Crear cliente" }).click();
    await expect(page.getByText("Escribe el número de documento.")).toBeVisible();
    await expectNoSeriousA11yViolations(page, `formulario ${theme}`);

    await page.goto(detail!);
    await expect(page.getByRole("heading", { name: "Datos del cliente" })).toBeVisible();
    await expectNoSeriousA11yViolations(page, `detalle ${theme}`);

    await page.goto(`${detail}?tab=oportunidades`);
    await expect(page.getByRole("heading", { name: "Oportunidades", level: 2 })).toBeVisible();
    await expect(page.getByRole("status", { name: "Cargando oportunidades" })).toBeHidden();
    await expectNoSeriousA11yViolations(page, `oportunidades ${theme}`);
  });
}
