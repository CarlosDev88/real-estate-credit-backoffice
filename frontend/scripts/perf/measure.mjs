// Medición de la auditoría de performance del front (Lighthouse + Web Vitals + red).
// Ver README.md de esta carpeta.
//
// Uso: node scripts/perf/measure.mjs --out <dir> [--roles public,admin,...] [--pages id,...]
//        [--only lighthouse|vitals] [--profiles mobile,desktop,warm,vitals,vitals-warm]
//        [--runs 5]
//
// Un Chrome (Playwright, perfil nuevo en una carpeta temporal) por rol: inicia sesión
// por la pantalla real y Lighthouse corre en ese mismo Chrome por el puerto de
// depuración, con la cookie ya puesta. Caché fría: Lighthouse limpia la caché HTTP en
// cada corrida (y para Web Vitals se limpia por CDP). Caché tibia: corrida aparte con
// una carga previa y sin limpiar.
//
// `lighthouse` y `web-vitals` no son dependencias del repo (solo sirven para medir en
// local): se cargan de `PERF_TOOLS`, una carpeta fuera del repo con
// `npm install lighthouse@13.6.0 web-vitals@6.2.3`. Playwright es el del repo.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

import { chromium } from "playwright";

import {
  BASE_URL,
  DEMO_PASSWORD,
  PAGES,
  ROLES,
  RUNS,
  USERS,
  VITALS_CPU_RATE,
  VITALS_VIEWPORT,
} from "./config.mjs";

const { values: args } = parseArgs({
  options: {
    out: { type: "string" },
    roles: { type: "string" },
    pages: { type: "string" },
    only: { type: "string" },
    runs: { type: "string" },
    port: { type: "string" },
    // Perfiles a correr (por omisión todos): mobile, desktop, warm, vitals, vitals-warm.
    profiles: { type: "string" },
  },
});
const OUT = path.resolve(args.out ?? "out");
const RUN_COUNT = Number(args.runs ?? RUNS);
const roles = args.roles ? args.roles.split(",") : ROLES;
const pageFilter = args.pages ? new Set(args.pages.split(",")) : null;
const DEBUG_PORT = Number(args.port ?? 9333);
const PROFILES = new Set((args.profiles ?? "mobile,desktop,warm,vitals,vitals-warm").split(","));
const TOOLS = path.resolve(
  process.env.PERF_TOOLS ?? path.join(import.meta.dirname, "../../../../_perf-tools"),
);
const tool = (rel) => {
  const file = path.join(TOOLS, "node_modules", rel);
  if (!existsSync(file)) {
    console.error(
      `Falta ${rel} en ${TOOLS}. Instala las herramientas fuera del repo (ver scripts/perf/README.md).`,
    );
    process.exit(1);
  }
  return file;
};
const { default: lighthouse } = await import(pathToFileURL(tool("lighthouse/core/index.js")).href);
const { default: desktopConfig } = await import(
  pathToFileURL(tool("lighthouse/core/config/desktop-config.js")).href
);
const WEB_VITALS = readFileSync(tool("web-vitals/dist/web-vitals.iife.js"), "utf8");
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const median = (xs) => {
  const v = xs.filter((x) => typeof x === "number" && Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};

// ---------- sesión ----------

async function login(page, email) {
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30_000 });
  await page.getByRole("heading", { level: 1 }).first().waitFor({ timeout: 30_000 });
  log(`  sesión de ${email} → ${new URL(page.url()).pathname}`);
}

async function csrfHeader(context) {
  const csrf = (await context.cookies(BASE_URL)).find((c) => c.name === "app_csrf")?.value;
  return csrf ? { "X-CSRFToken": csrf } : {};
}

/** Expediente de la asesora con radicación sin respuesta (botón "Registrar respuesta"). */
async function findDossier(context) {
  const api = context.request;
  const tryList = async (q) => {
    const r = await api.get(`${BASE_URL}/api/v1/applications?${q}&page_size=50`);
    return r.ok() ? (await r.json()).items : [];
  };
  const candidates = [...(await tryList("status=FILED")), ...(await tryList("quick_filter=bank"))];
  for (const app of candidates) {
    const slots = await api.get(
      `${BASE_URL}/api/v1/applications/${app.id}/document-slots?page_size=1`,
    );
    if (slots.ok() && (await slots.json()).total > 0) return app;
  }
  throw new Error("No hay un expediente radicado con documentos para la asesora.");
}

/** Enlace del comprador nuevo (como la asesora) para una solicitud en espera. */
async function createBuyerLink(context) {
  const api = context.request;
  const r = await api.get(`${BASE_URL}/api/v1/applications?quick_filter=waiting&page_size=50`);
  const items = (await r.json()).items;
  // Con PERF_BUYER_APP_CODE, siempre la misma solicitud (una sin consentimientos pendientes:
  // si no, el portal muestra esa pantalla en lugar del inicio).
  const fixed = process.env.PERF_BUYER_APP_CODE;
  const app = fixed
    ? items.find((i) => i.code === fixed)
    : items[Math.floor(Math.random() * items.length)];
  if (!app) throw new Error(`No hay una solicitud en espera ${fixed ?? ""}`);
  const created = await api.post(`${BASE_URL}/api/v1/applications/${app.id}/buyer-access-links`, {
    data: {},
    headers: await csrfHeader(context),
  });
  if (!created.ok()) throw new Error(`Enlace: ${created.status()} ${await created.text()}`);
  const url = new URL((await created.json()).url);
  return { path: `/acceso${url.search}`, code: app.code };
}

async function openRole(role, shared) {
  const userDataDir = mkdtempSync(path.join(os.tmpdir(), `perf-${role}-`));
  const context = await chromium.launchPersistentContext(userDataDir, {
    channel: "chromium",
    headless: true,
    args: [`--remote-debugging-port=${DEBUG_PORT}`],
    viewport: VITALS_VIEWPORT,
    locale: "es-CO",
    timezoneId: "America/Bogota",
  });
  context.setDefaultTimeout(30_000);
  const page = context.pages()[0] ?? (await context.newPage());
  if (USERS[role]) await login(page, USERS[role]);
  if (role === "asesora") {
    const dossier = await findDossier(context);
    shared.dossierId = dossier.id;
    shared.dossierCode = dossier.code;
    log(`  expediente: ${dossier.code} (${dossier.id})`);
  }
  if (role === "buyer") {
    if (!shared.buyerLink)
      throw new Error("Falta el enlace del comprador (corre también el rol asesora).");
    await page.goto(`${BASE_URL}${shared.buyerLink.path}`);
    await page.waitForURL((url) => url.pathname.startsWith("/portal"), { timeout: 30_000 });
    log(`  comprador dentro del portal (${shared.buyerLink.code})`);
  }
  await page.close();
  return {
    context,
    close: async () => {
      await context.close();
      rmSync(userDataDir, { recursive: true, force: true });
    },
  };
}

/** Carga previa en otra pestaña: renueva el access token si venció y calienta el servidor. */
async function warmup(context, url) {
  const p = await context.newPage();
  await p.goto(url, { waitUntil: "load" }).catch(() => {});
  await p.waitForLoadState("networkidle", { timeout: 6_000 }).catch(() => {});
  await p.close();
}

// ---------- Lighthouse ----------

// maxWaitForLoad 15 s (por omisión 45): ver P10 (cuerpo de /auth/refresh sin leer).
const LH_FLAGS = {
  port: DEBUG_PORT,
  output: ["json", "html"],
  logLevel: "error",
  maxWaitForLoad: 15_000,
};

function lhSummary(lhr) {
  const a = lhr.audits;
  const num = (id) => a[id]?.numericValue ?? null;
  return {
    finalUrl: lhr.finalDisplayedUrl,
    performance: lhr.categories.performance?.score,
    accessibility: lhr.categories.accessibility?.score,
    bestPractices: lhr.categories["best-practices"]?.score,
    seo: lhr.categories.seo?.score,
    fcp: num("first-contentful-paint"),
    lcp: num("largest-contentful-paint"),
    tbt: num("total-blocking-time"),
    cls: num("cumulative-layout-shift"),
    si: num("speed-index"),
    tti: num("interactive"),
    totalBytes: num("total-byte-weight"),
    jsBytes:
      a["resource-summary"]?.details?.items?.find((i) => i.resourceType === "script")
        ?.transferSize ?? null,
    requests: a["network-requests"]?.details?.items?.length ?? null,
    unusedJs: a["unused-javascript"]?.details?.overallSavingsBytes ?? null,
    lcpElement:
      a["lcp-breakdown-insight"]?.details?.items?.find((i) => i.type === "node")?.selector ?? null,
    renderBlocking: a["render-blocking-insight"]?.details?.items?.length ?? null,
    mainThread: num("mainthread-work-breakdown"),
    bootup: num("bootup-time"),
    runtimeError: lhr.runtimeError?.code ?? null,
    loadTimedOut: lhr.runWarnings.some((w) => w.includes("too slowly")),
  };
}

async function lighthouseRuns(ctx, pageDef, url, profile, warm) {
  const dir = path.join(OUT, "lighthouse", `${profile}${warm ? "-warm" : ""}`);
  mkdirSync(dir, { recursive: true });
  const config = profile === "desktop" ? desktopConfig : undefined;
  const runs = [];
  for (let i = 1; i <= RUN_COUNT; i++) {
    await warmup(ctx.context, url);
    const flags = { ...LH_FLAGS, disableStorageReset: warm };
    const result = await lighthouse(url, flags, config);
    const [json, html] = result.report;
    const base = path.join(dir, `${pageDef.id}-${i}`);
    writeFileSync(`${base}.json`, json);
    writeFileSync(`${base}.html`, html);
    const s = lhSummary(result.lhr);
    runs.push(s);
    log(
      `    LH ${profile}${warm ? "-warm" : ""} ${pageDef.id} #${i}: perf ${s.performance} LCP ${Math.round(s.lcp)} TBT ${Math.round(s.tbt)} CLS ${s.cls?.toFixed(3)}`,
    );
  }
  return runs;
}

// ---------- Web Vitals + red ----------

const VITALS_INIT = `
${WEB_VITALS}
window.__wv = {};
for (const name of ["LCP", "CLS", "INP", "FCP", "TTFB"]) {
  webVitals["on" + name]((m) => { window.__wv[name] = m.value; }, { reportAllChanges: true, durationThreshold: 0 });
}
`;

async function vitalsPage(context, { cold }) {
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  if (cold) await cdp.send("Network.clearBrowserCache");
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: VITALS_CPU_RATE });
  await page.addInitScript(VITALS_INIT);
  return { page, cdp };
}

function trackApi(page) {
  const reqs = [];
  const t0 = Date.now();
  page.on("request", (r) => {
    if (!r.url().includes("/api/v1/")) return;
    reqs.push({
      url: r.url().replace(BASE_URL, ""),
      method: r.method(),
      start: Date.now() - t0,
      req: r,
    });
  });
  return async () => {
    const out = [];
    // Con tope: el cuerpo de /auth/refresh sin leer por la app nunca termina (P10).
    const bounded = (p) =>
      Promise.race([p, new Promise((res) => setTimeout(() => res(null), 2_000))]);
    for (const r of reqs) {
      const resp = await bounded(r.req.response().catch(() => null));
      const timing = r.req.timing();
      let bytes = null;
      try {
        const body = resp ? await bounded(resp.body()) : null;
        bytes = body
          ? body.length
          : resp
            ? Number((await resp.allHeaders())["content-length"] ?? NaN) || null
            : null;
      } catch {}
      out.push({
        url: r.url,
        method: r.method,
        status: resp?.status() ?? null,
        // Hora real de salida (la del evento llega tarde): misma base que `end`.
        start: timing.startTime > 0 ? Math.round(timing.startTime - t0) : r.start,
        end: timing.responseEnd > 0 ? Math.round(timing.startTime + timing.responseEnd - t0) : null,
        bytes,
      });
    }
    return out;
  };
}

/** Oleadas: una petición que arranca después de que terminó otra de la API va en cascada. */
function waves(reqs) {
  const sorted = [...reqs].sort((a, b) => a.start - b.start);
  let wave = 0;
  let waveEnd = -1;
  for (const r of sorted) {
    if (r.start > waveEnd && waveEnd >= 0) wave++;
    r.wave = wave;
    waveEnd = Math.max(waveEnd, r.end ?? r.start);
  }
  return wave + 1;
}

async function settle(page, ms = 2500) {
  // Tope de 8 s: sin sesión, el cuerpo de /auth/refresh no se lee y la red no queda "idle" (PERF).
  await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => {});
  await page.waitForTimeout(ms);
}

async function neutralInteraction(page) {
  // Un clic en el título (o el cuerpo): INP de una interacción trivial con la página.
  const h1 = page.getByRole("heading", { level: 1 }).first();
  if (await h1.isVisible().catch(() => false)) await h1.click();
  else await page.mouse.click(5, 5);
  await page.waitForTimeout(800);
}

async function vitalsRuns(ctx, pageDef, url, warm) {
  const runs = [];
  let network = null;
  for (let i = 1; i <= RUN_COUNT; i++) {
    await warmup(ctx.context, url);
    if (warm) {
      // Primera carga sin medir para llenar la caché; luego la medida.
      const p = await ctx.context.newPage();
      await p.goto(url, { waitUntil: "load" }).catch(() => {});
      await p.waitForLoadState("networkidle", { timeout: 6_000 }).catch(() => {});
      await p.close();
    }
    const { page } = await vitalsPage(ctx.context, { cold: !warm });
    const collect = trackApi(page);
    await page.goto(url, { waitUntil: "load" });
    await settle(page);
    await neutralInteraction(page);
    const wv = await page.evaluate(() => ({ ...window.__wv }));
    if (i === 1 && !warm) {
      const reqs = await collect();
      const waveCount = waves(reqs);
      const counts = {};
      for (const r of reqs)
        counts[`${r.method} ${r.url}`] = (counts[`${r.method} ${r.url}`] ?? 0) + 1;
      network = {
        finalUrl: page.url().replace(BASE_URL, ""),
        apiRequests: reqs.length,
        waves: waveCount,
        duplicates: Object.entries(counts).filter(([, n]) => n > 1),
        requests: reqs,
      };
    }
    runs.push(wv);
    log(
      `    WV${warm ? "-warm" : ""} ${pageDef.id} #${i}: LCP ${Math.round(wv.LCP ?? -1)} FCP ${Math.round(wv.FCP ?? -1)} TTFB ${Math.round(wv.TTFB ?? -1)} CLS ${(wv.CLS ?? -1).toFixed(3)} INP ${wv.INP ?? "-"}`,
    );
    await page.close();
  }
  return { runs, network };
}

// ---------- interacciones (INP de 3 interacciones reales, como la asesora) ----------

async function measureInteraction(ctx, name, url, prepare, act) {
  const values = [];
  for (let i = 1; i <= RUN_COUNT; i++) {
    await warmup(ctx.context, url);
    const { page } = await vitalsPage(ctx.context, { cold: false });
    await page.goto(url, { waitUntil: "load" });
    await settle(page, Number(process.env.PERF_INTERACTION_SETTLE ?? 1500));
    await prepare(page);
    // INP solo de la interacción medida: se resetea el registro antes.
    await page.evaluate(() => {
      window.__inp = [];
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) if (e.interactionId) window.__inp.push(e.duration);
      }).observe({ type: "event", buffered: false, durationThreshold: 16 });
    });
    await act(page);
    await page.waitForTimeout(1500);
    const inp = await page.evaluate(() => (window.__inp.length ? Math.max(...window.__inp) : 0));
    values.push(inp);
    log(`    INP ${name} #${i}: ${inp} ms`);
    await page.close();
  }
  return { name, values, median: median(values) };
}

async function interactions(ctx, shared) {
  const list = `${BASE_URL}/solicitudes`;
  const dossier = `${BASE_URL}/solicitudes/${shared.dossierId}`;
  return [
    await measureInteraction(
      ctx,
      "abrir el filtro del listado",
      list,
      async (page) => page.getByLabel("Filtrar por banco").waitFor(),
      async (page) => {
        await page.getByLabel("Filtrar por banco").click();
        await page.locator(".ant-select-dropdown:visible").first().waitFor();
      },
    ),
    await measureInteraction(
      ctx,
      "cambiar de pestaña en el expediente",
      `${dossier}?tab=resumen`,
      async (page) =>
        page
          .getByRole("tab", { name: /Documentos/ })
          .first()
          .waitFor(),
      async (page) => {
        await page
          .getByRole("tab", { name: /Documentos/ })
          .first()
          .click();
        await page.getByRole("tabpanel").first().waitFor();
      },
    ),
    await measureInteraction(
      ctx,
      "abrir el modal Registrar respuesta",
      `${dossier}?tab=radicacion`,
      async (page) =>
        page
          .getByRole("button", { name: "Registrar respuesta" })
          .first()
          .waitFor({ timeout: 30_000 }),
      async (page) => {
        await page.getByRole("button", { name: "Registrar respuesta" }).first().click();
        await page.getByRole("dialog").first().waitFor();
      },
    ),
  ];
}

// ---------- principal ----------

const shared = {};
const results = {
  startedAt: new Date().toISOString(),
  baseUrl: BASE_URL,
  runs: RUN_COUNT,
  pages: {},
  interactions: null,
};
mkdirSync(OUT, { recursive: true });
const save = () => writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));

for (const role of roles) {
  const pages = PAGES.filter((p) => p.role === role && (!pageFilter || pageFilter.has(p.id)));
  const needsInteractions =
    role === "asesora" &&
    (!args.only || args.only === "vitals") &&
    (!pageFilter || pageFilter.has("interacciones"));
  if (!pages.length && !needsInteractions && !(role === "asesora" && roles.includes("buyer")))
    continue;
  log(`== rol ${role}`);
  const ctx = await openRole(role, shared);
  try {
    if (role === "asesora" && roles.includes("buyer"))
      shared.buyerLink = await createBuyerLink(ctx.context);
    for (const pageDef of pages) {
      const p = typeof pageDef.path === "function" ? pageDef.path(shared) : pageDef.path;
      const url = `${BASE_URL}${p}`;
      log(`  página ${pageDef.id} (${p})`);
      const entry = (results.pages[pageDef.id] = { role, path: p });
      if (!args.only || args.only === "lighthouse") {
        if (PROFILES.has("mobile"))
          entry.lhMobile = await lighthouseRuns(ctx, pageDef, url, "mobile", false);
        if (PROFILES.has("desktop"))
          entry.lhDesktop = await lighthouseRuns(ctx, pageDef, url, "desktop", false);
        if (PROFILES.has("warm"))
          entry.lhMobileWarm = await lighthouseRuns(ctx, pageDef, url, "mobile", true);
        save();
      }
      if (!args.only || args.only === "vitals") {
        const none = { runs: undefined, network: undefined };
        const cold = PROFILES.has("vitals") ? await vitalsRuns(ctx, pageDef, url, false) : none;
        const warm = PROFILES.has("vitals-warm") ? await vitalsRuns(ctx, pageDef, url, true) : none;
        entry.vitals = cold.runs;
        entry.vitalsWarm = warm.runs;
        entry.network = cold.network;
        save();
      }
    }
    if (needsInteractions) {
      results.interactions = await interactions(ctx, shared);
      save();
    }
  } finally {
    await ctx.close();
  }
}

// Medianas.
const pick = (runs, k) => median((runs ?? []).map((r) => r[k]));
results.medians = Object.fromEntries(
  Object.entries(results.pages).map(([id, e]) => [
    id,
    {
      path: e.path,
      lhMobile:
        e.lhMobile &&
        Object.fromEntries(
          [
            "performance",
            "accessibility",
            "bestPractices",
            "fcp",
            "lcp",
            "tbt",
            "cls",
            "si",
            "totalBytes",
            "jsBytes",
            "requests",
            "unusedJs",
          ].map((k) => [k, pick(e.lhMobile, k)]),
        ),
      lhDesktop:
        e.lhDesktop &&
        Object.fromEntries(
          ["performance", "fcp", "lcp", "tbt", "cls", "si"].map((k) => [k, pick(e.lhDesktop, k)]),
        ),
      lhMobileWarm:
        e.lhMobileWarm &&
        Object.fromEntries(
          ["performance", "fcp", "lcp", "tbt", "cls", "si", "totalBytes"].map((k) => [
            k,
            pick(e.lhMobileWarm, k),
          ]),
        ),
      vitals:
        e.vitals &&
        Object.fromEntries(["LCP", "CLS", "INP", "FCP", "TTFB"].map((k) => [k, pick(e.vitals, k)])),
      vitalsWarm:
        e.vitalsWarm &&
        Object.fromEntries(
          ["LCP", "CLS", "INP", "FCP", "TTFB"].map((k) => [k, pick(e.vitalsWarm, k)]),
        ),
      network: e.network && {
        apiRequests: e.network.apiRequests,
        waves: e.network.waves,
        duplicates: e.network.duplicates.length,
      },
    },
  ]),
);
results.finishedAt = new Date().toISOString();
save();
log("listo:", path.join(OUT, "results.json"));
