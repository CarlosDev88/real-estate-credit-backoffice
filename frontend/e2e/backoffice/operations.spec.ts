import { expect, expectNoSeriousA11yViolations, test } from "./fixtures";

// F5: Dashboard, Mi día y Reportes con el asesor de prueba, contra el backend local.
// `/dashboard/*` y `/reports/*` comparten un cupo de 20 consultas por minuto por usuario:
// cada vista se carga lo justo (axe en claro; el oscuro va en las capturas de la parte).

test.describe.configure({ timeout: 120_000 });

test("dashboard: carga los bloques y filtra por finalidad", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  const tiles = page.getByRole("region", { name: "Cifras del periodo" });
  await expect(tiles.getByText("Solicitudes creadas", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Solicitudes por estado" })).toBeVisible();
  await expect(page.getByRole("table", { name: /Embudo de solicitudes/ })).toBeVisible();
  // El asesor ve su carga (su fila) y los resultados por banco.
  await expect(page.getByRole("heading", { name: "Carga por asesor" })).toBeVisible();
  await expect(page.getByText(/No pudimos cargar/)).toHaveCount(0);
  await expectNoSeriousA11yViolations(page, "dashboard");

  await page.getByRole("combobox", { name: "Filtrar por finalidad" }).click();
  const option = page.getByRole("option").nth(1);
  const label = (await option.textContent())?.trim() ?? "";
  await option.click();
  await expect(page).toHaveURL(/purpose_code=/);
  await expect(page.getByRole("combobox", { name: "Filtrar por finalidad" })).toBeVisible();
  await expect(
    page.getByText(`Finalidad: ${label}`).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: /Embudo de solicitudes/ })
      .or(page.getByText("No se crearon solicitudes en el periodo")),
  ).toBeVisible();
  await expect(page.getByText(/No pudimos cargar/)).toHaveCount(0);
});

test("Mi día: filtra por segmento, crea una tarea desde la bandeja y la completa", async ({
  page,
}) => {
  await page.goto("/mi-dia");
  await expect(page.getByRole("heading", { name: "Mi día", level: 1 })).toBeVisible();
  const segments = page.getByRole("group", { name: "Segmentos de atención" });
  await expect(segments.getByRole("button").first()).toBeVisible();

  // El primer segmento con solicitudes (después de "Todas").
  const buttons = segments.getByRole("button");
  let picked = -1;
  for (let i = 1; i < (await buttons.count()); i += 1) {
    const count = Number((await buttons.nth(i).innerText()).match(/^\d+/)?.[0] ?? 0);
    if (count > 0) {
      picked = i;
      break;
    }
  }
  test.skip(picked < 0, "El asesor no tiene solicitudes en ningún segmento de atención.");
  await buttons.nth(picked).click();
  await expect(buttons.nth(picked)).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/attention=/);
  const tray = page.getByRole("table", { name: "Bandeja de solicitudes" });
  await expect(tray.getByRole("row").nth(1)).toBeVisible();

  // Nueva tarea desde la primera fila.
  const title = `E2E F5 ${Date.now()}`;
  await tray
    .getByRole("button", { name: /^Nueva tarea para / })
    .first()
    .click();
  const dialog = page.locator(".ant-modal").filter({ hasText: "Nueva tarea" });
  await dialog.getByLabel("Título").fill(title);
  await expectNoSeriousA11yViolations(page, "modal de nueva tarea");
  await dialog.getByRole("button", { name: "Crear tarea" }).click();
  await expect(page.getByText("Tarea creada")).toBeVisible();

  // En "Mis tareas", la completa.
  await page.getByRole("tab", { name: /Mis tareas/ }).click();
  await expect(page).toHaveURL(/tab=tareas/);
  const row = page
    .getByRole("table", { name: "Tareas" })
    .getByRole("row", { name: new RegExp(title) });
  await expect(row).toBeVisible();
  await expectNoSeriousA11yViolations(page, "mis tareas");
  await row.getByRole("button", { name: `Completar ${title}` }).click();
  await page
    .locator(".ant-modal")
    .filter({ hasText: "Completar tarea" })
    .getByRole("button", { name: "Completar" })
    .click();
  await expect(page.getByText("Tarea completada")).toBeVisible();
  await expect(row).toHaveCount(0);
});

test("reportes: pestañas, agrupar, CSV y exportación hasta descargarla", async ({ page }) => {
  await page.goto("/reportes");
  await expect(page.getByRole("heading", { name: "Reportes", level: 1 })).toBeVisible();
  await expect(page.getByRole("table", { name: /Embudo/ })).toBeVisible();
  await expectNoSeriousA11yViolations(page, "reportes: embudo");

  await page.getByRole("combobox", { name: "Agrupar por" }).click();
  await page.getByRole("option", { name: "asesor" }).click();
  await expect(page).toHaveURL(/group_by=advisor/);
  await expect(page.getByRole("table", { name: "Embudo por asesor" })).toBeVisible();

  await page.getByRole("tab", { name: "Solicitudes" }).click();
  await expect(page).toHaveURL(/tab=solicitudes/);
  await expect(page.getByRole("table", { name: "Solicitudes del reporte" })).toBeVisible();
  await expectNoSeriousA11yViolations(page, "reportes: solicitudes");

  const [csv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Descargar CSV" }).click(),
  ]);
  expect(csv.suggestedFilename()).toMatch(/^solicitudes_.*\.csv$/);

  await page.getByRole("button", { name: "Mis exportaciones" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("heading", { name: "Mis exportaciones" })).toBeVisible();
  await panel.getByRole("button", { name: "Preparar exportación" }).click();
  await expect(page.getByText("Exportación pedida")).toBeVisible();
  // En local (Celery en modo eager) termina en la misma petición; si no, se consulta cada 3 s.
  const job = panel.getByRole("listitem").first();
  const download = job.getByRole("button", { name: /^Descargar/ });
  await expect(download).toBeVisible({ timeout: 30_000 });
  await expectNoSeriousA11yViolations(page, "mis exportaciones");
  const [file] = await Promise.all([page.waitForEvent("download"), download.click()]);
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
});
