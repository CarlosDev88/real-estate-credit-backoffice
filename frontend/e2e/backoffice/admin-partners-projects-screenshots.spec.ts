import type { Page } from "@playwright/test";

import { adminTest as test, hideDevOverlay, ensurePartnerAndProject } from "./admin-fixtures";
import { expect, expectNoSeriousA11yViolations, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` de `/admin/constructoras` y `/proyectos` (F6, parte 2), con la sesión del
// administrador. No corren en la suite normal:
// `E2E_PORT=3002 E2E_SCREENSHOTS=1 node ./node_modules/@playwright/test/cli.js test admin-partners-projects-screenshots --project=backoffice --no-deps`.
// Si la base no tiene constructoras ni proyectos, crea uno de cada uno con nombre "E2E Capturas"
// (`ensurePartnerAndProject`); fuera de eso no cambian datos: los modales se cancelan y los
// formularios se envían vacíos.

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

/** Modal con ese título (no el panel lateral, que tiene botones con el mismo texto). */
const modalWith = (page: Page, title: string) =>
  page
    .getByRole("dialog")
    .filter({ has: page.locator(".ant-modal-title").getByText(title, { exact: true }) });

/** Abre el panel de la primera fila (tabla o tarjeta). `false` si el listado está vacío. */
async function openFirst(page: Page, name: string, wide: boolean): Promise<boolean> {
  const first = wide
    ? page.getByRole("table", { name }).getByRole("row").nth(1)
    : page.getByRole("list", { name }).getByRole("listitem").first();
  if ((await first.count()) === 0) return false;
  await first.getByRole("link").first().click();
  return true;
}

async function cancel(page: Page, title: string) {
  const modal = modalWith(page, title);
  await modal.getByRole("button", { name: "Cancelar" }).click();
  await expect(modal).toBeHidden();
}

for (const theme of THEMES) {
  test(`constructoras y proyectos en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    await hideDevOverlay(page);
    await page.goto("/proyectos");
    await ensurePartnerAndProject(page);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;
      const wide = size.width > 860;
      const axe = size.name === "1440";

      // ---------- constructoras ----------
      await page.goto("/admin/constructoras");
      await expect(page.getByRole("heading", { name: "Constructoras", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando constructoras" })).toBeHidden();
      await shoot(page, `admin-constructoras-listado-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `constructoras ${theme}`);

      await page.getByRole("button", { name: "Nueva constructora" }).click();
      await modalWith(page, "Nueva constructora")
        .getByRole("button", { name: "Crear constructora" })
        .click();
      await expect(page.getByText("Escribe la razón social.")).toBeVisible();
      await shoot(page, `admin-constructoras-nueva-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nueva constructora ${theme}`);
      await cancel(page, "Nueva constructora");

      if (await openFirst(page, "Constructoras", wide)) {
        const panel = page.getByRole("dialog");
        await expect(panel.getByText("Miembros activos")).toBeVisible();
        await expect(panel.getByRole("status", { name: "Cargando miembros" })).toBeHidden();
        await shoot(page, `admin-constructoras-panel-${tag}`);
        if (axe) await expectNoSeriousA11yViolations(page, `panel constructora ${theme}`);

        const add = panel.getByRole("button", { name: "Agregar miembro" });
        if (await add.isVisible()) {
          await add.click();
          await modalWith(page, "Agregar miembro")
            .getByRole("radio", { name: "Agregar un usuario existente" })
            .check();
          await shoot(page, `admin-constructoras-miembro-${tag}`);
          if (axe) await expectNoSeriousA11yViolations(page, `agregar miembro ${theme}`);
          await cancel(page, "Agregar miembro");
        }

        const deactivate = panel.getByRole("button", { name: "Desactivar" });
        if (await deactivate.isVisible()) {
          await deactivate.click();
          const modal = modalWith(page, "Desactivar constructora");
          await modal.getByRole("button", { name: "Desactivar" }).click();
          await expect(modal.getByText("Escribe el motivo.")).toBeVisible();
          await shoot(page, `admin-constructoras-desactivar-${tag}`);
          await cancel(page, "Desactivar constructora");
        }
      }

      // ---------- proyectos ----------
      await page.goto("/proyectos");
      await expect(page.getByRole("heading", { name: "Proyectos", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando proyectos" })).toBeHidden();
      await shoot(page, `proyectos-listado-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `proyectos ${theme}`);

      await page.goto("/proyectos?search=zzzz-sin-resultados");
      await expect(page.getByText("No hay proyectos con estos filtros")).toBeVisible();
      await shoot(page, `proyectos-vacio-${tag}`);

      await page.goto("/proyectos");
      await page.getByRole("button", { name: "Nuevo proyecto" }).click();
      await modalWith(page, "Nuevo proyecto")
        .getByRole("button", { name: "Crear proyecto" })
        .click();
      await expect(page.getByText("Escribe el nombre.")).toBeVisible();
      await shoot(page, `proyectos-nuevo-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nuevo proyecto ${theme}`);
      await cancel(page, "Nuevo proyecto");

      if (await openFirst(page, "Proyectos", wide)) {
        const panel = page.getByRole("dialog");
        await expect(panel.getByText("Dirección", { exact: true })).toBeVisible();
        await shoot(page, `proyectos-panel-${tag}`);
        if (axe) await expectNoSeriousA11yViolations(page, `panel proyecto ${theme}`);

        const archive = panel.getByRole("button", { name: "Archivar" });
        if (await archive.isVisible()) {
          await archive.click();
          const modal = modalWith(page, "Archivar proyecto");
          await modal.getByRole("button", { name: "Archivar" }).click();
          await expect(modal.getByText("Escribe el motivo.")).toBeVisible();
          await shoot(page, `proyectos-archivar-${tag}`);
          if (axe) await expectNoSeriousA11yViolations(page, `archivar ${theme}`);
          await cancel(page, "Archivar proyecto");
        }
      }
    }
  });
}
