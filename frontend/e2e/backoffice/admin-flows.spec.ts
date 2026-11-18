import { expect as baseExpect, type Browser, type Page } from "@playwright/test";

import { BASE_URL } from "../../playwright.config";
import {
  adminTest as test,
  advisorSession,
  ensurePartnerAndProject,
  ensureSession,
  firstItem,
  hideDevOverlay,
  invitationToken,
} from "./admin-fixtures";
import { expect, expectNoSeriousA11yViolations } from "./fixtures";

// E2E de administración (F6), contra el backend local con la sesión del administrador:
// invitar y aceptar; un proyecto de punta a punta (lo crea y envía la constructora, lo
// aprueba el asesor); crear un producto y probar una regla; reordenar un catálogo. `axe` en
// cada pantalla. Crean datos de prueba con nombres "E2E …" y un sello de tiempo:
// `E2E_PORT=3002 node ./node_modules/@playwright/test/cli.js test admin-flows --project=backoffice --no-deps`.
// El token de la invitación sale del correo que el backend local imprime en su log
// (`docker logs`, contenedor `E2E_BACKEND_CONTAINER`).

test.describe.configure({ mode: "serial", timeout: 180_000 });

const STAMP = Date.now().toString(36);
const PASSWORD = "Umbral-Prueba-E2E-2026";

/** Opción de un `Select` de Ant Design por su texto (la lista va en un portal). */
async function pick(page: Page, combobox: string, option: string) {
  await page.getByRole("combobox", { name: combobox, exact: true }).click();
  await page.locator(".ant-select-dropdown:visible").getByTitle(option, { exact: true }).click();
}

const modalWith = (page: Page, title: string | RegExp) =>
  page.getByRole("dialog").filter({ has: page.locator(".ant-modal-title").getByText(title) });

/** Invita desde `/admin/usuarios` y devuelve el token del correo. */
async function invite(page: Page, email: string, role: string, partner?: string) {
  await page.goto("/admin/usuarios");
  await page.getByRole("button", { name: "Invitar usuario" }).click();
  const modal = modalWith(page, "Invitar usuario");
  await modal.getByLabel("Correo").fill(email);
  await pick(page, "Rol", role);
  if (partner) {
    await page.getByRole("combobox", { name: "Constructora", exact: true }).fill(partner);
    await page.locator(".ant-select-dropdown:visible").getByTitle(partner, { exact: true }).click();
  }
  await modal.getByRole("button", { name: "Enviar invitación" }).click();
  await expect(page.getByText("Invitación enviada")).toBeVisible();
  await expect.poll(() => invitationToken(email), { timeout: 15_000 }).not.toBeNull();
  return invitationToken(email)!;
}

/** Acepta la invitación en una ventana sin sesión. */
async function accept(browser: Browser, token: string, name: string) {
  const context = await browser.newContext({ baseURL: BASE_URL, locale: "es-CO" });
  const page = await context.newPage();
  await hideDevOverlay(page);
  await page.goto(`/aceptar-invitacion?token=${token}`);
  await expect(page.getByRole("heading", { name: "Activa tu cuenta" })).toBeVisible();
  await expect(page).toHaveURL(/\/aceptar-invitacion$/);
  await page.getByLabel("Nombre").fill(name);
  await page.getByLabel("Apellido").fill("Pruebas E2E");
  await page.getByLabel("Contraseña", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Repite la contraseña").fill(PASSWORD);
  await expectNoSeriousA11yViolations(page, "aceptar invitación");
  await page.getByRole("button", { name: "Activar mi cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Tu cuenta está lista" })).toBeVisible();
  await context.close();
}

test.beforeEach(async ({ page }) => {
  await hideDevOverlay(page);
});

test("invitar un usuario y aceptar la invitación", async ({ page, browser }) => {
  const email = `e2e.asesor.${STAMP}@example.com`;
  const token = await invite(page, email, "Asesor");
  await expectNoSeriousA11yViolations(page, "usuarios tras invitar");

  await page.goto("/admin/usuarios?vista=invitaciones&status=PENDING");
  await expect(page.getByText(email)).toBeVisible();
  await expectNoSeriousA11yViolations(page, "invitaciones");

  await accept(browser, token, "Asesora");

  // Ya es un usuario activo.
  await page.goto(`/admin/usuarios?search=${encodeURIComponent(email)}`);
  const row = page.getByRole("table", { name: "Usuarios" }).getByRole("row").nth(1);
  await expect(row.getByText("Activo")).toBeVisible();
});

test("proyecto: lo crea y envía la constructora y lo aprueba el asesor", async ({
  page,
  browser,
}) => {
  const advisor = await advisorSession();
  test.skip(!advisor, "Falta el asesor de prueba (E2E_USER_EMAIL / E2E_USER_PASSWORD).");

  // La constructora de prueba y una persona suya, invitada y aceptada.
  await page.goto("/proyectos");
  await ensurePartnerAndProject(page);
  const email = `e2e.constructora.${STAMP}@example.com`;
  const token = await invite(page, email, "Usuario de constructora", "E2E Capturas");
  await accept(browser, token, "Constructora");

  // La constructora crea el proyecto (sin elegir constructora) y lo envía a validación.
  const partnerFile = await ensureSession(
    `test-results/.auth/partner-${STAMP}.json`,
    email,
    PASSWORD,
  );
  const partnerContext = await browser.newContext({ baseURL: BASE_URL, storageState: partnerFile });
  const partnerPage = await partnerContext.newPage();
  await hideDevOverlay(partnerPage);
  await partnerPage.goto("/proyectos");
  await expect(
    partnerPage.getByText("Los proyectos de tu constructora y su validación."),
  ).toBeVisible();
  await partnerPage.getByRole("button", { name: "Nuevo proyecto" }).click();
  const form = modalWith(partnerPage, "Nuevo proyecto");
  await baseExpect(form.getByRole("combobox", { name: "Constructora", exact: true })).toHaveCount(
    0,
  );
  const name = `Proyecto E2E ${STAMP}`;
  await form.getByLabel("Nombre").fill(name);
  await partnerPage.getByRole("combobox", { name: "Municipio", exact: true }).fill("Medellín");
  await partnerPage
    .locator(".ant-select-dropdown:visible")
    .getByTitle("Medellín (Antioquia)", { exact: true })
    .click();
  await form.getByLabel("Dirección").fill("Carrera 43A # 1-50");
  await expectNoSeriousA11yViolations(partnerPage, "nuevo proyecto (constructora)");
  await form.getByRole("button", { name: "Crear proyecto" }).click();
  await expect(partnerPage.getByText("Proyecto creado")).toBeVisible();
  await expect(partnerPage).toHaveURL(/proyecto=/);
  const projectId = new URL(partnerPage.url()).searchParams.get("proyecto")!;

  const partnerPanel = partnerPage.getByRole("dialog");
  await partnerPanel.getByRole("button", { name: "Enviar a validación" }).click();
  const submit = modalWith(partnerPage, "Enviar a validación");
  await submit.getByRole("button", { name: "Enviar a validación" }).click();
  await expect(partnerPage.getByText("Proyecto enviado a validación")).toBeVisible();
  await expect(partnerPanel.getByText("En validación")).toBeVisible();
  await partnerContext.close();

  // El asesor lo aprueba.
  const advisorContext = await browser.newContext({ baseURL: BASE_URL, storageState: advisor! });
  const advisorPage = await advisorContext.newPage();
  await hideDevOverlay(advisorPage);
  await advisorPage.goto(`/proyectos?proyecto=${projectId}`);
  const panel = advisorPage.getByRole("dialog");
  await expect(panel.getByRole("heading", { name })).toBeVisible();
  await expectNoSeriousA11yViolations(advisorPage, "proyecto en validación (asesor)");
  await panel.getByRole("button", { name: "Aprobar", exact: true }).click();
  const approve = modalWith(advisorPage, "Aprobar proyecto");
  await approve.getByRole("button", { name: "Aprobar" }).click();
  await expect(advisorPage.getByText("Proyecto aprobado")).toBeVisible();
  await expect(panel.getByText("Activo", { exact: true })).toBeVisible();
  await advisorContext.close();
});

test("crear un producto y probar una regla", async ({ page }) => {
  const bank = await firstItem<{ id: string }>(page, "/api/v1/banks?ordering=name&status=ACTIVE");
  test.skip(!bank, "La base no tiene bancos activos.");
  await page.goto(`/admin/bancos?banco=${bank!.id}`);
  const bankPanel = page.getByRole("dialog");
  await bankPanel.getByRole("button", { name: "Nuevo producto" }).click();
  const productForm = modalWith(page, "Nuevo producto");
  const code = `E2E_P_${STAMP.toUpperCase()}`;
  await productForm.getByLabel("Código").fill(code);
  await productForm.getByLabel("Nombre").fill(`Producto E2E ${STAMP}`);
  await page.getByRole("combobox", { name: "Tipo de producto", exact: true }).click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option").first().click();
  await productForm.getByLabel(/Plazo máximo/).fill("360");
  await productForm.getByRole("button", { name: "Crear producto" }).click();
  await expect(
    page.getByRole("heading", { name: `Producto E2E ${STAMP}`, level: 1 }),
  ).toBeVisible();
  await expectNoSeriousA11yViolations(page, "producto nuevo");

  await page.getByRole("button", { name: "Nueva regla" }).click();
  const ruleForm = modalWith(page, "Nueva regla");
  await ruleForm.getByLabel("Código").fill(`E2E_R_${STAMP.toUpperCase()}`);
  await ruleForm.getByLabel("Mensaje").fill("Plazo de hasta 30 años.");
  await ruleForm.getByRole("button", { name: "Crear regla" }).click();
  await expect(page.getByText("Regla creada")).toBeVisible();

  const rulePanel = page.getByRole("dialog");
  await rulePanel.getByRole("button", { name: "Probar" }).click();
  const testForm = modalWith(page, /^Probar E2E_R_/);
  await testForm.getByLabel("Contexto (JSON)").fill('{"financing": {"term_months": 400}}');
  await pick(page, "Resultado esperado", "No cumple");
  await testForm.getByRole("button", { name: "Probar" }).click();
  const results = testForm.getByRole("list", { name: "Resultados de la prueba" });
  await expect(results.getByText("No cumple")).toBeVisible();
  await expect(results.getByText("Coincide con lo esperado")).toBeVisible();
  await expectNoSeriousA11yViolations(page, "probar regla");
});

test("reordenar los valores de un catálogo (y dejarlo como estaba)", async ({ page }) => {
  const response = await page.request.get("/api/v1/catalogs?page_size=100");
  const catalogs = (
    (await response.json()) as {
      items: { id: string; is_manageable: boolean; items_count: number }[];
    }
  ).items;
  const catalog = catalogs.find(
    (c) => c.is_manageable && c.items_count >= 2 && c.items_count <= 100,
  );
  test.skip(!catalog, "No hay un catálogo editable con al menos dos valores.");

  const order = async () =>
    (
      (await (
        await page.request.get(
          `/api/v1/catalogs/${catalog!.id}/items?ordering=sort_order&page_size=100`,
        )
      ).json()) as {
        items: { id: string; label: string }[];
      }
    ).items;
  const before = await order();
  const first = before[0]!;

  await page.goto(`/admin/catalogos/${catalog!.id}`);
  const list = page.getByRole("list", { name: "Valores del catálogo" });
  await expect(list).toBeVisible();
  await expectNoSeriousA11yViolations(page, "catálogo");

  await list.getByRole("button", { name: `Bajar ${first.label}` }).click();
  await expect(page.getByText(`${first.label}: puesto 2 de ${before.length}.`)).toBeAttached();
  await page.getByRole("button", { name: "Guardar orden" }).click();
  await expect(page.getByText("Orden guardado")).toBeVisible();
  const moved = await order();
  expect(moved[1]!.id).toBe(first.id);
  expect(moved[0]!.id).toBe(before[1]!.id);

  // Se deja como estaba.
  await list.getByRole("button", { name: `Subir ${first.label}` }).click();
  await page.getByRole("button", { name: "Guardar orden" }).click();
  await expect.poll(async () => (await order()).map((i) => i.id)).toEqual(before.map((i) => i.id));
});
