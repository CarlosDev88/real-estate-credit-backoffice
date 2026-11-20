import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  budgetFor,
  checkBudget,
  formatResult,
  RESULT_FILE,
  run,
  type Budget,
} from "./check-bundle-budget";

/** Un build de ejemplo: chunks de bytes al azar (no se comprimen) y su manifiesto. */
function fakeBuild(budgetRoutes: Record<string, number>) {
  const dir = mkdtempSync(join(tmpdir(), "bundle-budget-"));
  const chunks = join(dir, ".next/static/chunks");
  mkdirSync(chunks, { recursive: true });
  mkdirSync(join(dir, ".next/diagnostics"), { recursive: true });
  // ~20 kB y ~40 kB gzip: los bytes al azar no se comprimen.
  writeFileSync(join(chunks, "shared.js"), randomBytes(20 * 1024));
  writeFileSync(join(chunks, "big.js"), randomBytes(40 * 1024));
  const stats = [
    { route: "/login", firstLoadChunkPaths: [".next\\static\\chunks\\shared.js"] },
    {
      route: "/solicitudes/[id]",
      firstLoadChunkPaths: [".next\\static\\chunks\\shared.js", ".next\\static\\chunks\\big.js"],
    },
  ];
  writeFileSync(join(dir, ".next/diagnostics/route-bundle-stats.json"), JSON.stringify(stats));
  const budget: Budget = { unit: "kB gzip (nivel 9)", margin: "", routes: budgetRoutes };
  writeFileSync(join(dir, "performance-budget.json"), JSON.stringify(budget));
  return dir;
}

const dirs: string[] = [];
const build = (routes: Record<string, number>) => {
  const dir = fakeBuild(routes);
  dirs.push(dir);
  return dir;
};

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("check-bundle-budget", () => {
  it("pasa con un build dentro del presupuesto y deja el resultado para el reporte", () => {
    const dir = build({ "/login": 25, "/solicitudes/[id]": 65 });
    vi.spyOn(console, "log").mockImplementation(() => {});
    expect(run(dir, [], { CI_REPORT_DIR: "out" })).toBe(0);
    const result = JSON.parse(readFileSync(join(dir, "out", RESULT_FILE), "utf8"));
    expect(result.ok).toBe(true);
    expect(result.routes.map((r: { status: string }) => r.status)).toEqual(["ok", "ok"]);
  });

  it("falla si una ruta se pasa, con la ruta, el valor y el presupuesto", () => {
    const dir = build({ "/login": 25, "/solicitudes/[id]": 50 });
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    expect(run(dir, [], {})).toBe(1);
    const output = log.mock.calls.map(([line]) => String(line)).join("\n");
    expect(output).toMatch(/✗ \/solicitudes\/\[id\]: 6\d\.\d kB, presupuesto 50 kB/);
    expect(output).toContain("1 de 2 rutas fuera");
  });

  it("falla si una ruta del build no tiene presupuesto y avisa de las que sobran", () => {
    const result = checkBudget(
      new Map([
        ["/login", 20],
        ["/nueva", 30],
      ]),
      { unit: "", margin: "", routes: { "/login": 25, "/vieja": 10 } },
    );
    expect(result.ok).toBe(false);
    expect(result.routes.find((r) => r.route === "/nueva")?.status).toBe("missing");
    expect(result.stale).toEqual(["/vieja"]);
    expect(formatResult(result)).toContain(
      "✗ /nueva: 30 kB, sin presupuesto en performance-budget.json",
    );
  });

  it("--update escribe lo medido + 10 %, redondeado hacia arriba a 5 kB", () => {
    const dir = build({});
    vi.spyOn(console, "log").mockImplementation(() => {});
    expect(run(dir, ["--update"], {})).toBe(0);
    const budget = JSON.parse(readFileSync(join(dir, "performance-budget.json"), "utf8"));
    expect(budget.routes).toEqual({ "/login": 25, "/solicitudes/[id]": 70 });
    expect(run(dir, [], {})).toBe(0);
  });

  it("budgetFor redondea hacia arriba al múltiplo de 5", () => {
    expect(budgetFor(298)).toBe(330);
    expect(budgetFor(337.4)).toBe(375);
    expect(budgetFor(10)).toBe(15);
  });
});
