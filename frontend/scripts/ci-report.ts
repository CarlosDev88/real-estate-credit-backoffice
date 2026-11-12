/**
 * Reporte del CI del frontend para el resumen del run y el comentario del PR.
 *
 * Mismo formato que `backend/scripts/ci_report.py`. Lee las salidas que dejan los pasos
 * del workflow en `CI_REPORT_DIR` (por defecto `.ci-report`) y el resultado de cada paso
 * (variables `OUTCOME_*`, con los valores de `steps.<id>.outcome`). Escribe un Markdown en
 * `report.md` y en `$GITHUB_STEP_SUMMARY`, e imprime las anotaciones de TypeScript (las de
 * ESLint las pone el *matcher* `eslint-stylish` de `setup-node`).
 *
 * Corre con Node 24 sin compilar (solo sintaxis de tipos borrable), sin dependencias y sin
 * importar nada de `src/`: solo `node:fs`, `node:path` y `node:process`.
 * Nunca hace fallar el job: si un paso no corrió, su fila sale ⏭️; si un archivo no se puede
 * leer, la fila lo dice; si algo inesperado falla, escribe un reporte mínimo y sale con 0.
 *
 * `node scripts/ci-report.ts --check-coverage` es el paso "Cobertura": compara el total de
 * líneas con `CI_COVERAGE_MIN` y sale con 1 si queda por debajo.
 */

import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import process from "node:process";

export const MARKER = "<!-- ci-report:frontend -->";
const TITLE = "Frontend CI";
const REPORT_FILE = "report.md";
const DEFAULT_REPORT_DIR = ".ci-report";
export const DEFAULT_COVERAGE_MIN = 70;

const MAX_REPORT_CHARS = 60_000;
const DETAIL_LINE_LIMITS = [50, 20, 5] as const;
const MAX_LINE_CHARS = 200;
const MAX_SUMMARY_CHARS = 160;
const MAX_TITLE_CHARS = 120;
const MAX_FAILED_TESTS = 20;
const LOWEST_COVERAGE_FILES = 5;
const TAIL_LINES = 30;
const BUILD_TAIL_LINES = 50;
const CONTRACT_DIFF_LINES = 50;
const MAX_ANNOTATIONS = 50;
const SKIPPED_LINE = "⏭️ Sin cambios en el frontend: verificaciones omitidas";
const DETAILS_OMITTED =
  "_El detalle no cabe en el comentario: está en el log del run y en el artefacto._";

const SUCCESS = "success";
const FAILURE = "failure";
const CANCELLED = "cancelled";

export const Status = {
  PASSED: "✅",
  WARNING: "⚠️",
  FAILED: "❌",
  SKIPPED: "⏭️",
} as const;
export type Status = (typeof Status)[keyof typeof Status];

const ESLINT = "ESLint";
const PRETTIER = "Prettier (formato)";
const TYPESCRIPT = "TypeScript";
const TESTS = "Tests";
const COVERAGE = "Cobertura";
const CONTRACT = "Contrato API";
const BUILD = "Build";

const ANSI_ESCAPE = /\x1b\[[0-9;]*[A-Za-z]/g;
const CONTROL_CHARS = /[\x00-\x08\x0b-\x1f\x7f]/g;
const MARKDOWN_SPECIAL = /([\\`*_[\]|~#!])/g;
const COMMIT_SHA = /^[0-9a-f]{7,40}$/;
const DIGITS = /^[0-9]+$/;
const SERVER_URL = /^https:\/\/[A-Za-z0-9.-]+(?::[0-9]+)?$/;
const REPOSITORY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const TS_ERROR = /^(?<path>.+?)\((?<line>\d+),(?<col>\d+)\): error (?<code>TS\d+): (?<message>.*)$/;
const HTTP_METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"];

export interface Detail {
  title: string;
  /** Cada entrada son una o más líneas de salida de una herramienta. */
  entries: string[];
  /** Entradas descartadas antes de llegar aquí (por ejemplo, tests más allá de los 20). */
  hidden?: number;
}

export interface Verdict {
  status: Status;
  summary: string;
  details?: Detail[];
}

export interface CheckResult extends Verdict {
  name: string;
  blocking: boolean;
}

export interface Context {
  reportDir: string;
  outcomes: Record<string, string>;
  coverageMin: number;
  /** Carpeta del frontend (las rutas del reporte son relativas a ella). */
  baseDir: string;
  /** Raíz del repo (las anotaciones de GitHub usan rutas relativas a ella). */
  repoDir: string;
}

// --- Formato -------------------------------------------------------------------------------

export function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function formatPercent(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} %`;
}

function formatMinimum(value: number): string {
  return `${String(value).replace(".", ",")} %`;
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours} h ${minutes} min`;
  if (minutes) return `${minutes} min ${secs} s`;
  return `${secs} s`;
}

function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
}

/** Una línea de salida, sin colores ni caracteres de control, y truncada. */
export function cleanLine(text: string): string {
  const plain = text.replace(ANSI_ESCAPE, "").replace(/\t/g, "    ");
  return truncate(plain.replace(CONTROL_CHARS, "").trimEnd(), MAX_LINE_CHARS);
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Texto seguro para una celda de tabla: sin HTML, sin Markdown y sin saltos de línea. */
export function mdInline(text: string, limit = MAX_SUMMARY_CHARS): string {
  const joined = text
    .split(/\r?\n/)
    .map((line) => cleanLine(line).trim())
    .join(" ");
  return escapeHtml(truncate(joined, limit)).replace(MARKDOWN_SPECIAL, "\\$1");
}

/** Texto seguro dentro de una etiqueta HTML (`<summary>`). */
function htmlText(text: string): string {
  return escapeHtml(truncate(cleanLine(text), MAX_TITLE_CHARS));
}

/** Bloque de código con una cerca más larga que cualquier serie de comillas del texto. */
export function codeBlock(lines: string[]): string {
  const longest = Math.max(0, ...lines.flatMap((l) => (l.match(/`+/g) ?? []).map((r) => r.length)));
  const fence = "`".repeat(Math.max(3, longest + 1));
  return [fence, ...lines, fence].join("\n");
}

function tail(text: string | null, count = TAIL_LINES): string[] {
  if (!text) return [];
  return text
    .split(/\r?\n/)
    .map(cleanLine)
    .filter((l) => l.trim())
    .slice(-count);
}

function tailDetails(title: string, text: string | null, count = TAIL_LINES): Detail[] {
  const lines = tail(text, count);
  return lines.length ? [{ title, entries: lines }] : [];
}

function countList(counter: Map<string, number>, limit = 5): string {
  const ranked = [...counter.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const text = ranked
    .slice(0, limit)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
  return text + (ranked.length > limit ? ", …" : "");
}

function countBy<T>(items: T[], key: (item: T) => string): Map<string, number> {
  const out = new Map<string, number>();
  for (const item of items) out.set(key(item), (out.get(key(item)) ?? 0) + 1);
  return out;
}

// --- Lectura -------------------------------------------------------------------------------

function readText(ctx: Context, name: string): string | null {
  const path = join(ctx.reportDir, name);
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

function readJson(ctx: Context, name: string): unknown {
  const text = readText(ctx, name);
  return text === null || !text.trim() ? null : (JSON.parse(text) as unknown);
}

/** Ruta legible, relativa a `frontend/`. */
function relativePath(ctx: Context, file: string): string {
  const absolute = isAbsolute(file) ? file : resolve(ctx.baseDir, file);
  const rel = relative(ctx.baseDir, absolute);
  return (rel.startsWith("..") ? file : rel).split(sep).join("/");
}

/** Ruta relativa a la raíz del repo, para las anotaciones. */
function repoPath(ctx: Context, frontendRelative: string): string {
  return relative(ctx.repoDir, resolve(ctx.baseDir, frontendRelative)).split(sep).join("/");
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function toInt(value: unknown): number {
  const n = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(n) ? n : 0;
}

// --- ESLint --------------------------------------------------------------------------------

export interface LintMessage {
  path: string;
  line: number;
  column: number;
  rule: string;
  severity: "error" | "warning";
  message: string;
}

export function loadEslint(ctx: Context): LintMessage[] | null {
  const data = readJson(ctx, "eslint.json");
  if (data === null) return null;
  if (!Array.isArray(data)) throw new Error("eslint.json: se esperaba una lista");
  const out: LintMessage[] = [];
  for (const file of data) {
    const record = asRecord(file);
    const path = relativePath(ctx, String(record.filePath ?? "?"));
    const messages = Array.isArray(record.messages) ? record.messages : [];
    for (const raw of messages) {
      const m = asRecord(raw);
      out.push({
        path,
        line: toInt(m.line),
        column: toInt(m.column),
        rule: String(m.ruleId ?? "parse-error"),
        severity: toInt(m.severity) === 2 ? "error" : "warning",
        message: String(m.message ?? ""),
      });
    }
  }
  return out;
}

function checkEslint(ctx: Context): Verdict {
  const succeeded = ctx.outcomes.eslint === SUCCESS;
  const messages = loadEslint(ctx);
  if (messages === null || messages.length === 0) {
    return succeeded
      ? { status: Status.PASSED, summary: "Sin errores" }
      : { status: Status.FAILED, summary: "Falló sin errores reportados (ver el log)" };
  }
  const errors = messages.filter((m) => m.severity === "error");
  const warnings = messages.filter((m) => m.severity === "warning");
  const files = new Set(messages.map((m) => m.path));
  const byRule = countBy(messages, (m) => m.rule);
  const ordered = [...messages].sort(
    (a, b) =>
      (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1) ||
      (byRule.get(b.rule) ?? 0) - (byRule.get(a.rule) ?? 0) ||
      a.rule.localeCompare(b.rule) ||
      a.path.localeCompare(b.path) ||
      a.line - b.line,
  );
  const parts = [];
  if (errors.length) parts.push(plural(errors.length, "error", "errores"));
  if (warnings.length) parts.push(plural(warnings.length, "advertencia", "advertencias"));
  const counts = parts.join(" · ");
  const detail: Detail = {
    title: `${ESLINT}: ${counts} (${countList(byRule)})`,
    entries: ordered.map(
      (m) =>
        `${m.severity === "error" ? "error" : "aviso"}  ${m.rule}  ${m.path}:${m.line}:${m.column}  ${m.message}`,
    ),
  };
  const summary = `${counts} en ${plural(files.size, "archivo", "archivos")}`;
  const status = errors.length || !succeeded ? Status.FAILED : Status.WARNING;
  return { status, summary, details: [detail] };
}

// --- Prettier ------------------------------------------------------------------------------

function checkPrettier(ctx: Context): Verdict {
  if (ctx.outcomes.prettier === SUCCESS) {
    return { status: Status.PASSED, summary: "Sin cambios pendientes" };
  }
  const text = readText(ctx, "prettier.txt");
  const lines = (text ?? "").split(/\r?\n/).map(cleanLine);
  const files = lines
    .filter((l) => l.startsWith("[warn] ") && !/Code style issues|Run Prettier/.test(l))
    .map((l) => l.slice("[warn] ".length).trim());
  const errors = lines.filter((l) => l.startsWith("[error] "));
  if (!files.length && !errors.length) {
    return {
      status: Status.FAILED,
      summary: "Falló (ver el log)",
      details: tailDetails(`${PRETTIER}: salida`, text),
    };
  }
  const parts = [];
  if (files.length)
    parts.push(plural(files.length, "archivo sin formatear", "archivos sin formatear"));
  if (errors.length) parts.push(plural(errors.length, "error", "errores"));
  const summary = parts.join(" · ");
  return {
    status: Status.FAILED,
    summary,
    details: [{ title: `${PRETTIER}: ${summary}`, entries: [...files, ...errors] }],
  };
}

// --- TypeScript ----------------------------------------------------------------------------

export interface TsError {
  path: string;
  line: number;
  column: number;
  code: string;
  message: string;
}

export function loadTypeScript(text: string | null): TsError[] {
  const out: TsError[] = [];
  for (const raw of (text ?? "").split(/\r?\n/)) {
    const match = TS_ERROR.exec(cleanLine(raw).trim());
    if (!match?.groups) continue;
    const g = match.groups;
    out.push({
      path: (g.path ?? "?").replace(/\\/g, "/"),
      line: toInt(g.line),
      column: toInt(g.col),
      code: g.code ?? "",
      message: g.message ?? "",
    });
  }
  return out;
}

function checkTypeScript(ctx: Context): Verdict {
  if (ctx.outcomes.typecheck === SUCCESS) return { status: Status.PASSED, summary: "Sin errores" };
  const text = readText(ctx, "tsc.txt");
  const errors = loadTypeScript(text);
  if (!errors.length) {
    return {
      status: Status.FAILED,
      summary: "Falló (ver el log)",
      details: tailDetails(`${TYPESCRIPT}: salida`, text),
    };
  }
  const files = new Set(errors.map((e) => e.path));
  const count = plural(errors.length, "error", "errores");
  return {
    status: Status.FAILED,
    summary: `${count} en ${plural(files.size, "archivo", "archivos")}`,
    details: [
      {
        title: `${TYPESCRIPT}: ${count}`,
        entries: errors.map((e) => `${e.path}:${e.line}:${e.column}  [${e.code}] ${e.message}`),
      },
    ],
  };
}

// --- Tests (JUnit de Vitest) ---------------------------------------------------------------

function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (_, entity: string) => {
    const e = entity.toLowerCase();
    if (e === "amp") return "&";
    if (e === "lt") return "<";
    if (e === "gt") return ">";
    if (e === "quot") return '"';
    if (e === "apos") return "'";
    const code = e.startsWith("#x")
      ? Number.parseInt(e.slice(2), 16)
      : Number.parseInt(e.slice(1), 10);
    return Number.isFinite(code) ? String.fromCodePoint(code) : "";
  });
}

function attributes(tag: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const match of tag.matchAll(/([\w:-]+)="([^"]*)"/g)) {
    if (match[1]) out[match[1]] = decodeEntities(match[2] ?? "");
  }
  return out;
}

export interface JUnitRun {
  total: number;
  passed: number;
  failing: number;
  skipped: number;
  duration: number;
  failures: { name: string; message: string }[];
}

/** Lector mínimo del JUnit que escribe Vitest (sin dependencias de XML). */
export function parseJUnit(xml: string): JUnitRun {
  const root = /<testsuites\b[^>]*>/.exec(xml);
  const duration = Number.parseFloat(attributes(root?.[0] ?? "").time ?? "0") || 0;
  const run: JUnitRun = { total: 0, passed: 0, failing: 0, skipped: 0, duration, failures: [] };
  for (const match of xml.matchAll(/<testcase\b([^>]*?)(\/>|>([\s\S]*?)<\/testcase>)/g)) {
    const attrs = attributes(match[1] ?? "");
    const body = match[3] ?? "";
    run.total += 1;
    const failure = /<(failure|error)\b([^>]*?)(?:\/>|>([\s\S]*?)<\/\1>)/.exec(body);
    if (failure) {
      run.failing += 1;
      const fAttrs = attributes(failure[2] ?? "");
      const message = fAttrs.message || decodeEntities(failure[3] ?? "");
      const first = message.split(/\r?\n/).find((l) => l.trim()) ?? "";
      const name = [attrs.classname, attrs.name].filter(Boolean).join(" › ");
      run.failures.push({ name, message: cleanLine(first.trim()) });
    } else if (/<skipped\b/.test(body)) {
      run.skipped += 1;
    } else {
      run.passed += 1;
    }
  }
  return run;
}

function checkTests(ctx: Context): Verdict {
  const succeeded = ctx.outcomes.tests === SUCCESS;
  const status = succeeded ? Status.PASSED : Status.FAILED;
  const xml = readText(ctx, "vitest.xml");
  if (xml === null) {
    return {
      status,
      summary: succeeded ? "Pasaron (sin resultados JUnit)" : "Falló sin resultados (ver el log)",
    };
  }
  const run = parseJUnit(xml);
  const summary =
    [
      plural(run.passed, "pasa", "pasan"),
      plural(run.failing, "falla", "fallan"),
      plural(run.skipped, "saltado", "saltados"),
    ].join(" · ") + ` (${run.total} en ${formatDuration(run.duration)})`;
  if (!run.failures.length) return { status, summary };
  const shown = run.failures.slice(0, MAX_FAILED_TESTS);
  return {
    status,
    summary,
    details: [
      {
        title: `Tests que fallan (${run.failing})`,
        entries: shown.map((f) => (f.message ? `${f.name}\n    ${f.message}` : f.name)),
        hidden: run.failures.length - shown.length,
      },
    ],
  };
}

// --- Cobertura -----------------------------------------------------------------------------

export interface CoverageFile {
  path: string;
  percent: number;
  lines: number;
}

export interface CoverageData {
  lines: number;
  branches: number;
  functions: number;
  files: CoverageFile[];
}

function pct(metric: unknown): number {
  const record = asRecord(metric);
  const value = typeof record.pct === "number" ? record.pct : Number(record.pct);
  return Number.isFinite(value) ? value : 100;
}

/** `coverage-summary.json` de Vitest (reporter `json-summary`). */
export function loadCoverage(ctx: Context): CoverageData | null {
  const data = asRecord(readJson(ctx, "coverage/coverage-summary.json"));
  if (!("total" in data)) return null;
  const total = asRecord(data.total);
  const files: CoverageFile[] = [];
  for (const [file, metrics] of Object.entries(data)) {
    if (file === "total") continue;
    const lines = asRecord(asRecord(metrics).lines);
    const count = toInt(lines.total);
    if (count > 0) files.push({ path: relativePath(ctx, file), percent: pct(lines), lines: count });
  }
  return {
    lines: pct(total.lines),
    branches: pct(total.branches),
    functions: pct(total.functions),
    files,
  };
}

function checkCoverage(ctx: Context): Verdict {
  const succeeded = ctx.outcomes.coverage === SUCCESS;
  const status = succeeded ? Status.PASSED : Status.FAILED;
  const testsFailed = ctx.outcomes.tests === FAILURE;
  const suffix = testsFailed ? " · con tests fallidos" : "";
  const minimum = formatMinimum(ctx.coverageMin);
  const data = loadCoverage(ctx);
  if (!data) {
    const summary = succeeded
      ? `Sobre el mínimo (${minimum})`
      : `Por debajo del mínimo (${minimum}) o sin datos (ver el log)`;
    return { status, summary: summary + suffix };
  }
  const percent = formatPercent(data.lines);
  // Con tests fallidos se separa con "·" para no encadenar paréntesis.
  const summary = testsFailed
    ? `${percent} · mínimo ${minimum}${suffix}`
    : `${percent} (mínimo ${minimum})`;
  if (succeeded) return { status, summary };
  const lowest = [...data.files]
    .sort((a, b) => a.percent - b.percent || b.lines - a.lines || a.path.localeCompare(b.path))
    .slice(0, LOWEST_COVERAGE_FILES);
  const entries = [
    `Líneas ${formatPercent(data.lines)} · ramas ${formatPercent(data.branches)} · funciones ${formatPercent(data.functions)}`,
    ...lowest.map(
      (f) =>
        `${formatPercent(f.percent).padStart(8)}  ${f.path} (${plural(f.lines, "línea", "líneas")})`,
    ),
  ];
  const title = `${COVERAGE}: ${plural(lowest.length, "archivo", "archivos")} con menos cobertura`;
  return { status, summary, details: [{ title, entries }] };
}

function coverageSkippedSummary(ctx: Context): string {
  const ran = ctx.outcomes.tests === SUCCESS || ctx.outcomes.tests === FAILURE;
  return ran ? "Sin datos de cobertura" : "No corrió";
}

// --- Contrato API (schema.d.ts) ------------------------------------------------------------

/** Entradas de una sección del `.d.ts` de openapi-typescript, por clave y con su texto. */
function sectionEntries(text: string, start: RegExp, indent: number): Map<string, string> {
  const lines = text.split(/\r?\n/);
  const out = new Map<string, string>();
  const begin = lines.findIndex((l) => start.test(l));
  if (begin < 0) return out;
  const close = " ".repeat(indent - 4);
  const keyLine = new RegExp(`^ {${indent}}(?:"([^"]+)"|([A-Za-z0-9_$]+))\\??: `);
  let current: string | null = null;
  for (const line of lines.slice(begin + 1)) {
    if (line === `${close}}` || line === `${close}};`) break;
    const match = keyLine.exec(line);
    if (match) {
      current = match[1] ?? match[2] ?? null;
      if (current) out.set(current, line);
    } else if (current) {
      out.set(current, `${out.get(current) ?? ""}\n${line}`);
    }
  }
  return out;
}

export interface ContractDiff {
  routesAdded: string[];
  routesRemoved: string[];
  routesChanged: string[];
  schemasAdded: string[];
  schemasRemoved: string[];
  schemasChanged: string[];
}

function routeMethods(block: string): { method: string; operation: string | null }[] {
  const out = [];
  for (const method of HTTP_METHODS) {
    const match = new RegExp(`^ {8}${method}: (?:operations\\["([^"]+)"\\]|never)`, "m").exec(
      block,
    );
    if (match && !match[0].endsWith("never")) out.push({ method, operation: match[1] ?? null });
  }
  return out;
}

function compareKeys(before: Map<string, string>, after: Map<string, string>) {
  const added = [...after.keys()].filter((k) => !before.has(k)).sort();
  const removed = [...before.keys()].filter((k) => !after.has(k)).sort();
  const changed = [...after.keys()]
    .filter((k) => before.has(k) && before.get(k) !== after.get(k))
    .sort();
  return { added, removed, changed };
}

/** Compara el `schema.d.ts` commiteado con el generado, por rutas, operaciones y esquemas. */
export function diffContract(committed: string, generated: string): ContractDiff {
  const pathsBefore = sectionEntries(committed, /^export interface paths \{$/, 4);
  const pathsAfter = sectionEntries(generated, /^export interface paths \{$/, 4);
  const opsBefore = sectionEntries(committed, /^export interface operations \{$/, 4);
  const opsAfter = sectionEntries(generated, /^export interface operations \{$/, 4);
  const schemasBefore = sectionEntries(committed, /^ {4}schemas: \{$/, 8);
  const schemasAfter = sectionEntries(generated, /^ {4}schemas: \{$/, 8);

  const label = (path: string, block: string | undefined) => {
    const methods = routeMethods(block ?? "").map((m) => m.method.toUpperCase());
    return methods.length ? `${methods.join(", ")} ${path}` : path;
  };
  const routes = compareKeys(pathsBefore, pathsAfter);
  const changedOps = new Set(compareKeys(opsBefore, opsAfter).changed);
  const changedRoutes = new Set(routes.changed);
  for (const [path, block] of pathsAfter) {
    if (!pathsBefore.has(path)) continue;
    if (routeMethods(block).some((m) => m.operation && changedOps.has(m.operation))) {
      changedRoutes.add(path);
    }
  }
  const schemas = compareKeys(schemasBefore, schemasAfter);
  return {
    routesAdded: routes.added.map((p) => label(p, pathsAfter.get(p))),
    routesRemoved: routes.removed.map((p) => label(p, pathsBefore.get(p))),
    routesChanged: [...changedRoutes].sort().map((p) => label(p, pathsAfter.get(p))),
    schemasAdded: schemas.added,
    schemasRemoved: schemas.removed,
    schemasChanged: schemas.changed,
  };
}

function checkContract(ctx: Context): Verdict {
  if (ctx.outcomes.api_contract === SUCCESS) return { status: Status.PASSED, summary: "Al día" };
  const committed = readText(ctx, "schema.committed.d.ts");
  const generated = readText(ctx, "schema.generated.d.ts");
  if (committed === null || generated === null) {
    return {
      status: Status.FAILED,
      summary: "No se pudieron generar los tipos (ver el log)",
      details: tailDetails(`${CONTRACT}: salida de api:gen`, readText(ctx, "api-gen.txt")),
    };
  }
  const diff = diffContract(committed, generated);
  const groups: [string[], string, string, string][] = [
    [diff.routesAdded, "+ ", "ruta nueva", "rutas nuevas"],
    [diff.routesRemoved, "- ", "ruta quitada", "rutas quitadas"],
    [diff.routesChanged, "~ ", "ruta cambiada", "rutas cambiadas"],
    [diff.schemasAdded, "+ esquema ", "esquema nuevo", "esquemas nuevos"],
    [diff.schemasRemoved, "- esquema ", "esquema quitado", "esquemas quitados"],
    [diff.schemasChanged, "~ esquema ", "esquema cambiado", "esquemas cambiados"],
  ];
  const parts = groups
    .filter(([items]) => items.length)
    .map(([items, , one, many]) => plural(items.length, one, many));
  const entries = groups.flatMap(([items, prefix]) => items.map((item) => `${prefix}${item}`));
  const summary = parts.length
    ? `Desactualizado: ${parts.join(" · ")}`
    : "Desactualizado (ver el log)";
  const hint = "Corre `pnpm api:gen` en frontend/ y commitea src/lib/api/schema.d.ts.";
  const details: Detail[] = [];
  if (entries.length) {
    details.push({ title: `${CONTRACT}: ${summary}`, entries: [...entries, "", hint] });
  }
  const diffLines = (readText(ctx, "api-contract.diff") ?? "")
    .split(/\r?\n/)
    .filter((l) => /^[+-]/.test(l) && !/^(\+\+\+|---) /.test(l))
    .map(cleanLine);
  if (diffLines.length) {
    details.push({
      title: `${CONTRACT}: diff de schema.d.ts (primeras ${CONTRACT_DIFF_LINES} líneas)`,
      entries: diffLines.slice(0, CONTRACT_DIFF_LINES),
      hidden: Math.max(0, diffLines.length - CONTRACT_DIFF_LINES),
    });
  }
  return { status: Status.FAILED, summary, details };
}

// --- Build ---------------------------------------------------------------------------------

function checkBuild(ctx: Context): Verdict {
  if (ctx.outcomes.build === SUCCESS) return { status: Status.PASSED, summary: "Compiló" };
  return {
    status: Status.FAILED,
    summary: "No compiló",
    details: tailDetails(
      `${BUILD}: últimas ${BUILD_TAIL_LINES} líneas`,
      readText(ctx, "build.txt"),
      BUILD_TAIL_LINES,
    ),
  };
}

// --- Reporte -------------------------------------------------------------------------------

interface CheckSpec {
  name: string;
  outcomeKey: string;
  build: (ctx: Context) => Verdict;
  skippedSummary?: (ctx: Context) => string;
}

const CHECKS: CheckSpec[] = [
  { name: ESLINT, outcomeKey: "eslint", build: checkEslint },
  { name: PRETTIER, outcomeKey: "prettier", build: checkPrettier },
  { name: TYPESCRIPT, outcomeKey: "typecheck", build: checkTypeScript },
  { name: TESTS, outcomeKey: "tests", build: checkTests },
  {
    name: COVERAGE,
    outcomeKey: "coverage",
    build: checkCoverage,
    skippedSummary: coverageSkippedSummary,
  },
  { name: CONTRACT, outcomeKey: "api_contract", build: checkContract },
  { name: BUILD, outcomeKey: "build", build: checkBuild },
];
const OUTCOME_KEYS = ["install", ...CHECKS.map((c) => c.outcomeKey)];

function runCheck(spec: CheckSpec, ctx: Context, skipped: boolean): CheckResult {
  const outcome = ctx.outcomes[spec.outcomeKey] ?? "";
  if (skipped)
    return {
      name: spec.name,
      status: Status.SKIPPED,
      summary: "Sin cambios en el frontend",
      blocking: true,
    };
  if (outcome !== SUCCESS && outcome !== FAILURE) {
    const summary =
      outcome === CANCELLED ? "Cancelado" : (spec.skippedSummary?.(ctx) ?? "No corrió");
    return { name: spec.name, status: Status.SKIPPED, summary, blocking: true };
  }
  try {
    return { name: spec.name, blocking: true, ...spec.build(ctx) };
  } catch (error) {
    // El reporte nunca falla por una salida inesperada.
    console.error(error);
    return {
      name: spec.name,
      blocking: true,
      status: outcome === FAILURE ? Status.FAILED : Status.PASSED,
      summary: "No se pudo leer el detalle (ver el log)",
    };
  }
}

export interface RunMeta {
  commit: string | null;
  runUrl: string | null;
  duration: string | null;
  setupFailed: boolean;
  skipped: boolean;
}

export function runMeta(env: Record<string, string | undefined>, now: number): RunMeta {
  const sha = (env.CI_COMMIT_SHA || env.GITHUB_SHA || "").trim().toLowerCase();
  const server = env.GITHUB_SERVER_URL ?? "";
  const repository = env.GITHUB_REPOSITORY ?? "";
  const runId = env.GITHUB_RUN_ID ?? "";
  let runUrl: string | null = null;
  if (SERVER_URL.test(server) && REPOSITORY.test(repository) && DIGITS.test(runId)) {
    runUrl = `${server}/${repository}/actions/runs/${runId}`;
    const attempt = env.GITHUB_RUN_ATTEMPT ?? "";
    if (DIGITS.test(attempt) && attempt !== "1") runUrl += `/attempts/${attempt}`;
  }
  const started = env.CI_STARTED_AT ?? "";
  const skipped = env.CI_SKIPPED === "true";
  return {
    commit: COMMIT_SHA.test(sha) ? sha.slice(0, 7) : null,
    runUrl,
    duration: DIGITS.test(started) ? formatDuration(now - Number(started)) : null,
    setupFailed: !skipped && [FAILURE, "skipped"].includes(env.OUTCOME_INSTALL ?? ""),
    skipped,
  };
}

export function headline(results: CheckResult[], meta: RunMeta): string {
  if (meta.skipped) return `${Status.SKIPPED} Sin cambios en el frontend`;
  const blocking = results.filter((r) => r.blocking);
  const total = blocking.length;
  const count = (s: Status) => blocking.filter((r) => r.status === s).length;
  const failed = count(Status.FAILED);
  const skipped = count(Status.SKIPPED);
  const warned = results.filter((r) => r.status === Status.WARNING).length;
  const parts = [];
  if (meta.setupFailed) parts.push(`${Status.FAILED} Falló la preparación del entorno`);
  if (failed) parts.push(`${Status.FAILED} ${failed} de ${total} fallaron`);
  else if (!meta.setupFailed) parts.push(`${Status.PASSED} ${total - skipped} de ${total} pasaron`);
  if (skipped) parts.push(`${Status.SKIPPED} ${skipped} no corrieron`);
  if (warned) parts.push(`${Status.WARNING} ${warned} con advertencias`);
  return parts.join(" · ");
}

function renderDetail(detail: Detail, lineLimit: number, runUrl: string | null): string {
  const lines: string[] = [];
  let shown = 0;
  for (const entry of detail.entries) {
    const entryLines = entry.split(/\r?\n/).map(cleanLine);
    const room = lineLimit - lines.length;
    if (room <= 0 || (lines.length && entryLines.length > room)) break;
    lines.push(...entryLines.slice(0, room));
    shown += 1;
  }
  const remaining = detail.entries.length - shown + (detail.hidden ?? 0);
  const parts = [`<details><summary>${htmlText(detail.title)}</summary>`, "", codeBlock(lines)];
  if (remaining) {
    parts.push("", `… y ${remaining} más${runUrl ? ` · [log completo](${runUrl})` : ""}`);
  }
  parts.push("", "</details>");
  return parts.join("\n");
}

/** Primero los tests que fallan, como en el reporte del backend. */
function detailOrder(result: CheckResult): number {
  return result.name === TESTS ? 0 : 1;
}

export function render(results: CheckResult[], meta: RunMeta, lineLimit: number | null): string {
  if (meta.skipped) return [MARKER, `## ${TITLE} · ${SKIPPED_LINE}`, ""].join("\n");
  const out = [MARKER, `## ${TITLE} · ${headline(results, meta)}`];
  const metaParts = [];
  if (meta.commit) metaParts.push(`Commit \`${meta.commit}\``);
  if (meta.runUrl) metaParts.push(`[Ver run](${meta.runUrl})`);
  if (meta.duration) metaParts.push(meta.duration);
  if (metaParts.length) out.push(metaParts.join(" · "));
  out.push("", "| Verificación | Estado | Detalle |", "| --- | --- | --- |");
  for (const r of results) out.push(`| ${r.name} | ${r.status} | ${mdInline(r.summary)} |`);
  const withDetails = results.filter((r) => r.details?.length);
  if (withDetails.length && lineLimit === null) {
    out.push("", DETAILS_OMITTED);
  } else if (lineLimit !== null) {
    for (const r of [...withDetails].sort((a, b) => detailOrder(a) - detailOrder(b))) {
      for (const d of r.details ?? []) out.push("", renderDetail(d, lineLimit, meta.runUrl));
    }
  }
  return `${out.join("\n")}\n`;
}

function coverageMin(env: Record<string, string | undefined>): number {
  const value = Number.parseFloat(env.CI_COVERAGE_MIN ?? "");
  return Number.isFinite(value) ? value : DEFAULT_COVERAGE_MIN;
}

export function makeContext(env: Record<string, string | undefined>, baseDir: string): Context {
  const outcomes: Record<string, string> = {};
  for (const key of OUTCOME_KEYS) {
    outcomes[key] = (env[`OUTCOME_${key.toUpperCase()}`] ?? "").trim().toLowerCase();
  }
  return {
    reportDir: resolve(baseDir, env.CI_REPORT_DIR || DEFAULT_REPORT_DIR),
    outcomes,
    coverageMin: coverageMin(env),
    baseDir,
    repoDir: env.GITHUB_WORKSPACE ? resolve(env.GITHUB_WORKSPACE) : dirname(baseDir),
  };
}

export function buildReport(
  env: Record<string, string | undefined>,
  baseDir: string,
  now: number,
): { markdown: string; ctx: Context } {
  const ctx = makeContext(env, baseDir);
  const meta = runMeta(env, now);
  const results = CHECKS.map((spec) => runCheck(spec, ctx, meta.skipped));
  for (const limit of DETAIL_LINE_LIMITS) {
    const markdown = render(results, meta, limit);
    if (markdown.length <= MAX_REPORT_CHARS) return { markdown, ctx };
  }
  return { markdown: render(results, meta, null), ctx };
}

function fallbackReport(): string {
  return (
    `${MARKER}\n` +
    `## ${TITLE} · ${Status.WARNING} No se pudo generar el reporte\n\n` +
    "El script del reporte falló; el detalle está en el log del run. " +
    "El check obligatorio no depende de este comentario.\n"
  );
}

// --- Anotaciones de GitHub -----------------------------------------------------------------

function escapeData(text: string): string {
  return text.replace(/%/g, "%25").replace(/\r/g, "%0D").replace(/\n/g, "%0A");
}

function escapeProperty(text: string): string {
  return escapeData(text).replace(/:/g, "%3A").replace(/,/g, "%2C");
}

/** Comandos `::error`/`::warning` para anotar ESLint y TypeScript en "Files changed". */
export function annotations(ctx: Context): string[] {
  const out: string[] = [];
  const add = (
    level: "error" | "warning",
    path: string,
    line: number,
    col: number,
    title: string,
    message: string,
  ) => {
    if (out.length >= MAX_ANNOTATIONS) return;
    const file = escapeProperty(repoPath(ctx, path));
    out.push(
      `::${level} file=${file},line=${line},col=${col},title=${escapeProperty(title)}::${escapeData(message)}`,
    );
  };
  // Solo TypeScript: tsc imprime rutas relativas a frontend/ y el *matcher* `tsc` de
  // setup-node no las encontraría; ESLint (stylish) imprime rutas absolutas y su *matcher*
  // sí las anota, así que aquí no se repiten.
  for (const e of loadTypeScript(readText(ctx, "tsc.txt"))) {
    add("error", e.path, e.line, e.column, `TypeScript (${e.code})`, e.message);
  }
  return out;
}

// --- Paso "Cobertura" ----------------------------------------------------------------------

/** Compara el total de líneas con el mínimo. Devuelve el código de salida del paso. */
export function checkCoverageStep(
  env: Record<string, string | undefined>,
  baseDir: string,
): number {
  const ctx = makeContext(env, baseDir);
  const data = loadCoverage(ctx);
  if (!data) {
    console.error("Cobertura: no hay coverage/coverage-summary.json");
    return 1;
  }
  const ok = data.lines >= ctx.coverageMin;
  console.log(
    `Cobertura de líneas: ${formatPercent(data.lines)} (mínimo ${formatMinimum(ctx.coverageMin)})` +
      ` · ramas ${formatPercent(data.branches)} · funciones ${formatPercent(data.functions)}`,
  );
  if (!ok) console.error("Cobertura por debajo del mínimo.");
  return ok ? 0 : 1;
}

// --- Entrada -------------------------------------------------------------------------------

export function main(
  argv: string[] = process.argv.slice(2),
  env: Record<string, string | undefined> = process.env,
  now: number = Date.now() / 1000,
): number {
  const baseDir = process.cwd();
  if (argv.includes("--check-coverage")) return checkCoverageStep(env, baseDir);

  let markdown: string;
  let ctx: Context | null = null;
  try {
    ({ markdown, ctx } = buildReport(env, baseDir, now));
  } catch (error) {
    // El script nunca hace fallar el job.
    console.error(error);
    markdown = fallbackReport();
  }
  const reportDir = ctx?.reportDir ?? resolve(baseDir, env.CI_REPORT_DIR || DEFAULT_REPORT_DIR);
  try {
    mkdirSync(reportDir, { recursive: true });
    writeFileSync(join(reportDir, REPORT_FILE), markdown, "utf8");
    if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, markdown, "utf8");
  } catch (error) {
    console.error(error);
  }
  if (ctx) {
    try {
      for (const line of annotations(ctx)) console.log(line);
    } catch (error) {
      console.error(error);
    }
  }
  console.log(`ci-report: reporte escrito en ${join(reportDir, REPORT_FILE)}`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === import.meta.filename) {
  process.exitCode = main();
}
