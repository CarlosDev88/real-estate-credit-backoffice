import type { Page } from "@playwright/test";

import { adminTest as test, hideDevOverlay } from "./admin-fixtures";
import { expect, expectNoSeriousA11yViolations, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` de `/admin/documentos`, `/admin/catalogos` y `/admin/flujos` (F6, parte 4),
// con la sesión del administrador. No corren en la suite normal:
// `E2E_PORT=3002 E2E_SCREENSHOTS=1 node ./node_modules/@playwright/test/cli.js test admin-config-screenshots --project=backoffice --no-deps`.
// No cambian datos: los formularios se envían vacíos, la vista previa no escribe y el orden
// del catálogo se descarta sin guardar.

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

async function cancel(page: Page, title: string | RegExp) {
  const modal = modalWith(page, title);
  await modal.locator(".ant-modal-footer").getByRole("button", { name: "Cancelar" }).click();
  await expect(modal).toBeHidden();
}

/** Abre el primer elemento del listado (tabla o tarjetas) con su botón principal. */
async function openFirst(page: Page, name: string, wide: boolean) {
  const first = wide
    ? page.getByRole("table", { name }).getByRole("row").nth(1)
    : page.getByRole("list", { name }).getByRole("listitem").first();
  await first.getByRole("button").first().click();
}

for (const theme of THEMES) {
  test(`documentos, catálogos y flujos en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    await hideDevOverlay(page);
    const catalogs = (
      (await (await page.request.get("/api/v1/catalogs?page_size=100")).json()) as {
        items: { id: string; is_manageable: boolean; items_count: number }[];
      }
    ).items;
    const editable = catalogs.find(
      (c) => c.is_manageable && c.items_count >= 2 && c.items_count <= 100,
    );

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;
      const wide = size.width > 860;
      const axe = size.name === "1440";

      // ---------- documentos ----------
      await page.goto("/admin/documentos");
      await expect(page.getByRole("heading", { name: "Documentos", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando tipos documentales" })).toBeHidden();
      await shoot(page, `admin-documentos-tipos-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `tipos ${theme}`);

      await openFirst(page, "Tipos documentales", wide);
      await expect(page.getByRole("dialog").getByText("Formatos", { exact: true })).toBeVisible();
      await shoot(page, `admin-documentos-tipo-panel-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `panel tipo ${theme}`);
      await page.getByRole("dialog").getByRole("button", { name: "Cerrar" }).click();

      await page.getByRole("button", { name: "Nuevo tipo" }).click();
      await modalWith(page, "Nuevo tipo documental")
        .getByRole("button", { name: "Crear tipo" })
        .click();
      await expect(page.getByText("Escribe el código.")).toBeVisible();
      await shoot(page, `admin-documentos-tipo-nuevo-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nuevo tipo ${theme}`);
      await cancel(page, "Nuevo tipo documental");

      await page.goto("/admin/documentos?vista=requisitos");
      await expect(page.getByRole("status", { name: "Cargando requisitos" })).toBeHidden();
      await shoot(page, `admin-documentos-requisitos-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `requisitos ${theme}`);

      if ((await page.getByRole(wide ? "table" : "list", { name: "Requisitos" }).count()) > 0) {
        await openFirst(page, "Requisitos", wide);
        await expect(
          page.getByRole("dialog").getByText("Condiciones", { exact: true }),
        ).toBeVisible();
        await shoot(page, `admin-documentos-requisito-panel-${tag}`);
        if (axe) await expectNoSeriousA11yViolations(page, `panel requisito ${theme}`);
        await page.getByRole("dialog").getByRole("button", { name: "Cerrar" }).click();
      }

      await page.getByRole("button", { name: "Nuevo requisito" }).click();
      await expect(modalWith(page, "Nuevo requisito").getByText("Archivos mínimos")).toBeVisible();
      await shoot(page, `admin-documentos-requisito-nuevo-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `nuevo requisito ${theme}`);
      await cancel(page, "Nuevo requisito");

      await page.goto("/admin/documentos?vista=vista-previa");
      await page.getByRole("button", { name: "Ver checklist" }).click();
      await expect(page.getByRole("heading", { name: "De la solicitud" })).toBeVisible();
      await shoot(page, `admin-documentos-vista-previa-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `vista previa ${theme}`);

      // ---------- catálogos ----------
      await page.goto("/admin/catalogos");
      await expect(page.getByRole("heading", { name: "Catálogos", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando catálogos" })).toBeHidden();
      await shoot(page, `admin-catalogos-listado-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `catálogos ${theme}`);

      if (editable) {
        await page.goto(`/admin/catalogos/${editable.id}`);
        const list = page.getByRole("list", { name: "Valores del catálogo" });
        await expect(list).toBeVisible();
        await list
          .getByRole("button", { name: /^Bajar / })
          .first()
          .click();
        await expect(page.getByRole("region", { name: "Orden sin guardar" })).toBeVisible();
        await shoot(page, `admin-catalogo-orden-${tag}`);
        if (axe) await expectNoSeriousA11yViolations(page, `orden catálogo ${theme}`);
        await page.getByRole("button", { name: "Descartar" }).click();
      }

      // ---------- flujos ----------
      await page.goto("/admin/flujos?flujo=PROJECT");
      await expect(page.getByRole("heading", { name: "Flujos", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando transiciones" })).toBeHidden();
      await shoot(page, `admin-flujos-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `flujos ${theme}`);

      await openFirst(page, "Transiciones", wide);
      await expect(page.getByRole("dialog").getByText("Quién la ejecuta")).toBeVisible();
      await shoot(page, `admin-flujos-panel-${tag}`);
      if (axe) await expectNoSeriousA11yViolations(page, `panel flujo ${theme}`);
    }
  });
}
