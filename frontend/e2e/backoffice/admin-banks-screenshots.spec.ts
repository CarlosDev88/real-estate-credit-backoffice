import type { Page } from "@playwright/test";

import { adminTest as test, hideDevOverlay, ensureProductAndRule } from "./admin-fixtures";
import { expect, expectNoSeriousA11yViolations, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` de `/admin/bancos` y de la página de un producto con sus reglas (F6,
// parte 3), con la sesión del administrador. No corren en la suite normal:
// `E2E_PORT=3002 E2E_SCREENSHOTS=1 node ./node_modules/@playwright/test/cli.js test admin-banks-screenshots --project=backoffice --no-deps`.
// Si falta, crea por la API "Producto E2E Capturas" (en el primer banco) con la regla en
// borrador "E2E_CAPTURAS_PLAZO" (`ensureProductAndRule`). La prueba de la regla no cambia
// datos; los demás modales se cancelan o se envían vacíos.

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
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: true });
}

const modalWith = (page: Page, title: string | RegExp) =>
  page.getByRole("dialog").filter({ has: page.locator(".ant-modal-title").getByText(title) });

async function cancel(page: Page, title: string | RegExp, button = "Cancelar") {
  const modal = modalWith(page, title);
  await modal.locator(".ant-modal-footer").getByRole("button", { name: button }).click();
  await expect(modal).toBeHidden();
}

for (const theme of THEMES) {
  test(`bancos y reglas en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    await hideDevOverlay(page);
    await page.goto("/admin/bancos");
    const productId = await ensureProductAndRule(page);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;
      const wide = size.width > 860;
      const axe = size.name === "1440";

      // ---------- bancos ----------
      await page.goto("/admin/bancos");
      await expect(page.getByRole("heading", { name: "Bancos", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando bancos" })).toBeHidden();
      await shoot(page, `admin-bancos-listado-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `bancos ${theme}`);

      const first = wide
        ? page.getByRole("table", { name: "Bancos" }).getByRole("row").nth(1)
        : page.getByRole("list", { name: "Bancos" }).getByRole("listitem").first();
      await first.getByRole("link").first().click();
      const panel = page.getByRole("dialog");
      await expect(panel.getByRole("heading", { name: "Productos" })).toBeVisible();
      await shoot(page, `admin-bancos-panel-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `panel banco ${theme}`);

      await panel.getByRole("button", { name: "Nuevo producto" }).click();
      await modalWith(page, "Nuevo producto")
        .getByRole("button", { name: "Crear producto" })
        .click();
      await expect(page.getByText("Escribe el código.")).toBeVisible();
      await shoot(page, `admin-bancos-nuevo-producto-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nuevo producto ${theme}`);
      await cancel(page, "Nuevo producto");

      // ---------- producto y reglas ----------
      await page.goto(`/admin/bancos/productos/${productId}`);
      await expect(page.getByRole("heading", { name: "Reglas", level: 2 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando reglas" })).toBeHidden();
      await shoot(page, `admin-producto-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `producto ${theme}`);

      await page.getByRole("button", { name: "Cambiar finalidades" }).click();
      await expect(
        modalWith(page, "Finalidades del producto").getByRole("checkbox").first(),
      ).toBeVisible();
      await shoot(page, `admin-producto-finalidades-${tag}`);
      await cancel(page, "Finalidades del producto");

      await page.getByRole("button", { name: "Nueva regla" }).click();
      await expect(modalWith(page, "Nueva regla").getByText(/Se lee:/)).toBeVisible();
      await shoot(page, `admin-regla-nueva-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nueva regla ${theme}`);
      await cancel(page, "Nueva regla");

      const rule = page.getByRole("button", { name: /^E2E_CAPTURAS_PLAZO/ }).first();
      await rule.click();
      const rulePanel = page.getByRole("dialog");
      await expect(rulePanel.getByRole("list", { name: "Versiones" })).toBeVisible();
      await shoot(page, `admin-regla-panel-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `panel regla ${theme}`);

      await rulePanel.getByRole("button", { name: "Probar" }).click();
      const testModal = modalWith(page, /^Probar E2E_CAPTURAS_PLAZO/);
      await testModal.getByLabel("Contexto (JSON)").fill('{"financing": {"term_months": 300}}');
      await testModal.getByRole("button", { name: "Probar" }).click();
      await expect(testModal.getByRole("list", { name: "Resultados de la prueba" })).toBeVisible();
      await shoot(page, `admin-regla-prueba-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `probar regla ${theme}`);
      await cancel(page, /^Probar E2E_CAPTURAS_PLAZO/, "Cerrar");
    }
  });
}
