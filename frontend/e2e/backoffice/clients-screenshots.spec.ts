import type { Page } from "@playwright/test";

import { expect, expectNoSeriousA11yViolations, test, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` del listado, el formulario, el detalle (pestañas, panel de la
// oportunidad y "Crear solicitud") de clientes (F4). No corren en
// la suite normal: `E2E_PORT=3001 E2E_SCREENSHOTS=1 pnpm exec playwright test clients-screenshots`.
// Salen en `test-results/screenshots/` (no se versiona). No cambian datos: el formulario se
// envía vacío (lo frena la validación del front), la edición no se guarda y el modal de
// "Crear solicitud" se cancela.

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

/**
 * Cliente con oportunidades: el titular de la primera solicitud del asesor (toda
 * solicitud nace de una oportunidad). `null` si el asesor no tiene solicitudes.
 */
async function clientWithOpportunities(page: Page): Promise<string | null> {
  const response = await page.request.get("/api/v1/applications?page_size=1");
  if (!response.ok()) return null;
  const body = (await response.json()) as { items: { applicant: { id: string } }[] };
  const id = body.items[0]?.applicant.id;
  return id ? `/clientes/${id}` : null;
}

for (const theme of THEMES) {
  test(`clientes en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    const detail = await firstClientPath(page);
    const withOpportunities = await clientWithOpportunities(page);

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

        await page.goto(`${detail}?tab=solicitudes`);
        await expect(page.getByRole("tabpanel", { name: "Solicitudes" })).toBeVisible();
        await expect(page.getByRole("status", { name: "Cargando solicitudes" })).toBeHidden();
        await shoot(page, `clientes-detalle-solicitudes-${tag}`);

        await page.goto(`${detail}/editar`);
        await expect(page.getByRole("heading", { name: "Editar cliente", level: 1 })).toBeVisible();
        await shoot(page, `clientes-editar-${tag}`);
      }

      if (withOpportunities) {
        await page.goto(`${withOpportunities}?tab=oportunidades`);
        const list = page.getByRole("list", { name: "Oportunidades" });
        await expect(list).toBeVisible();
        await shoot(page, `clientes-oportunidades-${tag}`);
        if (size.name === "1440")
          await expectNoSeriousA11yViolations(page, `oportunidades ${theme}`);

        await list.getByRole("button").first().click();
        const panel = page.getByRole("dialog");
        await expect(panel.getByText("Origen", { exact: true })).toBeVisible();
        await shoot(page, `clientes-oportunidad-panel-${tag}`);
        if (size.name === "1440") await expectNoSeriousA11yViolations(page, `panel ${theme}`);

        const create = panel.getByRole("button", { name: "Crear solicitud de crédito" });
        if (await create.isVisible()) {
          await create.click();
          const modal = page.getByRole("dialog").filter({ hasText: "Finalidad del crédito" });
          await expect(modal).toBeVisible();
          await shoot(page, `clientes-crear-solicitud-${tag}`);
          if (size.name === "1440")
            await expectNoSeriousA11yViolations(page, `crear solicitud ${theme}`);
          await modal.getByRole("button", { name: "Cancelar" }).click();
          await expect(modal).toBeHidden();
        }
      }

      await page.goto("/clientes?nueva_solicitud=1");
      await expect(page.getByText("Elige el cliente y su oportunidad")).toBeVisible();
      await shoot(page, `clientes-nueva-solicitud-${tag}`);

      await page.goto("/solicitudes");
      await expect(page.getByRole("button", { name: "Nueva solicitud" })).toBeVisible();
      await shoot(page, `solicitudes-nueva-${tag}`);
    }
  });
}
