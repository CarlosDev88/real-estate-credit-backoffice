// Junta los results.json de una campaña (carpetas run-*) y escribe tablas Markdown.
// Uso: node report.mjs <campaignDir> [<beforeCampaignDir>]  → <campaignDir>/tables.md y merged.json
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { PAGES } from "./config.mjs";

function load(dir) {
  const merged = { pages: {}, medians: {}, interactions: null };
  for (const d of readdirSync(dir).filter((d) => d.startsWith("run-"))) {
    const f = path.join(dir, d, "results.json");
    if (!existsSync(f)) continue;
    const r = JSON.parse(readFileSync(f, "utf8"));
    // Una página puede medirse en varias corridas (p. ej. Lighthouse en una, Web Vitals en otra).
    const defined = (o) => Object.fromEntries(Object.entries(o ?? {}).filter(([, v]) => v != null));
    for (const [id, e] of Object.entries(r.pages))
      merged.pages[id] = { ...merged.pages[id], ...defined(e) };
    for (const [id, m] of Object.entries(r.medians ?? {}))
      merged.medians[id] = { ...merged.medians[id], ...defined(m) };
    if (r.interactions) merged.interactions = r.interactions;
  }
  return merged;
}

const median = (xs) => {
  const v = xs.filter((x) => typeof x === "number" && Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};
const KEYS = {
  lhMobile: [
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
  ],
  lhDesktop: ["performance", "fcp", "lcp", "tbt", "cls", "si"],
  lhMobileWarm: ["performance", "fcp", "lcp", "tbt", "cls", "si", "totalBytes"],
  vitals: ["LCP", "CLS", "INP", "FCP", "TTFB"],
  vitalsWarm: ["LCP", "CLS", "INP", "FCP", "TTFB"],
};
/** Medianas desde las corridas crudas (no dependen de que la corrida haya terminado). */
function withMedians(merged) {
  for (const [id, e] of Object.entries(merged.pages)) {
    const m = { path: e.path };
    for (const [k, keys] of Object.entries(KEYS))
      if (e[k]?.length)
        m[k] = Object.fromEntries(keys.map((x) => [x, median(e[k].map((r) => r[x]))]));
    if (e.network)
      m.network = {
        apiRequests: e.network.apiRequests,
        waves: e.network.waves,
        duplicates: e.network.duplicates.length,
      };
    merged.medians[id] = m;
  }
  return merged;
}

const [dir, beforeDir] = process.argv.slice(2);
const now = withMedians(load(dir));
const before = beforeDir ? withMedians(load(beforeDir)) : null;
writeFileSync(path.join(dir, "merged.json"), JSON.stringify(now, null, 2));

const ms = (v) => (v == null ? "—" : `${Math.round(v).toLocaleString("es-CO")}`);
const s = (v) => (v == null ? "—" : `${(v / 1000).toFixed(2).replace(".", ",")} s`);
const score = (v) => (v == null ? "—" : `${Math.round(v * 100)}`);
const cls = (v) => (v == null ? "—" : v.toFixed(3).replace(".", ","));
const kb = (v) => (v == null ? "—" : `${Math.round(v / 1024).toLocaleString("es-CO")} kB`);
const ba = (fmt, b, a) => (before ? `${fmt(b)} → ${fmt(a)}` : fmt(a));

const order = PAGES.map((p) => p.id).filter((id) => now.medians[id]);
const label = (id) => `\`${now.medians[id].path.replace(/[0-9a-f-]{36}/, "<id>")}\``;
const out = [];
const table = (title, head, rowFn) => {
  out.push(
    `### ${title}\n`,
    `| Página | ${head.join(" | ")} |`,
    `|---|${head.map(() => "---:").join("|")}|`,
  );
  for (const id of order)
    out.push(`| ${label(id)} | ${rowFn(now.medians[id], before?.medians[id] ?? {}).join(" | ")} |`);
  out.push("");
};

table(
  "Lighthouse móvil (caché fría, mediana de 5)",
  ["Perf.", "A11y", "Buenas pr.", "FCP", "LCP", "TBT", "CLS", "SI", "Peso total", "JS (transfer.)"],
  (m, b) => {
    const x = m.lhMobile ?? {},
      y = b.lhMobile ?? {};
    return [
      ba(score, y.performance, x.performance),
      ba(score, y.accessibility, x.accessibility),
      ba(score, y.bestPractices, x.bestPractices),
      ba(s, y.fcp, x.fcp),
      ba(s, y.lcp, x.lcp),
      ba(ms, y.tbt, x.tbt) + " ms",
      ba(cls, y.cls, x.cls),
      ba(s, y.si, x.si),
      ba(kb, y.totalBytes, x.totalBytes),
      ba(kb, y.jsBytes, x.jsBytes),
    ];
  },
);
table(
  "Lighthouse escritorio (caché fría, mediana de 5)",
  ["Perf.", "FCP", "LCP", "TBT", "CLS", "SI"],
  (m, b) => {
    const x = m.lhDesktop ?? {},
      y = b.lhDesktop ?? {};
    return [
      ba(score, y.performance, x.performance),
      ba(s, y.fcp, x.fcp),
      ba(s, y.lcp, x.lcp),
      ba(ms, y.tbt, x.tbt) + " ms",
      ba(cls, y.cls, x.cls),
      ba(s, y.si, x.si),
    ];
  },
);
table(
  "Lighthouse móvil (caché tibia, mediana de 5)",
  ["Perf.", "FCP", "LCP", "TBT", "CLS", "Peso transferido"],
  (m, b) => {
    const x = m.lhMobileWarm ?? {},
      y = b.lhMobileWarm ?? {};
    return [
      ba(score, y.performance, x.performance),
      ba(s, y.fcp, x.fcp),
      ba(s, y.lcp, x.lcp),
      ba(ms, y.tbt, x.tbt) + " ms",
      ba(cls, y.cls, x.cls),
      ba(kb, y.totalBytes, x.totalBytes),
    ];
  },
);
for (const [key, title] of [
  ["vitals", "caché fría"],
  ["vitalsWarm", "caché tibia"],
]) {
  table(
    `Web Vitals de laboratorio (${title}, escritorio, CPU ×4, mediana de 5)`,
    ["LCP", "FCP", "TTFB", "CLS", "INP (clic neutro)"],
    (m, b) => {
      const x = m[key] ?? {},
        y = b[key] ?? {};
      return [
        ba(ms, y.LCP, x.LCP) + " ms",
        ba(ms, y.FCP, x.FCP) + " ms",
        ba(ms, y.TTFB, x.TTFB) + " ms",
        ba(cls, y.CLS, x.CLS),
        ba(ms, y.INP, x.INP) + " ms",
      ];
    },
  );
}
table(
  "Red: peticiones a la API al abrir la página (caché fría)",
  ["Peticiones", "Oleadas (cascada)", "Repetidas"],
  (m, b) => {
    const x = m.network ?? {},
      y = b.network ?? {};
    return [
      ba((v) => v ?? "—", y.apiRequests, x.apiRequests),
      ba((v) => v ?? "—", y.waves, x.waves),
      ba((v) => v ?? "—", y.duplicates, x.duplicates),
    ];
  },
);

if (now.interactions) {
  out.push(
    "### INP de 3 interacciones reales (asesora, escritorio, CPU ×4, mediana de 5)\n",
    "| Interacción | INP (ms) | Corridas |",
    "|---|---:|---|",
  );
  for (const it of now.interactions) {
    const b = before?.interactions?.find((x) => x.name === it.name);
    out.push(
      `| ${it.name} | ${ba(ms, b?.median, it.median)} | ${it.values.map((v) => Math.round(v)).join(", ")} |`,
    );
  }
  out.push("");
}

// Detalle de red: peticiones por página, las más grandes y las repetidas.
out.push("### Detalle de red por página\n");
for (const id of order) {
  const n = now.pages[id]?.network;
  if (!n) continue;
  const big = [...n.requests].sort((a, b) => (b.bytes ?? 0) - (a.bytes ?? 0)).slice(0, 3);
  out.push(
    `- ${label(id)}: ${n.apiRequests} peticiones en ${n.waves} oleadas. Mayores: ${big.map((r) => `\`${r.method} ${r.url.replace(/[0-9a-f-]{36}/g, "<id>").split("?")[0]}\` ${kb(r.bytes)}`).join(", ")}.${n.duplicates.length ? ` Repetidas: ${n.duplicates.map(([k, c]) => `\`${k.replace(/[0-9a-f-]{36}/g, "<id>")}\` ×${c}`).join(", ")}.` : ""}`,
  );
}
writeFileSync(path.join(dir, "tables.md"), out.join("\n"));
console.log(out.join("\n"));
