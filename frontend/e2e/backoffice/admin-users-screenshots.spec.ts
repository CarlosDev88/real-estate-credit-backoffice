import { test as base, type Page } from "@playwright/test";

import { adminTest as test, hideDevOverlay } from "./admin-fixtures";
import { expect, expectNoSeriousA11yViolations, useTheme, type Theme } from "./fixtures";

// Capturas y `axe` de `/admin/usuarios` (usuarios, panel, roles, invitaciones, invitar) y de
// la página pública `/aceptar-invitacion` (F6, parte 1). No corren en la suite normal:
// `E2E_PORT=3002 E2E_SCREENSHOTS=1 node ./node_modules/@playwright/test/cli.js test admin-users-screenshots --project=backoffice --no-deps`
// (con la sesión del administrador de `admin-fixtures.ts`; `--no-deps` evita el login del asesor).
// Salen en `test-results/screenshots/` (no se versiona). No cambian datos: los modales se
// cancelan y los formularios se envían vacíos (los frena la validación del front). En
// `/aceptar-invitacion` se manda un token falso, que la API rechaza.

const OUT = "test-results/screenshots";
const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1280", width: 1280, height: 800 },
  { name: "390", width: 390, height: 844 },
];
const THEMES: Theme[] = ["light", "dark"];
const NO_USERS_READ = "El usuario no tiene `users.read`: no hay capturas de /admin/usuarios.";

test.skip(!process.env.E2E_SCREENSHOTS, "Capturas: corre con E2E_SCREENSHOTS=1.");
test.describe.configure({ timeout: 300_000 });

async function shoot(page: Page, file: string) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: true });
}

async function permissions(page: Page): Promise<string[]> {
  const response = await page.request.get("/api/v1/auth/me");
  if (!response.ok()) return [];
  return ((await response.json()) as { permissions: string[] }).permissions;
}

/** Modal con ese título (no el panel lateral, que tiene botones con el mismo texto). */
const dialogWith = (page: Page, title: string) =>
  page
    .getByRole("dialog")
    .filter({ has: page.locator(".ant-modal-title").getByText(title, { exact: true }) });

for (const theme of THEMES) {
  test(`usuarios en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    await hideDevOverlay(page);
    const granted = await permissions(page);
    test.skip(!granted.includes("users.read"), NO_USERS_READ);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;
      const wide = size.name === "1440";

      await page.goto("/admin/usuarios");
      await expect(page.getByRole("heading", { name: "Usuarios", level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: "Cargando usuarios" })).toBeHidden();
      await shoot(page, `admin-usuarios-listado-${tag}`);
      if (wide) await expectNoSeriousA11yViolations(page, `usuarios ${theme}`);

      await page.goto("/admin/usuarios?search=zzzz-sin-resultados");
      await expect(page.getByText("No hay usuarios con estos filtros")).toBeVisible();
      await shoot(page, `admin-usuarios-vacio-${tag}`);

      await page.goto("/admin/usuarios");
      const first =
        size.width > 860
          ? page.getByRole("table", { name: "Usuarios" }).getByRole("row").nth(1)
          : page.getByRole("list", { name: "Usuarios" }).getByRole("listitem").first();
      await first.getByRole("link").first().click();
      const panel = page.getByRole("dialog");
      await expect(panel.getByText("Correo", { exact: true })).toBeVisible();
      await shoot(page, `admin-usuarios-panel-${tag}`);
      if (wide) await expectNoSeriousA11yViolations(page, `panel ${theme}`);

      const roles = panel.getByRole("button", { name: "Cambiar roles" });
      if (await roles.isVisible()) {
        await roles.click();
        const modal = dialogWith(page, "Cambiar roles");
        await expect(modal.getByRole("checkbox").first()).toBeVisible();
        await shoot(page, `admin-usuarios-roles-${tag}`);
        if (wide) await expectNoSeriousA11yViolations(page, `roles ${theme}`);
        await modal.getByRole("button", { name: "Cancelar" }).click();
        await expect(modal).toBeHidden();
      }

      const deactivate = panel.getByRole("button", { name: "Desactivar" });
      if (await deactivate.isVisible()) {
        await deactivate.click();
        const modal = dialogWith(page, "Desactivar usuario");
        await modal.getByRole("button", { name: "Desactivar" }).click();
        await expect(modal.getByText("Escribe el motivo.")).toBeVisible();
        await shoot(page, `admin-usuarios-desactivar-${tag}`);
        if (wide) await expectNoSeriousA11yViolations(page, `desactivar ${theme}`);
        await modal.getByRole("button", { name: "Cancelar" }).click();
        await expect(modal).toBeHidden();
      }

      if (granted.includes("invitations.read")) {
        await page.goto("/admin/usuarios?vista=invitaciones");
        await expect(page.getByRole("region", { name: "Listado de invitaciones" })).toBeVisible();
        await expect(page.getByRole("status", { name: "Cargando invitaciones" })).toBeHidden();
        await shoot(page, `admin-invitaciones-listado-${tag}`);
        if (wide) await expectNoSeriousA11yViolations(page, `invitaciones ${theme}`);
      }

      if (granted.includes("invitations.create")) {
        await page.getByRole("button", { name: "Invitar usuario" }).click();
        const modal = dialogWith(page, "Invitar usuario");
        await modal.getByRole("button", { name: "Enviar invitación" }).click();
        await expect(modal.getByText("Escribe el correo.")).toBeVisible();
        await shoot(page, `admin-invitar-${tag}`);
        if (wide) await expectNoSeriousA11yViolations(page, `invitar ${theme}`);
        await modal.getByRole("button", { name: "Cancelar" }).click();
        await expect(modal).toBeHidden();
      }
    }
  });
}

// La página pública, sin sesión.
const publicTest = base.extend({});
publicTest.skip(!process.env.E2E_SCREENSHOTS, "Capturas: corre con E2E_SCREENSHOTS=1.");
publicTest.describe.configure({ timeout: 300_000 });

for (const theme of THEMES) {
  publicTest(`aceptar invitación en tema ${theme}`, async ({ page }) => {
    await useTheme(page, theme);
    await hideDevOverlay(page);
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const tag = `${size.name}-${theme}`;
      const wide = size.name === "1440";

      await page.goto("/aceptar-invitacion?token=token-de-prueba-falso");
      await expect(page.getByRole("heading", { name: "Activa tu cuenta" })).toBeVisible();
      await expect(page).toHaveURL(/\/aceptar-invitacion$/);
      await shoot(page, `aceptar-invitacion-${tag}`);
      if (wide) await expectNoSeriousA11yViolations(page, `aceptar ${theme}`);

      await page.getByRole("button", { name: "Activar mi cuenta" }).click();
      await expect(page.getByText("Escribe tu nombre.")).toBeVisible();
      await shoot(page, `aceptar-invitacion-errores-${tag}`);

      // El token falso: la API responde INVITATION_INVALID (una vez por tema, por el límite).
      if (wide) {
        await page.getByLabel("Nombre").fill("Prueba");
        await page.getByLabel("Apellido").fill("Capturas");
        await page.getByLabel("Contraseña", { exact: true }).fill("Clave-De-Prueba-2026");
        await page.getByLabel("Repite la contraseña").fill("Clave-De-Prueba-2026");
        await page.getByRole("button", { name: "Activar mi cuenta" }).click();
        await expect(
          page.getByRole("heading", { name: "Esta invitación ya no sirve" }),
        ).toBeVisible();
        await shoot(page, `aceptar-invitacion-invalida-${tag}`);
        await expectNoSeriousA11yViolations(page, `invitación inválida ${theme}`);
      }

      await page.goto("/aceptar-invitacion");
      await expect(page.getByRole("heading", { name: "Este enlace no es válido" })).toBeVisible();
      await shoot(page, `aceptar-invitacion-sin-token-${tag}`);
    }
  });
}
