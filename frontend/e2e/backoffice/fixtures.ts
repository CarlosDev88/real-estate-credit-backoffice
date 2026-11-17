import { existsSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test as base, type Page } from "@playwright/test";

import { AUTH_FILE, BASE_URL } from "../../playwright.config";

export const NO_SESSION =
  "Sin sesión del asesor: el login se saltó (falta E2E_USER_EMAIL / E2E_USER_PASSWORD en frontend/.env.local).";
export const NO_DEMO_DATA =
  "La base no tiene datos de demo: corre `python manage.py seed_demo_data --advisor-email <usuario de prueba>` en el contenedor del backend.";

/** Pruebas con la sesión del asesor; sin sesión se saltan con un mensaje claro. */
export const test = base.extend({
  // `provide` es el `use` de Playwright (con ese nombre, la regla de hooks de React lo marca).
  storageState: async ({}, provide, testInfo) => {
    // Se revisa al correr (no al cargar): el setup crea el archivo antes.
    if (!existsSync(AUTH_FILE)) testInfo.skip(true, NO_SESSION);
    await provide(AUTH_FILE);
  },
});
export { expect };

export type Theme = "light" | "dark";

/** El tema se elige con la cookie `um-theme` (la lee el layout en el servidor). */
export async function useTheme(page: Page, theme: Theme) {
  await page.context().addCookies([{ name: "um-theme", value: theme, url: BASE_URL }]);
}

/** Abre el listado y salta la prueba si el asesor no tiene solicitudes (base sin demo). */
export async function openListOrSkip(page: Page, search = "") {
  await page.goto(`/solicitudes${search}`);
  const all = page.getByRole("tab", { name: /^Todas/ });
  await expect(all).toBeVisible();
  const count = Number((await all.textContent())?.replace(/\D/g, "") || 0);
  test.skip(count === 0, NO_DEMO_DATA);
}

/** Códigos y enlaces de las filas visibles del listado. */
export async function rowLinks(page: Page): Promise<string[]> {
  const links = page.locator("table tbody tr td:first-child a");
  await expect(links.first()).toBeVisible();
  return links.evaluateAll((els) => els.map((el) => (el as HTMLAnchorElement).pathname));
}

/** `axe` con las reglas WCAG 2.1 A y AA: falla si hay violaciones serias o críticas. */
export async function expectNoSeriousA11yViolations(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  const summary = serious.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} — ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(summary, `axe en ${label}`).toEqual([]);
}
