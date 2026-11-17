import path from "node:path";
import { pathToFileURL } from "node:url";

import type { Locator, Page } from "@playwright/test";

import { expect, rowLinks, test, useTheme, type Theme } from "./fixtures";

// Capturas para comparar con los mockups (Parte 4). No corren en la suite normal:
// `E2E_SCREENSHOTS=1 pnpm exec playwright test screenshots`. Salen en
// `test-results/screenshots/` (no se versiona), junto con las del mockup en el mismo tamaño.

const OUT = "test-results/screenshots";
const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1280", width: 1280, height: 800 },
  { name: "390", width: 390, height: 844 },
];
const THEMES: Theme[] = ["light", "dark"];
const MOCKUPS = path.resolve(import.meta.dirname, "../../../design/screens");

test.skip(!process.env.E2E_SCREENSHOTS, "Capturas: corre con E2E_SCREENSHOTS=1.");
test.describe.configure({ timeout: 180_000 });

/**
 * Navega y espera a que se vea `ready`. Si el backend se reinicia (otro agente lo
 * modifica y Django recarga: `socket hang up` o `502`), espera 10 s y reintenta, hasta 3 veces.
 */
async function stableGoto(page: Page, url: string, ready: (page: Page) => Locator) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      await page.goto(url);
      await expect(ready(page)).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(/No pudimos cargar/)).toHaveCount(0);
      return;
    } catch (error) {
      if (attempt >= 3) throw error;
      await page.waitForTimeout(10_000);
    }
  }
}

async function shoot(page: Page, file: string) {
  // Espera a que terminen las animaciones de Ant Design (drawer, pestañas).
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: true });
}

async function mockup(page: Page, file: string, theme: Theme) {
  await page.goto(pathToFileURL(path.join(MOCKUPS, file)).href);
  await page.evaluate((t) => {
    if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
  }, theme);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    const tag = `${size.name}-${theme}`;

    test(`capturas ${tag}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await useTheme(page, theme);

      // Listado.
      await stableGoto(page, "/solicitudes", (p) => p.getByRole("tab", { name: /^Todas/ }));
      await expect(
        page.locator("table tbody tr, ul[aria-label='Solicitudes'] li").first(),
      ).toBeVisible();
      await shoot(page, `app-listado-${tag}`);

      // Expediente: la primera solicitud en revisión.
      await stableGoto(page, "/solicitudes?quick_filter=review", (p) =>
        p.getByRole("tab", { name: /^En revisión/ }),
      );
      let workspace: string | undefined;
      if (size.width > 860) {
        [workspace] = await rowLinks(page);
      } else {
        const href = await page
          .locator("ul[aria-label='Solicitudes'] li a")
          .first()
          .getAttribute("href");
        workspace = href ?? undefined;
      }
      expect(workspace, "No hay solicitudes en revisión en la demo").toBeTruthy();
      await stableGoto(page, workspace!, (p) =>
        p.getByRole("heading", { name: "Completitud del expediente" }),
      );
      await shoot(page, `app-expediente-${tag}`);

      // Panel de revisión: el primer documento que se pueda revisar.
      await stableGoto(page, `${workspace!}?tab=documentos`, (p) =>
        p.getByRole("tabpanel", { name: "Documentos" }).locator("li").first(),
      );
      const review = page.getByRole("button", { name: /^Revisar / }).first();
      if ((await review.count()) > 0) {
        await review.click();
        await expect(page.locator(".ant-drawer-open .ant-drawer-section")).toBeVisible();
        await shoot(page, `app-panel-${tag}`);
      }

      // Mockups en el mismo tamaño y tema.
      await mockup(page, "solicitudes.html", theme);
      await shoot(page, `mockup-listado-${tag}`);
      await mockup(page, "solicitud.html", theme);
      await shoot(page, `mockup-expediente-${tag}`);
      await page.locator("#reviewNext").click();
      await shoot(page, `mockup-panel-${tag}`);
    });
  }
}
