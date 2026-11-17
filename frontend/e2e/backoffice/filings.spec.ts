import type { Locator, Page } from "@playwright/test";

import {
  expect,
  expectNoSeriousA11yViolations,
  openListOrSkip,
  rowLinks,
  test,
  useTheme,
  type Theme,
} from "./fixtures";

// Radicación (F3) contra el backend con los datos de demo. Cambia los datos: radica una
// solicitud de "Listas para radicar" y le registra respuestas. Se corre en :3001 con
// `E2E_PORT=3001 pnpm exec playwright test filings`.

const NO_READY =
  "Ninguna solicitud de 'Listas para radicar' arma el paquete (la demo ya se radicó o le falta un documento aprobado). Vuelve a sembrar la demo para repetir esta prueba.";
const noneWith = (label: string) =>
  `No hay solicitudes "${label}" en 'En el banco' para el usuario de prueba (siembra los casos radicados de la demo con --advisor-email).`;
/** Etiquetas de estado de la API que buscan las pruebas (no se fijan códigos de solicitud). */
const OBSERVED = "Observación del banco";
const APPROVED = "Aprobada";
const FILED = "Radicada";

function filingTab(page: Page): Locator {
  return page.getByRole("tabpanel", { name: "Radicación" });
}

/** Primera solicitud de "En el banco" con ese estado (etiqueta de la API), o `null`. */
async function inBankWithStatus(page: Page, label: string): Promise<string | null> {
  await openListOrSkip(page, "?quick_filter=bank&page_size=50");
  await page.locator("table tbody tr").first().waitFor();
  const row = page
    .locator("table tbody tr")
    .filter({ has: page.getByText(label, { exact: true }) })
    .first();
  if ((await row.count()) === 0) return null;
  return row.locator("td:first-child a").getAttribute("href");
}

/**
 * Abre las solicitudes listas para radicar y pide el paquete de cada una hasta que una lo
 * arme (en la demo, alguna puede tener un documento que otra prueba rechazó: la API
 * responde `APPLICATION_NOT_READY` y la pestaña lo muestra). Queda en esa pestaña con el
 * paquete listo. `null` si ninguna sirve.
 */
async function readyWithPackage(page: Page): Promise<string | null> {
  await openListOrSkip(page, "?quick_filter=ready&page_size=50");
  const tab = page.getByRole("tab", { name: /^Listas para radicar/ });
  const count = Number((await tab.textContent())?.replace(/\D/g, "") || 0);
  if (count === 0) return null;
  const paths = await rowLinks(page);
  for (const path of paths) {
    await page.goto(`${path}?tab=radicacion`);
    const panel = filingTab(page);
    await expect(panel.getByRole("heading", { name: "Entregar al banco" })).toBeVisible();
    await panel.getByRole("button", { name: "Preparar paquete" }).click();
    // Lo arma el worker; la pestaña consulta cada 3 s.
    const ready = panel.getByText("Paquete listo:");
    const failed = panel.getByText(/^No se pudo (preparar|armar) el paquete$/);
    await expect(ready.or(failed)).toBeVisible({ timeout: 90_000 });
    if (await ready.isVisible()) return path;
  }
  return null;
}

const NO_FILED =
  "No hay solicitudes radicadas sin respuestas en 'En el banco'. Corre antes la prueba que radica o vuelve a sembrar la demo.";

/** Primera solicitud radicada (sin respuestas todavía), o `null`. */
async function filedApplication(page: Page): Promise<string | null> {
  return inBankWithStatus(page, FILED);
}

const NO_IN_BANK = "No hay solicitudes en 'En el banco' para el usuario de prueba.";

/** Primera solicitud de "En el banco" (radicada o con respuestas), o `null`. */
async function firstInBank(page: Page): Promise<string | null> {
  await openListOrSkip(page, "?quick_filter=bank");
  const links = await rowLinks(page).catch(() => [] as string[]);
  return links[0] ?? null;
}

/** Elige la primera opción de un `Select` del modal (las opciones vienen de la API). */
async function chooseFirst(page: Page, dialog: Locator, label: string | RegExp) {
  await dialog.getByLabel(label).click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option").first().click();
}

async function chooseOption(page: Page, dialog: Locator, label: string | RegExp, option: string) {
  await dialog.getByLabel(label).click();
  await page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: new RegExp(`^${option}$`) })
    .click();
}

async function recordResponse(page: Page, type: string) {
  const latest = filingTab(page)
    .locator("article")
    .filter({ has: page.getByRole("button", { name: "Registrar respuesta" }) });
  await latest.getByRole("button", { name: "Registrar respuesta" }).click();
  const dialog = page.getByRole("dialog");
  await chooseOption(page, dialog, "Tipo de respuesta", type);
  await dialog.getByRole("button", { name: "Registrar respuesta" }).click();
  await expect(page.getByText("Respuesta registrada")).toBeVisible();
  // Paso opcional de la evidencia.
  const evidence = page.getByRole("dialog", { name: "Adjuntar evidencia" });
  await expect(evidence).toBeVisible();
  await evidence.getByRole("button", { name: "Ahora no" }).click();
  await expect(evidence).toBeHidden();
}

// Corren en orden (`workers: 1`); sin `serial`, una prueba saltada no arrastra a las demás.
test.describe.configure({ timeout: 180_000 });

test.describe("radicación", () => {
  test("prepara el paquete, descarga el ZIP y radica", async ({ page }) => {
    const path = await readyWithPackage(page);
    test.skip(!path, NO_READY);
    const panel = filingTab(page);
    const download = page.waitForEvent("download");
    await panel.getByRole("button", { name: "Descargar ZIP" }).click();
    expect((await download).suggestedFilename()).toMatch(/\.zip$/);

    await panel.getByRole("button", { name: "Registrar radicación" }).click();
    const dialog = page.getByRole("dialog", { name: "Registrar radicación" });
    await chooseFirst(page, dialog, "Canal");
    await dialog.getByLabel(/Referencia del banco/).fill(`E2E-${Date.now()}`);
    await dialog.getByLabel(/Comentario/).fill("Radicación de prueba E2E.");
    await dialog.getByRole("button", { name: "Registrar radicación" }).click();
    await expect(page.getByText("Radicación registrada")).toBeVisible();
    await expect(dialog).toBeHidden();

    // La solicitud pasa a radicada y la radicación queda en la lista.
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Radicada");
    await expect(panel.getByRole("heading", { name: /^#\d+/ }).first()).toBeVisible();
    await expect(panel.getByRole("heading", { name: "Entregar al banco" })).toHaveCount(0);
  });

  test("registra 'Recibida' y 'En análisis' en una solicitud radicada", async ({ page }) => {
    const path = await filedApplication(page);
    test.skip(!path, NO_FILED);
    await page.goto(`${path!}?tab=radicacion`);
    const panel = filingTab(page);
    await recordResponse(page, "Recibida");
    await expect(panel.getByText("Recibida", { exact: true }).first()).toBeVisible();
    await recordResponse(page, "En análisis");
    await expect(panel.getByText("En análisis", { exact: true }).first()).toBeVisible();
  });

  test("observada por el banco: banner y enlace al documento", async ({ page }) => {
    const path = await inBankWithStatus(page, OBSERVED);
    test.skip(!path, noneWith(OBSERVED));
    await page.goto(`${path!}?tab=radicacion`);
    const panel = filingTab(page);
    await expect(panel.getByText(/^El banco observó \d+ documentos?$/)).toBeVisible();
    await expect(panel.getByText("Documentos observados:")).toBeVisible();

    // El enlace lleva al documento en la pestaña Documentos.
    await panel.getByRole("alert").getByRole("button").first().click();
    await expect(page).toHaveURL(/tab=documentos&slot=/);
  });

  test("aprobada: banner y monto aprobado", async ({ page }) => {
    const path = await inBankWithStatus(page, APPROVED);
    test.skip(!path, noneWith(APPROVED));
    await page.goto(`${path!}?tab=radicacion`);
    const panel = filingTab(page);
    await expect(panel.getByText("El banco aprobó el crédito")).toBeVisible();
    await expect(panel.getByText("Monto aprobado:")).toBeVisible();
  });

  for (const theme of ["light", "dark"] as Theme[]) {
    test(`axe sin violaciones serias en la pestaña y los modales (${theme})`, async ({ page }) => {
      await useTheme(page, theme);
      const path = await firstInBank(page);
      test.skip(!path, NO_IN_BANK);
      await page.goto(`${path!}?tab=radicacion`);
      const panel = filingTab(page);
      await expect(panel.getByRole("heading", { name: /^#\d+/ }).first()).toBeVisible();
      await expect(panel.getByText("Respuestas del banco").first()).toBeVisible();
      await page.waitForTimeout(500);
      await expectNoSeriousA11yViolations(page, `radicación (${theme})`);

      const record = panel.getByRole("button", { name: "Registrar respuesta" });
      if ((await record.count()) > 0) {
        await record.click();
        const dialog = page.getByRole("dialog");
        await chooseOption(page, dialog, "Tipo de respuesta", "Devuelta");
        await page.waitForTimeout(500);
        await expectNoSeriousA11yViolations(page, `modal de respuesta (${theme})`);
        await dialog.getByRole("button", { name: "Cancelar" }).click();
        await expect(dialog).toBeHidden();
      }

      const edit = panel.getByRole("button", { name: /Corregir referencia o comentario/ }).first();
      if ((await edit.count()) > 0) {
        await edit.click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await page.waitForTimeout(500);
        await expectNoSeriousA11yViolations(page, `modal de corrección (${theme})`);
        await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
      }
    });
  }

  for (const theme of ["light", "dark"] as Theme[]) {
    test(`axe en 'Entregar al banco' y el modal de radicación (${theme})`, async ({ page }) => {
      await useTheme(page, theme);
      // El paquete se pide pero no se radica: la solicitud no cambia.
      const path = await readyWithPackage(page);
      test.skip(!path, NO_READY);
      const panel = filingTab(page);
      await expectNoSeriousA11yViolations(page, `entregar al banco, paquete listo (${theme})`);
      await panel.getByRole("button", { name: "Registrar radicación" }).click();
      await expect(page.getByRole("dialog", { name: "Registrar radicación" })).toBeVisible();
      await page.waitForTimeout(500);
      await expectNoSeriousA11yViolations(page, `modal de radicación (${theme})`);
      await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
    });
  }
});
