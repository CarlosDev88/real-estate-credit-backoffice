import type { Locator, Page } from "@playwright/test";

import { expect, test, useTheme, type Theme } from "./fixtures";

// Capturas de la pestaña Radicación y sus modales. No corren en la suite normal:
// `E2E_PORT=3001 E2E_SCREENSHOTS=1 pnpm exec playwright test filings-screenshots`.
// Salen en `test-results/screenshots/` (no se versiona). No cambian datos: los modales se
// abren y se cancelan.

const OUT = "test-results/screenshots";
const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1280", width: 1280, height: 800 },
  { name: "390", width: 390, height: 844 },
];
const THEMES: Theme[] = ["light", "dark"];

test.skip(!process.env.E2E_SCREENSHOTS, "Capturas: corre con E2E_SCREENSHOTS=1.");
test.describe.configure({ timeout: 300_000 });

async function shoot(page: Page, file: string) {
  // Espera a que terminen las animaciones de Ant Design (modales, pestañas).
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: true });
}

function panel(page: Page): Locator {
  return page.getByRole("tabpanel", { name: "Radicación" });
}

/**
 * Ruta del primer resultado del listado con esos filtros (a 1440 px, la tabla) y, si se
 * pasa, con ese estado (etiqueta de la API). No se fijan códigos de solicitud.
 */
async function firstPath(page: Page, search: string, status?: string): Promise<string | null> {
  const size = page.viewportSize();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/solicitudes${search}`);
  const all = page.getByRole("tab", { name: /^Todas/ });
  await expect(all).toBeVisible();
  // Sin resultados no se salta la prueba (como haría `openListOrSkip`): solo esa captura.
  const count = Number((await all.textContent())?.replace(/\D/g, "") || 0);
  let path: string | null = null;
  if (count > 0) {
    const rows = page.locator("table tbody tr");
    await rows.first().waitFor();
    const row = status
      ? rows.filter({ has: page.getByText(status, { exact: true }) }).first()
      : rows.first();
    if ((await row.count()) > 0) path = await row.locator("td:first-child a").getAttribute("href");
  }
  if (size) await page.setViewportSize(size);
  return path;
}

async function cancel(page: Page) {
  await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
}

/** Abre "Registrar respuesta", elige "Devuelta" y marca el primer documento. */
async function openReturnedForm(page: Page): Promise<boolean> {
  const record = panel(page).getByRole("button", { name: "Registrar respuesta" });
  if ((await record.count()) === 0) return false;
  await record.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Tipo de respuesta").click();
  await page
    .locator(".ant-select-dropdown:visible .ant-select-item-option")
    .filter({ hasText: /^Devuelta$/ })
    .click();
  const box = dialog.getByRole("checkbox").first();
  if ((await box.count()) > 0) await box.check();
  return true;
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    const tag = `${size.name}-${theme}`;

    test(`radicación ${tag}`, async ({ page }) => {
      await useTheme(page, theme);
      await page.setViewportSize({ width: size.width, height: size.height });

      // En el banco: radicaciones, línea de tiempo y modal de respuesta (devolución).
      const inBank = await firstPath(page, "?quick_filter=bank");
      if (inBank) {
        await page.goto(`${inBank}?tab=radicacion`);
        await expect(panel(page).getByRole("heading", { name: /^#\d+/ }).first()).toBeVisible();
        await expect(panel(page).getByText("Respuestas del banco").first()).toBeVisible();
        await shoot(page, `filings-en-banco-${tag}`);
        if (await openReturnedForm(page)) {
          await shoot(page, `filings-modal-respuesta-${tag}`);
          await cancel(page);
        }
      }

      // Observada por el banco y aprobada (casos radicados de la demo, si están).
      const observed = await firstPath(page, "?quick_filter=bank", "Observación del banco");
      if (observed) {
        await page.goto(`${observed}?tab=radicacion`);
        await expect(panel(page).getByText(/^El banco observó/)).toBeVisible();
        await shoot(page, `filings-observada-${tag}`);
      }
      const approved = await firstPath(page, "?quick_filter=bank", "Aprobada");
      if (approved) {
        await page.goto(`${approved}?tab=radicacion`);
        await expect(panel(page).getByText("El banco aprobó el crédito")).toBeVisible();
        await shoot(page, `filings-aprobada-${tag}`);
      }

      // Lista para radicar: panel de entrega, resultado del paquete y modal de radicación.
      const ready = await firstPath(page, "?quick_filter=ready");
      if (ready) {
        await page.goto(`${ready}?tab=radicacion`);
        await expect(panel(page).getByRole("heading", { name: "Entregar al banco" })).toBeVisible();
        await shoot(page, `filings-entregar-${tag}`);
        await panel(page).getByRole("button", { name: "Preparar paquete" }).click();
        const done = panel(page).getByText("Paquete listo:");
        const failed = panel(page).getByText(/^No se pudo (preparar|armar) el paquete$/);
        await expect(done.or(failed)).toBeVisible({ timeout: 90_000 });
        await shoot(page, `filings-paquete-${tag}`);
        if (await done.isVisible()) {
          await panel(page).getByRole("button", { name: "Registrar radicación" }).click();
          await expect(page.getByRole("dialog", { name: "Registrar radicación" })).toBeVisible();
          await shoot(page, `filings-modal-radicacion-${tag}`);
          await cancel(page);
        }
      }
    });
  }
}
