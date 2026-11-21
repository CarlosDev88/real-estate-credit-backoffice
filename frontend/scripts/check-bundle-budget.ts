/**
 * Presupuesto de JS de primera carga por ruta (auditoría de performance, Parte 3).
 *
 * Lee la salida de `next build` (`.next/diagnostics/route-bundle-stats.json`: los chunks de
 * primera carga de cada ruta), suma el gzip (nivel 9) de esos chunks y lo compara con
 * `performance-budget.json`. Next 16 con Turbopack ya no imprime "First Load JS" en la tabla
 * del build: este número es el mismo que se midió en la auditoría (`docs/PERFORMANCE.md`).
 *
 * Corre con Node 24 sin compilar y sin dependencias (`node:fs`, `node:path`, `node:zlib`):
 *
 *   node scripts/check-bundle-budget.ts            compara; sale con 1 si una ruta se pasa
 *   node scripts/check-bundle-budget.ts --update   reescribe el presupuesto con lo medido
 *                                                  + 10 %, redondeado hacia arriba a 5 kB
 *
 * Con `CI_REPORT_DIR`, deja `bundle-budget.json` para el reporte del CI.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import process from "node:process";
import { constants, gzipSync } from "node:zlib";

export const STATS_FILE = ".next/diagnostics/route-bundle-stats.json";
export const BUDGET_FILE = "performance-budget.json";
export const RESULT_FILE = "bundle-budget.json";
/** Margen sobre lo medido y redondeo del presupuesto (spec §5.1). */
export const MARGIN = 0.1;
export const ROUND_TO_KB = 5;
const KB = 1024;

export interface RouteStat {
  route: string;
  firstLoadChunkPaths: string[];
}

export interface Budget {
  /** Siempre "kB gzip (nivel 9)": lo que suma este script. */
  unit: string;
  margin: string;
  routes: Record<string, number>;
}

export interface RouteResult {
  route: string;
  /** Primera carga medida, en kB gzip (un decimal). */
  kb: number;
  /** Presupuesto en kB, o `null` si la ruta no tiene. */
  budget: number | null;
  status: "ok" | "over" | "missing";
}

export interface BudgetResult {
  ok: boolean;
  routes: RouteResult[];
  /** Rutas del presupuesto que ya no existen en el build (aviso, no falla). */
  stale: string[];
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/** kB gzip de la primera carga de cada ruta. `readChunk` recibe la ruta tal como la da Next. */
export function measureRoutes(
  stats: RouteStat[],
  readChunk: (path: string) => Buffer,
): Map<string, number> {
  const cache = new Map<string, number>();
  const gzipped = (path: string) => {
    const key = path.replaceAll("\\", "/");
    let size = cache.get(key);
    if (size === undefined) {
      size = gzipSync(readChunk(key), { level: constants.Z_BEST_COMPRESSION }).length;
      cache.set(key, size);
    }
    return size;
  };
  const sizes = new Map<string, number>();
  for (const stat of stats) {
    const bytes = stat.firstLoadChunkPaths.reduce((sum, path) => sum + gzipped(path), 0);
    sizes.set(stat.route, round1(bytes / KB));
  }
  return sizes;
}

export function checkBudget(sizes: Map<string, number>, budget: Budget): BudgetResult {
  const routes: RouteResult[] = [...sizes].map(([route, kb]) => {
    const limit = budget.routes[route];
    if (limit === undefined) return { route, kb, budget: null, status: "missing" };
    return { route, kb, budget: limit, status: kb > limit ? "over" : "ok" };
  });
  routes.sort((a, b) => a.route.localeCompare(b.route));
  const stale = Object.keys(budget.routes).filter((route) => !sizes.has(route));
  return { ok: routes.every((r) => r.status === "ok"), routes, stale };
}

/** Lo medido + 10 %, redondeado hacia arriba al múltiplo de 5 kB. */
export function budgetFor(kb: number): number {
  return Math.ceil((kb * (1 + MARGIN)) / ROUND_TO_KB) * ROUND_TO_KB;
}

export function makeBudget(sizes: Map<string, number>): Budget {
  const routes = Object.fromEntries(
    [...sizes].sort(([a], [b]) => a.localeCompare(b)).map(([route, kb]) => [route, budgetFor(kb)]),
  );
  return {
    unit: "kB gzip (nivel 9)",
    margin: "medido + 10 %, redondeado hacia arriba a 5 kB",
    routes,
  };
}

export function formatResult(result: BudgetResult): string[] {
  const lines: string[] = [];
  for (const r of result.routes) {
    if (r.status === "over") {
      lines.push(
        `✗ ${r.route}: ${r.kb} kB, presupuesto ${r.budget} kB (se pasa por ${round1(r.kb - (r.budget ?? 0))} kB)`,
      );
    } else if (r.status === "missing") {
      lines.push(`✗ ${r.route}: ${r.kb} kB, sin presupuesto en ${BUDGET_FILE}`);
    }
  }
  for (const route of result.stale)
    lines.push(`! ${route}: está en ${BUDGET_FILE} pero no en el build`);
  const okCount = result.routes.filter((r) => r.status === "ok").length;
  lines.push(
    result.ok
      ? `Presupuesto de bundle: ${okCount} rutas dentro del presupuesto.`
      : `Presupuesto de bundle: ${result.routes.length - okCount} de ${result.routes.length} rutas fuera.` +
          ` Si el aumento es a propósito, corre \`node scripts/check-bundle-budget.ts --update\`` +
          ` y explica el número en el PR.`,
  );
  return lines;
}

export function run(
  baseDir: string,
  argv: string[],
  env: Record<string, string | undefined>,
): number {
  const statsPath = join(baseDir, STATS_FILE);
  if (!existsSync(statsPath)) {
    console.error(`No está ${STATS_FILE}: corre \`pnpm build\` antes.`);
    return 1;
  }
  const stats = JSON.parse(readFileSync(statsPath, "utf8")) as RouteStat[];
  const sizes = measureRoutes(stats, (path) => readFileSync(resolve(baseDir, path)));
  const budgetPath = join(baseDir, BUDGET_FILE);

  if (argv.includes("--update")) {
    writeFileSync(budgetPath, `${JSON.stringify(makeBudget(sizes), null, 2)}\n`);
    console.log(`Presupuesto reescrito en ${BUDGET_FILE} (${sizes.size} rutas).`);
    return 0;
  }

  const budget = JSON.parse(readFileSync(budgetPath, "utf8")) as Budget;
  const result = checkBudget(sizes, budget);
  for (const line of formatResult(result)) console.log(line);
  if (env.CI_REPORT_DIR) {
    const dir = resolve(baseDir, env.CI_REPORT_DIR);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, RESULT_FILE), JSON.stringify(result, null, 2));
  }
  return result.ok ? 0 : 1;
}

if (process.argv[1] && resolve(process.argv[1]) === import.meta.filename) {
  process.exitCode = run(process.cwd(), process.argv.slice(2), process.env);
}
