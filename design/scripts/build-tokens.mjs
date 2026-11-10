#!/usr/bin/env node
// Genera los artefactos del design system desde design/tokens/tokens.json.
// Uso: node design/scripts/build-tokens.mjs
// Sin dependencias: solo Node 18+.
// Falla (exit 1) si una referencia no existe o si un par de contraste no cumple WCAG.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const tokens = JSON.parse(readFileSync(join(root, "tokens", "tokens.json"), "utf8"));
const P = tokens.meta.prefix;
const colors = tokens.primitives.color;
const errors = [];

// ---------- utilidades ----------
const kebab = (s) => s.replace(/\./g, "-").replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
const cssVar = (name) => `--${P}-${kebab(name)}`;

function resolveColor(ref) {
  const m = /^\{(.+)\}$/.exec(ref);
  if (!m) return ref;
  const value = m[1].split(".").reduce((node, key) => (node == null ? undefined : node[key]), colors);
  if (typeof value !== "string") {
    errors.push(`Referencia inexistente: ${ref}`);
    return "#000000";
  }
  return value;
}

function resolveTheme(mode) {
  const out = {};
  for (const [name, ref] of Object.entries(tokens.semantic[mode])) out[name] = resolveColor(ref);
  return out;
}

function luminance(hex) {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

const themes = { light: resolveTheme("light"), dark: resolveTheme("dark") };

// ---------- contraste ----------
const report = [];
for (const mode of ["light", "dark"]) {
  for (const [fg, bg, min] of tokens.contrastChecks) {
    const ratio = contrast(themes[mode][fg], themes[mode][bg]);
    const ok = ratio >= min;
    report.push({ mode, fg, bg, ratio: Math.round(ratio * 100) / 100, min, ok });
    if (!ok) errors.push(`Contraste insuficiente (${mode}): ${fg} sobre ${bg} = ${ratio.toFixed(2)} (mínimo ${min})`);
  }
}

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}

// ---------- tokens.css ----------
const header = "/* Generado por design/scripts/build-tokens.mjs desde design/tokens/tokens.json. No editar a mano. */\n";

function primitiveVars() {
  const lines = [];
  const walk = (node, path) => {
    for (const [k, v] of Object.entries(node)) {
      const p = [...path, k];
      if (typeof v === "string") lines.push(`  --${P}-${p.map(kebab).join("-")}: ${v};`);
      else walk(v, p);
    }
  };
  walk({ color: colors }, []);
  const f = tokens.primitives.font;
  for (const [k, v] of Object.entries(f.family)) lines.push(`  --${P}-font-${k}: ${v};`);
  for (const [k, v] of Object.entries(f.size)) lines.push(`  --${P}-text-${k}: ${v};`);
  for (const [k, v] of Object.entries(f.lineHeight)) lines.push(`  --${P}-leading-${k}: ${v};`);
  for (const [k, v] of Object.entries(f.weight)) lines.push(`  --${P}-weight-${k}: ${v};`);
  for (const [k, v] of Object.entries(tokens.primitives.space)) lines.push(`  --${P}-space-${k}: ${v};`);
  for (const [k, v] of Object.entries(tokens.primitives.radius)) lines.push(`  --${P}-radius-${k}: ${v};`);
  for (const [k, v] of Object.entries(tokens.primitives.control)) lines.push(`  --${P}-control-${kebab(k)}: ${v};`);
  return lines.join("\n");
}

const semanticVars = (mode) =>
  Object.entries(themes[mode]).map(([name, value]) => `  ${cssVar(name)}: ${value};`).join("\n");

const tokensCss = `${header}
:root {
${primitiveVars()}
}

:root,
[data-theme="light"] {
  color-scheme: light;
${semanticVars("light")}
}

[data-theme="dark"] {
  color-scheme: dark;
${semanticVars("dark")}
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
${semanticVars("dark").replace(/^ {2}/gm, "    ")}
  }
}
`;

// ---------- tailwind-theme.css (Tailwind v4) ----------
const twColors = Object.keys(themes.light)
  .filter((n) => !n.startsWith("shadow."))
  .map((n) => `  --color-${kebab(n)}: var(${cssVar(n)});`)
  .join("\n");
const f = tokens.primitives.font;
const tailwindCss = `${header}/* Importar después de tokens.css: @import "tailwindcss"; @import "./tokens.css"; @import "./tailwind-theme.css"; */
@theme inline {
${twColors}
  --font-sans: var(--${P}-font-sans);
  --font-mono: var(--${P}-font-mono);
${Object.keys(f.size).map((k) => `  --text-${k}: var(--${P}-text-${k});\n  --text-${k}--line-height: var(--${P}-leading-${k});`).join("\n")}
${Object.keys(tokens.primitives.radius).filter((k) => k !== "full").map((k) => `  --radius-${k}: var(--${P}-radius-${k});`).join("\n")}
  --shadow-sm: var(${cssVar("shadow.sm")});
  --shadow-md: var(${cssVar("shadow.md")});
  --shadow-lg: var(${cssVar("shadow.lg")});
}
`;

// ---------- antd-theme.ts ----------
function antdTokens(mode) {
  const t = themes[mode];
  return {
    colorPrimary: t["brand.primary"],
    colorInfo: t["brand.primary"],
    colorSuccess: mode === "light" ? colors.green["600"] : colors.green["400"],
    colorWarning: mode === "light" ? colors.amber["600"] : colors.amber["400"],
    colorError: mode === "light" ? colors.red["600"] : colors.red["400"],
    colorLink: t["text.link"],
    colorText: t["text.primary"],
    colorTextSecondary: t["text.secondary"],
    colorTextTertiary: t["text.tertiary"],
    colorTextDisabled: t["text.disabled"],
    colorBgLayout: t["bg.canvas"],
    colorBgContainer: t["bg.surface"],
    colorBgElevated: t["bg.surface"],
    colorFillAlter: t["bg.subtle"],
    colorBorder: t["border.default"],
    colorBorderSecondary: t["border.default"],
    fontFamily: f.family.sans,
    fontFamilyCode: f.family.mono,
    fontSize: 14,
    borderRadius: 6,
    borderRadiusSM: 4,
    borderRadiusLG: 8,
    controlHeight: 32,
    controlHeightSM: 28,
    controlHeightLG: 40,
    boxShadow: t["shadow.md"],
    boxShadowSecondary: t["shadow.lg"],
  };
}

function antdComponents(mode) {
  const t = themes[mode];
  return {
    Layout: { siderBg: t["bg.sidebar"], headerBg: t["bg.surface"], bodyBg: t["bg.canvas"] },
    Menu: {
      darkItemBg: t["bg.sidebar"],
      darkSubMenuItemBg: t["bg.sidebar"],
      darkItemColor: t["text.onSidebar"],
      darkItemSelectedBg: mode === "light" ? colors.blue["700"] : colors.blue["800"],
    },
    Table: {
      headerBg: t["bg.subtle"],
      headerColor: t["text.secondary"],
      rowHoverBg: t["brand.subtle"],
      borderColor: t["border.default"],
      cellPaddingBlock: 10,
      cellPaddingInline: 12,
    },
    Card: { headerFontSize: 16 },
    Tag: { defaultBg: t["tone.neutral.bg"], defaultColor: t["tone.neutral.fg"] },
  };
}

const antdTs = `${header.replace("/*", "//").replace(" */", "")}import { theme, type ThemeConfig } from "antd";

export const lightTheme: ThemeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: ${JSON.stringify(antdTokens("light"), null, 2).replace(/\n/g, "\n  ")},
  components: ${JSON.stringify(antdComponents("light"), null, 2).replace(/\n/g, "\n  ")},
};

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: ${JSON.stringify(antdTokens("dark"), null, 2).replace(/\n/g, "\n  ")},
  components: ${JSON.stringify(antdComponents("dark"), null, 2).replace(/\n/g, "\n  ")},
};
`;

// ---------- status-tones.ts ----------
const st = { ...tokens.statusTones };
delete st.$description;
const statusTs = `${header.replace("/*", "//").replace(" */", "")}// Tono visual por código de estado. Es presentación: un código desconocido cae en "neutral".

export type Tone = "neutral" | "info" | "accent" | "success" | "warning" | "danger";
export type StatusKind = ${Object.keys(st).map((k) => JSON.stringify(k)).join(" | ")};

const TONES: Record<StatusKind, Readonly<Record<string, Tone>>> = ${JSON.stringify(st, null, 2)};

export function toneFor(kind: StatusKind, code: string | null | undefined): Tone {
  if (!code) return "neutral";
  return TONES[kind][code] ?? "neutral";
}
`;

// ---------- escribir ----------
const gen = join(root, "generated");
mkdirSync(gen, { recursive: true });
writeFileSync(join(gen, "tokens.css"), tokensCss);
writeFileSync(join(gen, "tailwind-theme.css"), tailwindCss);
writeFileSync(join(gen, "antd-theme.ts"), antdTs);
writeFileSync(join(gen, "status-tones.ts"), statusTs);
writeFileSync(
  join(gen, "contrast-report.md"),
  `# Reporte de contraste (WCAG 2.1)\n\nGenerado por \`build-tokens.mjs\`. Texto normal exige 4,5:1; elementos de interfaz y texto grande, 3:1.\n\n| Modo | Texto / elemento | Fondo | Contraste | Mínimo | OK |\n| --- | --- | --- | ---: | ---: | :---: |\n${report
    .map((r) => `| ${r.mode} | \`${r.fg}\` | \`${r.bg}\` | ${r.ratio.toFixed(2)} | ${r.min} | ${r.ok ? "sí" : "NO"} |`)
    .join("\n")}\n`,
);

// La vista previa incrusta tokens.css para abrirse sola en el navegador.
const tpl = readFileSync(join(root, "preview", "template.html"), "utf8");
writeFileSync(join(root, "preview", "index.html"), tpl.replace("/*__TOKENS_CSS__*/", tokensCss));

const worst = report.reduce((a, b) => (a.ratio / a.min < b.ratio / b.min ? a : b));
console.log(`OK: ${report.length} pares de contraste cumplen. El más justo: ${worst.mode} ${worst.fg} / ${worst.bg} = ${worst.ratio} (mín. ${worst.min}).`);
