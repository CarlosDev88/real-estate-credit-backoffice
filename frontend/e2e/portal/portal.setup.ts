import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

import { request, test as setup } from "@playwright/test";

import { AUTH_FILE, BASE_URL } from "../../playwright.config";
import { LINKS_FILE, type PortalLinks } from "./fixtures";

const PROJECTS = ["portal-mobile", "portal-desktop"];

// Como el asesor de prueba: busca solicitudes de demo en espera y crea un enlace nuevo
// del comprador para cada proyecto del portal (cada enlace sirve una sola vez).
setup("enlaces del comprador", async () => {
  rmSync(LINKS_FILE, { force: true });
  setup.skip(!existsSync(AUTH_FILE), "Sin sesión del asesor: falta el usuario de prueba.");

  const api = await request.newContext({ baseURL: BASE_URL, storageState: AUTH_FILE });
  const csrf = (await api.storageState()).cookies.find((c) => c.name === "app_csrf")?.value;
  // En espera y en revisión documental: en las dos el comprador todavía puede cargar.
  const items: { id: string; code: string }[] = [];
  for (const tab of ["waiting", "review"]) {
    const list = await api.get(`/api/v1/applications?quick_filter=${tab}&page_size=50`);
    if (list.ok()) items.push(...((await list.json()) as { items: typeof items }).items);
  }
  // Solo las que tienen algún documento pendiente: el flujo sube un PDF.
  const withPending: typeof items = [];
  for (const app of items) {
    const slots = await api.get(
      `/api/v1/applications/${app.id}/document-slots?status=PENDING&page_size=1`,
    );
    if (slots.ok() && ((await slots.json()) as { total: number }).total > 0) withPending.push(app);
  }
  setup.skip(
    withPending.length < PROJECTS.length,
    "La base no tiene solicitudes de demo en espera o en revisión con documentos pendientes: corre `python manage.py seed_demo_data` en el contenedor del backend.",
  );

  // Al azar, para no gastar el límite de enlaces por hora de una misma solicitud.
  const shuffled = [...withPending].sort(() => Math.random() - 0.5);
  const links: PortalLinks = {};
  for (const [index, project] of PROJECTS.entries()) {
    const app = shuffled[index]!;
    const created = await api.post(`/api/v1/applications/${app.id}/buyer-access-links`, {
      data: {},
      headers: csrf ? { "X-CSRFToken": csrf } : {},
    });
    if (!created.ok())
      throw new Error(
        `No se pudo crear el enlace de ${app.code}: ${created.status()} ${await created.text()}`,
      );
    const url = new URL(((await created.json()) as { url: string }).url);
    links[project] = { path: `/acceso${url.search}`, code: app.code };
  }
  mkdirSync(path.dirname(LINKS_FILE), { recursive: true });
  writeFileSync(LINKS_FILE, JSON.stringify(links));
  await api.dispose();
});
