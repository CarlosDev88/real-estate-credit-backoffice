import path from "node:path";
import { pathToFileURL } from "node:url";

import type { Page } from "@playwright/test";

// `useTheme` no es un hook de React (pone la cookie del tema): con otro nombre, la regla de hooks no lo marca.
import {
  expectNoSeriousA11yViolations,
  useTheme as setThemeCookie,
  type Theme,
} from "../backoffice/fixtures";
import { expect, test } from "./fixtures";

// Flujo del comprador con un enlace nuevo (uno por proyecto: cada enlace sirve una vez y
// `/buyer-access/consume` admite 5 intentos por hora por IP). Todo va en una sola sesión:
// el flujo de la spec, `axe` en cada pantalla en claro y oscuro y, con E2E_SCREENSHOTS=1
// en el proyecto de escritorio, las capturas a 390, 1280 y 1440 px junto a los mockups.

const SHOTS = "test-results/portal";
const THEMES: Theme[] = ["light", "dark"];
const SIZES = [
  { name: "390", width: 390, height: 844 },
  { name: "1280", width: 1280, height: 800 },
  { name: "1440", width: 1440, height: 900 },
];
const MOCKUPS = path.resolve(import.meta.dirname, "../../../design/screens");

/** PDF de una página en blanco: el backend valida el tipo real por el contenido. */
const MINIMAL_PDF = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj
trailer<</Root 1 0 R>>
%%EOF
`;

const FORMS = [
  ["/portal/datos", "Tus datos personales"],
  ["/portal/ingresos", "Ingresos y gastos"],
  ["/portal/inmueble", "El inmueble"],
  ["/portal/financiacion", "Financiación"],
] as const;

test.describe.configure({ timeout: 240_000 });

/** Va a una página del portal y espera a que termine de cargar. */
async function visit(page: Page, url: string, heading: string | RegExp) {
  await page.goto(url);
  await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  await expect(page.getByText("Cargando…")).toHaveCount(0);
  await expect(page.getByText(/No pudimos cargar/)).toHaveCount(0);
}

/** Abre la hoja de carga del primer documento que admite carga. Devuelve su etiqueta. */
async function openFirstSheet(page: Page): Promise<string | null> {
  const button = page.getByRole("button", { name: /^(Subir|Reemplazar) / }).first();
  if ((await button.count()) === 0) return null;
  const label = (await button.getAttribute("aria-label"))!
    .replace(/^(Subir|Reemplazar) /, "")
    .split(" · ")[0]!;
  await button.click();
  await expect(page.getByRole("dialog", { name: label })).toBeVisible();
  // Que termine la animación de entrada (para axe y las capturas).
  await page.waitForTimeout(500);
  return label;
}

async function shoot(page: Page, file: string, fullPage = true) {
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SHOTS}/${file}.png`, fullPage });
}

/** Todas las pantallas del portal con `axe`, en el tema de la cookie. */
async function a11yPass(page: Page, theme: Theme) {
  await visit(page, "/portal", /^Hola, /);
  await expectNoSeriousA11yViolations(page, `inicio (${theme})`);
  await visit(page, "/portal/consentimientos", "Antes de empezar");
  await expectNoSeriousA11yViolations(page, `consentimientos (${theme})`);
  for (const [url, title] of FORMS) {
    await visit(page, url, title);
    await expectNoSeriousA11yViolations(page, `${title} (${theme})`);
  }
  await visit(page, "/portal/documentos", "Tus documentos");
  await expectNoSeriousA11yViolations(page, `documentos (${theme})`);
  if (await openFirstSheet(page)) {
    await expectNoSeriousA11yViolations(page, `hoja de carga (${theme})`);
    await page.keyboard.press("Escape");
  }
}

async function mockup(page: Page, file: string, theme: Theme) {
  await page.goto(pathToFileURL(path.join(MOCKUPS, file)).href);
  await page.evaluate((t) => {
    if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
  }, theme);
}

/** Capturas de la app y del mockup en cada tamaño y tema (solo con E2E_SCREENSHOTS=1). */
async function screenshotPass(page: Page) {
  for (const theme of THEMES) {
    await setThemeCookie(page, theme);
    for (const size of SIZES) {
      const tag = `${size.name}-${theme}`;
      await page.setViewportSize({ width: size.width, height: size.height });
      await visit(page, "/portal", /^Hola, /);
      await shoot(page, `app-inicio-${tag}`);
      await visit(page, "/portal/datos", "Tus datos personales");
      await shoot(page, `app-formulario-${tag}`);
      await visit(page, "/portal/documentos", "Tus documentos");
      await shoot(page, `app-documentos-${tag}`);
      if (await openFirstSheet(page)) await shoot(page, `app-hoja-de-carga-${tag}`, false);

      await mockup(page, "portal.html", theme);
      await shoot(page, `mockup-inicio-${tag}`);
      await page.locator("[data-upload]").first().click();
      await shoot(page, `mockup-hoja-de-carga-${tag}`, false);
      await mockup(page, "portal-documentos.html", theme);
      await shoot(page, `mockup-documentos-${tag}`);
    }
  }
}

test("enlace, consentimientos, dato de contacto, carga de un PDF y salida, con axe", async ({
  page,
  link,
}, testInfo) => {
  const name = testInfo.project.name;
  await setThemeCookie(page, "light");

  // Acceso sin token: pantalla de enlace inválido (no llama a la API).
  for (const theme of THEMES) {
    await setThemeCookie(page, theme);
    await page.goto("/acceso");
    await expect(page.getByRole("heading", { name: "Este enlace no es válido" })).toBeVisible();
    await expectNoSeriousA11yViolations(page, `acceso sin token (${theme})`);
  }
  await setThemeCookie(page, "light");

  await page.goto(link.path);
  // Primero los consentimientos pendientes; si no hay, el inicio.
  const first = page.getByRole("heading", { name: /^(Antes de empezar|Hola, )/ });
  await expect(first).toBeVisible({ timeout: 20_000 });
  // El token no queda en la URL.
  expect(page.url()).not.toContain("token=");

  if ((await first.textContent()) === "Antes de empezar") {
    await shoot(page, `${name}-consentimientos`);
    const accept = page.getByRole("button", { name: "Acepto" });
    while ((await accept.count()) > 0) {
      const before = await accept.count();
      await accept.first().click();
      await expect(accept).toHaveCount(before - 1);
    }
    await page.getByRole("button", { name: "Continuar" }).click();
  }

  await expect(page).toHaveURL(/\/portal$/);
  await expect(page.getByRole("heading", { name: /^Hola, / })).toBeVisible();
  await expect(page.getByText(link.code).filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Lo que necesitamos de ti/ })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones de tu solicitud" })).toBeVisible();
  await shoot(page, `${name}-inicio`);

  // Un dato de contacto: primero un error real de la API en el campo y luego el guardado.
  await page.getByRole("link", { name: /Tus datos personales/ }).click();
  const phone = page.getByLabel("Teléfono");
  await expect(phone).toBeEditable();
  await phone.fill("123");
  await page.getByRole("button", { name: /Guardar$/ }).click();
  await expect(phone).toHaveAttribute("aria-invalid", "true");
  await phone.fill(`+57300${String(Date.now()).slice(-7)}`);
  await page.getByRole("button", { name: /Guardar$/ }).click();
  await expect(page.getByText("Guardamos tus datos")).toBeVisible();
  await expect(phone).not.toHaveAttribute("aria-invalid", "true");

  // Subir un PDF pequeño a un documento pendiente y verlo "En revisión".
  await visit(page, "/portal/documentos", "Tus documentos");
  const upload = page.getByRole("button", { name: /^Subir / }).first();
  // Nombre accesible: "Subir <documento> · <titular>"; la hoja se titula con el documento.
  const label = (await upload.getAttribute("aria-label"))!.replace(/^Subir /, "").split(" · ")[0]!;
  await upload.click();
  const sheet = page.getByRole("dialog", { name: label });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText("de hasta");
  // El último input es "Elegir archivo" en móvil y el de arrastrar en escritorio.
  await sheet
    .locator('input[type="file"]')
    .last()
    .setInputFiles({
      name: "e2e-prueba.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(MINIMAL_PDF),
    });
  await expect(page.getByText("Documento subido")).toBeVisible({ timeout: 30_000 });
  await expect(sheet).toBeHidden();
  // Puede haber cargas de corridas anteriores: la tarjeta con ese título y ese archivo.
  const uploaded = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: label, exact: true }) })
    .filter({ hasText: "e2e-prueba.pdf" })
    .first();
  await expect(uploaded).toContainText("En revisión");
  await shoot(page, `${name}-documentos`);

  // axe en cada pantalla, en claro y en oscuro.
  for (const theme of THEMES) {
    await setThemeCookie(page, theme);
    await a11yPass(page, theme);
  }

  if (process.env.E2E_SCREENSHOTS && name === "portal-desktop") {
    await screenshotPass(page);
    await page.setViewportSize({ width: 1280, height: 800 });
  }

  // Salir y acceso vencido, en los dos temas.
  await setThemeCookie(page, "light");
  await visit(page, "/portal", /^Hola, /);
  await page.getByRole("button", { name: /^Cuenta de / }).click();
  await page.getByRole("menuitem", { name: "Salir" }).click();
  await expect(page.getByRole("heading", { name: "Saliste del portal" })).toBeVisible();
  await expectNoSeriousA11yViolations(page, "saliste del portal");
  for (const theme of THEMES) {
    await setThemeCookie(page, theme);
    await page.goto("/portal");
    await expect(page.getByRole("heading", { name: "Tu acceso venció" })).toBeVisible();
    await expectNoSeriousA11yViolations(page, `acceso vencido (${theme})`);
  }
});
