import { rmSync } from "node:fs";

import { expect, test as setup } from "@playwright/test";

import { AUTH_FILE } from "../playwright.config";

// Login del asesor por la pantalla real; la sesión queda en AUTH_FILE para las demás pruebas.
setup("login del asesor", async ({ page }) => {
  // Una sesión de una corrida anterior no cuenta: sin login, las pruebas se saltan.
  rmSync(AUTH_FILE, { force: true });
  const email = process.env.E2E_USER_EMAIL;
  const password = process.env.E2E_USER_PASSWORD;
  setup.skip(
    !email || !password,
    "Falta el usuario de prueba: define E2E_USER_EMAIL y E2E_USER_PASSWORD en frontend/.env.local.",
  );

  await page.goto("/login");
  await page.getByLabel("Correo").fill(email!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Ingresar" }).click();

  await expect(page).toHaveURL(/\/solicitudes/);
  await expect(page.getByRole("heading", { name: "Solicitudes", level: 1 })).toBeVisible();
  await page.context().storageState({ path: AUTH_FILE });
});
