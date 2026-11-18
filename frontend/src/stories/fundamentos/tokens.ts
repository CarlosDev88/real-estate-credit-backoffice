// Lee los archivos generados de design/generated/ para las páginas de fundamentos.
// Nada de valores copiados: si cambian los tokens, las páginas cambian solas.

import statusTonesSource from "@design/status-tones.ts?raw";
import tailwindThemeCss from "@design/tailwind-theme.css?raw";
import tokensCss from "@design/tokens.css?raw";

import designReadme from "../../../../design/README.md?raw";
import type { StatusKind, Tone } from "@design/status-tones";

export type ThemeName = "light" | "dark";

export interface ParsedTokens {
  /** `:root` sin tema: paletas, tipografía, espaciado, radios y alturas de control. */
  base: Map<string, string>;
  light: Map<string, string>;
  dark: Map<string, string>;
}

const BLOCK = /([^{}]+)\{([^{}]*)\}/g;
const DECLARATION = /--um-([a-z0-9-]+)\s*:\s*([^;]+);/g;

/** Variables `--um-*` de tokens.css, separadas en base, claro y oscuro (sin el prefijo). */
export function parseTokensCss(css: string): ParsedTokens {
  const parsed: ParsedTokens = { base: new Map(), light: new Map(), dark: new Map() };
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const [, selector = "", body = ""] of withoutComments.matchAll(BLOCK)) {
    const target = selector.includes('data-theme="dark"')
      ? parsed.dark
      : selector.includes('data-theme="light"')
        ? parsed.light
        : parsed.base;
    for (const [, name = "", value = ""] of body.matchAll(DECLARATION)) {
      target.set(name, value.trim());
    }
  }
  return parsed;
}

const kebabToCamel = (text: string) =>
  text.replace(/-([a-z0-9])/g, (_, c: string) => c.toUpperCase());

/**
 * Nombre del token en `tokens.json` a partir de la variable CSS:
 * `brand-primary-hover` → `brand.primaryHover`, `tone-danger-on-solid` → `tone.danger.onSolid`.
 */
export function tokenName(cssName: string): string {
  const [group = "", ...rest] = cssName.split("-");
  if (group === "tone") {
    const [tone = "", ...part] = rest;
    return `tone.${tone}.${kebabToCamel(part.join("-"))}`;
  }
  return `${group}.${kebabToCamel(rest.join("-"))}`;
}

export interface ThemedToken {
  /** Nombre del token (`text.secondary`). */
  token: string;
  /** Variable CSS sin `--` (`um-text-secondary`). */
  cssVar: string;
  light: string;
  dark: string;
}

export interface TokenGroup {
  id: string;
  tokens: ThemedToken[];
}

const COLOR_GROUP_ORDER = ["bg", "border", "text", "brand", "accent", "focus", "sidebar", "tone"];

/** Tokens semánticos de color, con su valor en claro y oscuro, agrupados por prefijo. */
export function semanticColorGroups(parsed: ParsedTokens): TokenGroup[] {
  const groups = new Map<string, ThemedToken[]>();
  for (const [name, light] of parsed.light) {
    if (name.startsWith("shadow-")) continue;
    const token = tokenName(name);
    const id = token.split(".")[0] ?? "";
    const entry = { token, cssVar: `um-${name}`, light, dark: parsed.dark.get(name) ?? "" };
    groups.set(id, [...(groups.get(id) ?? []), entry]);
  }
  return [...groups.entries()]
    .map(([id, tokens]) => ({ id, tokens }))
    .sort((a, b) => order(COLOR_GROUP_ORDER, a.id) - order(COLOR_GROUP_ORDER, b.id));
}

function order(list: string[], id: string): number {
  const at = list.indexOf(id);
  return at === -1 ? list.length : at;
}

export interface PaletteColor {
  /** `blue-600` */
  name: string;
  cssVar: string;
  value: string;
}

/** Paletas primitivas (`--um-color-*`), agrupadas por familia. */
export function palettes(parsed: ParsedTokens): { family: string; colors: PaletteColor[] }[] {
  const families = new Map<string, PaletteColor[]>();
  for (const [name, value] of parsed.base) {
    if (!name.startsWith("color-")) continue;
    const short = name.slice("color-".length);
    const family = short.split("-")[0] ?? short;
    const color = { name: short, cssVar: `um-${name}`, value };
    families.set(family, [...(families.get(family) ?? []), color]);
  }
  return [...families.entries()].map(([family, colors]) => ({ family, colors }));
}

export interface ScaleStep {
  /** Paso de la escala (`md`, `4`, `full`). */
  step: string;
  cssVar: string;
  value: string;
}

/** Variables base con un prefijo (`space`, `radius`, `weight`...), en el orden del archivo. */
export function scale(parsed: ParsedTokens, prefix: string): ScaleStep[] {
  const steps: ScaleStep[] = [];
  for (const [name, value] of parsed.base) {
    if (!name.startsWith(`${prefix}-`)) continue;
    steps.push({ step: name.slice(prefix.length + 1), cssVar: `um-${name}`, value });
  }
  return steps;
}

export interface TypeStep extends ScaleStep {
  /** Interlineado del mismo paso (`--um-leading-<paso>`). */
  leading: string;
  leadingVar: string;
}

/** Escala tipográfica: cada tamaño con su interlineado. */
export function typeScale(parsed: ParsedTokens): TypeStep[] {
  return scale(parsed, "text").map((size) => ({
    ...size,
    leading: parsed.base.get(`leading-${size.step}`) ?? "",
    leadingVar: `um-leading-${size.step}`,
  }));
}

/** Sombras por tema (son las únicas que cambian con el tema fuera de los colores). */
export function shadows(parsed: ParsedTokens): ThemedToken[] {
  return [...parsed.light]
    .filter(([name]) => name.startsWith("shadow-"))
    .map(([name, light]) => ({
      token: tokenName(name),
      cssVar: `um-${name}`,
      light,
      dark: parsed.dark.get(name) ?? "",
    }));
}

export type ToneMap = Record<StatusKind, Record<string, Tone>>;

/** El mapa de tonos de status-tones.ts (no se exporta: se lee del fuente generado). */
export function parseStatusTones(source: string): ToneMap {
  const match = /const TONES[^=]*=\s*(\{[\s\S]*?\n\});/.exec(source);
  if (!match?.[1]) throw new Error("status-tones.ts: no se encontró el mapa TONES");
  return JSON.parse(match[1]) as ToneMap;
}

/** Tonos en el orden del README (de neutro a peligro). */
export const TONE_ORDER: Tone[] = ["neutral", "info", "accent", "success", "warning", "danger"];

/** Colores que expone el tema de Tailwind (`--color-<nombre>` de tailwind-theme.css). */
export function tailwindColors(css: string): Set<string> {
  return new Set([...css.matchAll(/--color-([a-z0-9-]+)\s*:/g)].map(([, name = ""]) => name));
}

/**
 * Clase de Tailwind de ejemplo para un color semántico: `text-` para texto y primer plano,
 * `border-` para bordes y divisores, `bg-` para el resto. `null` si el tema no lo expone.
 */
export function tailwindClass(cssName: string, available: Set<string>): string | null {
  if (!available.has(cssName)) return null;
  const isText = /^text-|-fg$|(^|-)on-/.test(cssName);
  if (cssName.startsWith("focus-")) return `outline-${cssName}`;
  const isBorder = /^border-|-border$|-divider$/.test(cssName);
  return `${isText ? "text" : isBorder ? "border" : "bg"}-${cssName}`;
}

/** Uso de cada tono según la tabla "Estados" del README (fuente única de la explicación). */
export function parseToneUses(readme: string): Partial<Record<Tone, string>> {
  const section = readme.split(/^## /m).find((part) => part.startsWith("Estados")) ?? "";
  const uses: Partial<Record<Tone, string>> = {};
  for (const [, tone = "", use = ""] of section.matchAll(/^\| `([a-z]+)` \| (.+?) \|$/gm)) {
    if ((TONE_ORDER as string[]).includes(tone)) uses[tone as Tone] = use.trim();
  }
  return uses;
}

export const tokens = parseTokensCss(tokensCss);
export const statusTones = parseStatusTones(statusTonesSource);
export const tailwindColorNames = tailwindColors(tailwindThemeCss);
export const toneUses = parseToneUses(designReadme);
