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

const NO_DOCS_TO_REVIEW =
  "Ninguna solicitud en revisión tiene dos documentos cargados por revisar (los datos de demo ya se revisaron). Vuelve a sembrar la demo para repetir esta prueba.";

/** Filas de documentos cargados, con análisis limpio, que el asesor puede revisar. */
function reviewableRows(page: Page): Locator {
  return page
    .getByRole("tabpanel", { name: "Documentos" })
    .locator("li")
    .filter({ has: page.getByRole("button", { name: /^Revisar / }) })
    .filter({ hasText: "Cargado" });
}

/** Primera solicitud en revisión con al menos `needed` documentos por revisar. */
async function applicationWithDocsToReview(page: Page, needed: number): Promise<string | null> {
  await openListOrSkip(page, "?quick_filter=review&page_size=50");
  const paths = await rowLinks(page).catch(() => [] as string[]);
  for (const path of paths) {
    await page.goto(`${path}?tab=documentos`);
    await expect(page.getByRole("tabpanel", { name: "Documentos" })).toBeVisible();
    await page.getByRole("tabpanel", { name: "Documentos" }).locator("li").first().waitFor();
    if ((await reviewableRows(page).count()) >= needed) return path;
  }
  return null;
}

/** Barra de filtros (el texto del select también está en la región `aria-live` de Ant Design). */
function filters(page: Page): Locator {
  return page.getByRole("group", { name: "Filtros" });
}

function drawer(page: Page): Locator {
  return page.locator(".ant-drawer-open .ant-drawer-section");
}

test.describe("backoffice del asesor", () => {
  test("listado: pestañas con conteos y un filtro en la URL", async ({ page }) => {
    await openListOrSkip(page);

    const review = page.getByRole("tab", { name: /^En revisión/ });
    await review.click();
    await expect(page).toHaveURL(/quick_filter=review/);
    await expect(review).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("table tbody tr").first()).toBeVisible();

    // Filtro por tipo de crédito: la primera opción del catálogo.
    await page.getByRole("combobox", { name: "Filtrar por tipo de crédito" }).click();
    const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").nth(1);
    const label = (await option.getAttribute("title")) ?? "";
    await option.click();
    await expect(page).toHaveURL(/product_type=/);
    await expect(filters(page).getByTitle(label)).toHaveText(`Tipo de crédito: ${label}`);

    // El estado vive en la URL: al recargar se conserva.
    await page.reload();
    await expect(page.getByRole("tab", { name: /^En revisión/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(filters(page).getByTitle(label)).toHaveText(`Tipo de crédito: ${label}`);

    await page.getByRole("button", { name: "Limpiar", exact: true }).click();
    await expect(page).not.toHaveURL(/product_type=/);
  });

  test("abre una solicitud en revisión", async ({ page }) => {
    await openListOrSkip(page, "?quick_filter=review");
    const firstRow = page.locator("table tbody tr").first();
    const code = (await firstRow.locator("td").first().textContent())?.trim() ?? "";
    await firstRow.locator("td").nth(1).click();

    await expect(page).toHaveURL(/\/solicitudes\/[0-9a-f-]+/);
    await expect(page.getByRole("heading", { name: code, level: 1 })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Resumen" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByRole("heading", { name: "Completitud del expediente" })).toBeVisible();
    await expect(page.getByRole("banner")).toContainText(code);
  });

  test("aprueba un documento y rechaza otro con su motivo", async ({ page }) => {
    const path = await applicationWithDocsToReview(page, 2);
    test.skip(path === null, NO_DOCS_TO_REVIEW);

    // Aprobar el primero.
    await reviewableRows(page)
      .first()
      .getByRole("button", { name: /^Revisar / })
      .click();
    await expect(page).toHaveURL(/slot=/);
    const panel = drawer(page);
    await expect(panel.getByText("Sin amenazas")).toBeVisible();
    const date = panel.getByLabel("Fecha del documento");
    if ((await date.count()) > 0 && !(await date.inputValue())) {
      // Sin fecha del comprador: la de ayer (no puede ser futura ni vencida).
      const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
      await date.fill(yesterday);
    }
    const approved = (await panel.getByRole("heading", { level: 2 }).textContent())?.trim();
    await panel.getByRole("button", { name: "Aprobar documento" }).click();
    await expect(page.getByText(`${approved}: aprobado`)).toBeVisible();

    // Rechazar otro: el panel pasa solo al siguiente; si se cerró, se abre desde la lista.
    if (!(await drawer(page).isVisible())) {
      await reviewableRows(page)
        .first()
        .getByRole("button", { name: /^Revisar / })
        .click();
    }
    const next = drawer(page);
    await expect(next.getByRole("heading", { level: 2 })).not.toHaveText(approved ?? "");
    const rejected = (await next.getByRole("heading", { level: 2 }).textContent())?.trim();
    await next.getByText("Rechazar", { exact: true }).click();
    await next.getByLabel("Motivo").click();
    await page.locator(".ant-select-dropdown:visible .ant-select-item-option").first().click();
    await next.getByLabel("Mensaje para el comprador").fill("Prueba E2E: sube una copia legible.");
    await next.getByRole("button", { name: "Rechazar documento" }).click();
    await expect(page.getByText(`${rejected}: rechazado`)).toBeVisible();

    // En la lista, el rechazado muestra el mensaje al comprador.
    await page.keyboard.press("Escape");
    // Puede haber dos documentos con el mismo nombre (uno por participante).
    const row = page
      .getByRole("tabpanel", { name: "Documentos" })
      .locator("li")
      .filter({ has: page.getByText(rejected ?? "", { exact: true }) })
      .filter({ hasText: "Mensaje al comprador: Prueba E2E: sube una copia legible." });
    await expect(row.first()).toBeVisible();
  });

  for (const theme of ["light", "dark"] as Theme[]) {
    test(`axe sin violaciones serias en el listado y el expediente (${theme})`, async ({
      page,
    }) => {
      await useTheme(page, theme);
      await openListOrSkip(page);
      if (theme === "dark")
        await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
      else await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");
      await expect(page.locator("table tbody tr").first()).toBeVisible();
      await expectNoSeriousA11yViolations(page, `listado (${theme})`);

      const [first] = await rowLinks(page);
      await page.goto(first!);
      await expect(page.getByRole("heading", { name: "Completitud del expediente" })).toBeVisible();
      await expectNoSeriousA11yViolations(page, `expediente, resumen (${theme})`);

      await page.goto(`${first!}?tab=documentos`);
      await page.getByRole("tabpanel", { name: "Documentos" }).locator("li").first().waitFor();
      await expectNoSeriousA11yViolations(page, `expediente, documentos (${theme})`);

      await page.goto(`${first!}?tab=historial`);
      await expect(
        page.getByRole("tabpanel", { name: "Historial" }).locator("li").first(),
      ).toBeVisible();
      await expectNoSeriousA11yViolations(page, `expediente, historial (${theme})`);
    });
  }
});
