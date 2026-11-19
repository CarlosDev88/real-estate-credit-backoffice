import type { Browser, Locator, Page } from "@playwright/test";

import { BASE_URL } from "../../playwright.config";
import { ensureSession, firstItem } from "./admin-fixtures";
import { expect, NO_DEMO_DATA, test } from "./fixtures";

// F7 contra el backend con los datos de demo (`seed_demo_data`): pagar una parte de comisión
// y verla en "Mis comisiones" del asesor, pasar una oportunidad a perdida con motivo, la
// bandeja del broker con su enlace y la edición del inmueble antes de radicar. Cambia los
// datos de demo. Se corre en :3001 con `E2E_PORT=3001 pnpm exec playwright test f7.spec`.
//
// Los usuarios `@demo.local` comparten la contraseña de demo del backend (solo local; ver
// `backend/README.md`). Cada uno guarda su sesión y la renueva en la siguiente corrida: el
// login tiene límite de intentos (5 cada 15 min por correo).

const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "DemoUmbral2026!";
const PORT = new URL(BASE_URL).port || "3000";
const DEMO_ADVISORS: Record<string, string> = {
  "Lucía Rojas": "asesora.lucia@demo.local",
  "Andrés Patiño": "asesor.andres@demo.local",
};

/** Contexto con la sesión de un usuario de demo (renueva la guardada o inicia sesión). */
async function demoPage(browser: Browser, email: string): Promise<Page> {
  const name = email.split("@")[0]!.replace(/\W/g, "-");
  const file = await ensureSession(
    `test-results/.auth/demo-${name}-${PORT}.json`,
    email,
    DEMO_PASSWORD,
  );
  const context = await browser.newContext({ storageState: file, baseURL: BASE_URL });
  return context.newPage();
}

/** Diálogo de Ant Design que contiene ese título (el panel lateral también es un diálogo). */
function dialogWith(page: Page, title: string | RegExp): Locator {
  return page.getByRole("dialog").filter({ has: page.getByText(title, { exact: true }) });
}

/** Elige la primera opción de un `Select` (las opciones vienen de los catálogos de la API). */
async function chooseFirst(page: Page, scope: Locator, label: string | RegExp) {
  await scope.getByLabel(label).click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option").first().click();
}

interface Share {
  id: string;
  status: string;
  beneficiary_role: string;
  beneficiary: { id: string; name: string };
}
interface Settlement {
  id: string;
  status: string;
  application: { id: string; code: string };
  shares: Share[];
}

test.describe.configure({ mode: "serial" });

test("paga una parte de la comisión y el asesor la ve pagada en Mis comisiones", async ({
  browser,
}) => {
  test.setTimeout(120_000);
  const admin = await demoPage(browser, "admin@demo.local");

  // Una liquidación activa con la parte pendiente de un asesor de demo.
  const response = await admin.request.get(
    "/api/v1/commission-settlements?status=ACTIVE&page_size=50",
  );
  expect(response.ok()).toBe(true);
  const settlements = ((await response.json()) as { items: Settlement[] }).items;
  const target = settlements
    .flatMap((settlement) => settlement.shares.map((share) => ({ settlement, share })))
    .find(
      ({ share }) =>
        share.status === "PENDING" &&
        share.beneficiary_role === "ADVISOR" &&
        share.beneficiary.name in DEMO_ADVISORS,
    );
  test.skip(!target, `${NO_DEMO_DATA} (sin partes pendientes de un asesor de demo)`);
  const { settlement, share } = target!;
  const reference = `E2E-${String(Date.now()).slice(-8)}`;

  await admin.goto(`/comisiones?liquidacion=${settlement.id}`);
  const panel = dialogWith(admin, settlement.application.code);
  const item = panel.getByRole("listitem").filter({ hasText: share.beneficiary.name });
  await item.getByRole("button", { name: "Registrar pago" }).click();
  const pay = dialogWith(admin, "Registrar pago");
  await pay.getByLabel("Referencia").fill(reference);
  await pay.getByRole("button", { name: "Registrar pago" }).click();
  await expect(admin.getByText("Pago registrado")).toBeVisible();
  await expect(item.getByText(reference)).toBeVisible();
  await admin.context().close();

  // El asesor la ve pagada, con la fecha, en "Mis comisiones".
  const advisor = await demoPage(browser, DEMO_ADVISORS[share.beneficiary.name]!);
  await advisor.goto("/mis-comisiones?status=PAID");
  await expect(advisor.getByRole("heading", { name: "Mis comisiones", level: 1 })).toBeVisible();
  const row = advisor.locator("table tbody tr").filter({ hasText: settlement.application.code });
  await expect(row).toBeVisible();
  await expect(row).toContainText(/Pagada/);
  await advisor.context().close();
});

test("pasa una oportunidad a perdida con el motivo del catálogo", async ({ page }) => {
  test.setTimeout(120_000);
  const document = `7${String(Date.now()).slice(-9)}`;

  // Un cliente nuevo con su oportunidad, asignada al asesor de prueba.
  await page.goto("/clientes/nuevo");
  const form = page.getByRole("form", { name: "Nuevo cliente" });
  await chooseFirst(page, form, "Tipo de documento");
  await form.getByLabel("Número de documento").fill(document);
  await form.getByLabel("Nombres").fill("Cliente E2E");
  await form.getByLabel("Apellidos").fill(`Perdida ${document.slice(-4)}`);
  await form.getByRole("button", { name: "Crear cliente" }).click();
  await expect(page).toHaveURL(/\/clientes\/[0-9a-f-]{36}$/);
  const clientPath = new URL(page.url()).pathname;

  await page.goto(`${clientPath}?tab=oportunidades`);
  await page.getByRole("button", { name: "Nueva oportunidad" }).click();
  const create = dialogWith(page, "Nueva oportunidad");
  await chooseFirst(page, create, "Origen");
  await create.getByRole("button", { name: "Crear oportunidad" }).click();
  await expect(page).toHaveURL(/[?&]oportunidad=[0-9a-f-]{36}/);
  const opportunityId = /[?&]oportunidad=([0-9a-f-]{36})/.exec(page.url())![1]!;
  const panel = dialogWith(page, "Oportunidad");
  const assign = panel.getByRole("button", { name: "Asignarme" });
  if (await assign.isVisible()) {
    await assign.click();
    await expect(assign).toBeHidden();
  }

  // La acción que lleva a perdida sale de `available_actions` (texto de la API).
  const detail = await page.request.get(`/api/v1/opportunities/${opportunityId}`);
  const actions = (
    (await detail.json()) as {
      available_actions: { label: string; target_status: string; reason_required: boolean }[];
    }
  ).available_actions;
  const lose = actions.find((action) => action.target_status === "LOST");
  test.skip(!lose, "La oportunidad no ofrece la acción de perdida.");

  await panel.getByRole("button", { name: lose!.label, exact: true }).click();
  const confirm = page.getByRole("dialog").filter({ has: page.getByLabel("Motivo") });
  // Sin motivo no se puede: el campo muestra el error.
  await confirm.getByRole("button", { name: lose!.label, exact: true }).click();
  await expect(confirm.getByLabel("Motivo")).toHaveAttribute("aria-invalid", "true");
  await chooseFirst(page, confirm, "Motivo");
  await confirm.getByRole("button", { name: lose!.label, exact: true }).click();
  await expect(confirm).toBeHidden();
  await expect(panel.getByText("Motivo de pérdida")).toBeVisible();

  const after = (await (
    await page.request.get(`/api/v1/opportunities/${opportunityId}`)
  ).json()) as {
    status: string;
    lost_reason: { code: string } | null;
  };
  expect(after.status).toBe("LOST");
  expect(after.lost_reason?.code).toBeTruthy();
});

test("el broker ve su bandeja y genera el enlace del comprador", async ({ browser }) => {
  test.setTimeout(120_000);
  const broker = await demoPage(browser, "broker@demo.local");

  // Su inicio es la bandeja: sin el menú interno.
  await broker.goto("/");
  await expect(broker).toHaveURL(/\/prospectos/);
  await expect(broker.getByRole("heading", { name: "Mis prospectos", level: 1 })).toBeVisible();
  await expect(broker.getByText("Estado de tus solicitudes")).toBeVisible();
  await expect(broker.getByRole("link", { name: "Solicitudes", exact: true })).toHaveCount(0);

  await broker.goto("/prospectos?tab=solicitudes");
  const send = broker.getByRole("button", { name: /^Enviar enlace de SOL-/ }).first();
  test.skip(!(await send.isVisible().catch(() => false)), NO_DEMO_DATA);
  const code = /SOL-\d+/.exec((await send.getAttribute("aria-label")) ?? "")![0];
  await send.click();
  const modal = dialogWith(broker, "Enviar enlace al comprador");
  await expect(modal.getByText(code, { exact: false })).toBeVisible();
  await modal.getByRole("button", { name: "Generar enlace" }).click();
  const link = modal.getByLabel("Enlace de acceso");
  await expect(link).toHaveValue(/^https?:\/\/\S+/);
  await modal.getByRole("button", { name: "Listo" }).click();
  await expect(modal).toBeHidden();
  await broker.context().close();
});

test("el asesor edita el inmueble antes de radicar", async ({ page }) => {
  test.setTimeout(120_000);
  const application = await firstItem<{ id: string; code: string }>(
    page,
    "/api/v1/applications?status=DOCUMENT_REVIEW&page_size=1",
  );
  test.skip(!application, `${NO_DEMO_DATA} (sin solicitudes en revisión documental)`);
  const unit = `Apto E2E ${String(Date.now()).slice(-4)}`;

  await page.goto(`/solicitudes/${application!.id}`);
  const card = page.getByRole("region", { name: "Inmueble" });
  const edit = card.getByRole("button", { name: "Editar" });
  test.skip(!(await edit.isVisible().catch(() => false)), "La solicitud no tiene inmueble.");
  await edit.click();

  const panel = dialogWith(page, "Editar inmueble");
  await panel.getByLabel(/^Unidad/).fill(unit);
  await panel.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Inmueble guardado")).toBeVisible();
  await expect(panel).toBeHidden();
  await expect(card).toContainText(unit);

  // Lo guardado es lo que devuelve la API.
  const saved = (await (
    await page.request.get(`/api/v1/applications/${application!.id}/property`)
  ).json()) as { unit_reference: string };
  expect(saved.unit_reference).toBe(unit);
});
