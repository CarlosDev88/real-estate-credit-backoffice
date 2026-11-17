import { existsSync, readFileSync } from "node:fs";

import { expect, test as base } from "@playwright/test";

export { expect };

export const LINKS_FILE = "test-results/.auth/portal-links.json";
export const NO_LINKS =
  "Sin enlaces del comprador: el setup del portal se saltó (sin sesión del asesor o sin solicitudes de demo en espera).";

export interface PortalLinks {
  /** Ruta `/acceso?token=…` por proyecto (`portal-mobile`, `portal-desktop`). */
  [project: string]: { path: string; code: string };
}

export function readLinks(): PortalLinks | null {
  if (!existsSync(LINKS_FILE)) return null;
  return JSON.parse(readFileSync(LINKS_FILE, "utf-8")) as PortalLinks;
}

/** Pruebas del portal: cada proyecto usa su propio enlace (sirven una sola vez). */
export const test = base.extend<{ link: { path: string; code: string } }>({
  link: async ({}, provide, testInfo) => {
    const link = readLinks()?.[testInfo.project.name];
    if (!link) testInfo.skip(true, NO_LINKS);
    await provide(link!);
  },
});
