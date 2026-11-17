import type { Page } from "@playwright/test";

import { expect, expectNoSeriousA11yViolations, test, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` del listado, el formulario y el detalle de clientes (F4). No corren en
// la suite normal: `E2E_PORT=3001 E2E_SCREENSHOTS=1 pnpm exec playwright test clients-screenshots`.
// Salen en `test-results/screenshots/` (no se versiona). No cambian datos: el formulario se
// envía vacío (lo frena la validación del front) y la edición no se guarda.

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

/** Ruta del detalle del primer cliente del listado, o `null` si no hay clientes. */
async function firstClientPath(page: Page): Promise<string | null> {
  const size = page.viewportSize();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/clientes");
  await expect(page.getByRole("heading", { name: "Clientes", level: 1 })).toBeVisible();
  const link = page.locator("table tbody tr td:first-child a").first();
  const empty = page.getByText("Todavía no hay clientes");
  await expect(link.or(empty)).toBeVisible();
  const path = (await link.count()) > 0 ? await link.getAttribute("href") : null;
  if (size) await page.setViewportSize(size);
  return path;
}

for (const theme of THEMES) {
  test(`clientes en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    const detail = await firstClientPath(page);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;

      await page.goto("/clientes");
      await expect(page.getByRole("region", { name: "Listado de clientes" })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando clientes" })).toBeHidden();
      await shoot(page, `clientes-listado-${tag}`);
      if (size.name === "1440") await expectNoSeriousA11yViolations(page, `listado ${theme}`);

      await page.goto("/clientes?search=zzzz-sin-resultados");
      await expect(page.getByText("No hay clientes con estos filtros")).toBeVisible();
      await shoot(page, `clientes-vacio-${tag}`);

      await page.goto("/clientes/nuevo");
      await expect(page.getByRole("heading", { name: "Nuevo cliente", level: 1 })).toBeVisible();
      await shoot(page, `clientes-nuevo-${tag}`);
      await page.getByRole("button", { name: "Crear cliente" }).click();
      await expect(page.getByText("Escribe el número de documento.")).toBeVisible();
      await shoot(page, `clientes-nuevo-errores-${tag}`);
      if (size.name === "1440") await expectNoSeriousA11yViolations(page, `formulario ${theme}`);

      if (detail) {
        await page.goto(detail);
        await expect(page.getByRole("heading", { name: "Datos del cliente" })).toBeVisible();
        await shoot(page, `clientes-detalle-${tag}`);
        if (size.name === "1440") await expectNoSeriousA11yViolations(page, `detalle ${theme}`);

        await page.goto(`${detail}/editar`);
        await expect(page.getByRole("heading", { name: "Editar cliente", level: 1 })).toBeVisible();
        await shoot(page, `clientes-editar-${tag}`);
      }
    }
  });
}
