// @vitest-environment node
import { mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  annotations,
  buildReport,
  checkCoverageStep,
  codeBlock,
  diffContract,
  main,
  makeContext,
  MARKER,
  mdInline,
  parseJUnit,
} from "./ci-report.ts";

const FIXTURES = resolve(import.meta.dirname, "__fixtures__");
// Rutas de los fixtures (eslint.json y coverage-summary.json) relativas a esta carpeta.
const BASE_DIR = resolve("/repo/frontend");
const NOW = 1_800_000_000;

const ALL_SUCCESS = {
  OUTCOME_INSTALL: "success",
  OUTCOME_ESLINT: "success",
  OUTCOME_PRETTIER: "success",
  OUTCOME_TYPECHECK: "success",
  OUTCOME_TESTS: "success",
  OUTCOME_COVERAGE: "success",
  OUTCOME_API_CONTRACT: "success",
  OUTCOME_BUILD: "success",
};

const RUN_ENV = {
  CI_COMMIT_SHA: "abcdef1234567890abcdef1234567890abcdef12",
  GITHUB_SERVER_URL: "https://github.com",
  GITHUB_REPOSITORY: "acme/mvp-backoffice",
  GITHUB_RUN_ID: "123",
  CI_STARTED_AT: String(NOW - 134),
};

function report(dir: string, env: Record<string, string>) {
  return buildReport({ CI_REPORT_DIR: join(FIXTURES, dir), ...RUN_ENV, ...env }, BASE_DIR, NOW)
    .markdown;
}

const tempDirs: string[] = [];
function tempDir(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "ci-report-"));
  tempDirs.push(dir);
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(join(dir, name, ".."), { recursive: true });
    writeFileSync(join(dir, name), content);
  }
  return dir;
}

afterEach(() => {
  for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  vi.restoreAllMocks();
});

describe("todo en verde", () => {
  it("encabezado, enlace al run, duración y 7 filas en ✅", () => {
    const md = report("green", ALL_SUCCESS);
    expect(md.startsWith(`${MARKER}\n## Frontend CI · ✅ 7 de 7 pasaron\n`)).toBe(true);
    expect(md).toContain(
      "Commit `abcdef1` · [Ver run](https://github.com/acme/mvp-backoffice/actions/runs/123) · 2 min 14 s",
    );
    expect(md).toContain("| ESLint | ✅ | Sin errores |");
    expect(md).toContain("| Prettier (formato) | ✅ | Sin cambios pendientes |");
    expect(md).toContain("| TypeScript | ✅ | Sin errores |");
    expect(md).toContain("| Tests | ✅ | 3 pasan · 0 fallan · 0 saltados (3 en 13 s) |");
    expect(md).toContain("| Cobertura | ✅ | 81,20 % (mínimo 70 %) |");
    expect(md).toContain("| Contrato API | ✅ | Al día |");
    expect(md).toContain("| Build | ✅ | Compiló |");
    expect(md).not.toContain("<details>");
  });
});

describe("fallos y warnings juntos", () => {
  const env = {
    ...ALL_SUCCESS,
    OUTCOME_ESLINT: "failure",
    OUTCOME_PRETTIER: "failure",
    OUTCOME_TYPECHECK: "failure",
    OUTCOME_TESTS: "failure",
    OUTCOME_COVERAGE: "failure",
    OUTCOME_API_CONTRACT: "failure",
    OUTCOME_BUILD: "failure",
  };
  const md = report("failing", env);

  it("encabezado y filas", () => {
    expect(md).toContain("## Frontend CI · ❌ 7 de 7 fallaron\n");
    expect(md).toContain("| ESLint | ❌ | 2 errores · 1 advertencia en 2 archivos |");
    expect(md).toContain("| Prettier (formato) | ❌ | 2 archivos sin formatear |");
    expect(md).toContain("| TypeScript | ❌ | 2 errores en 2 archivos |");
    expect(md).toContain("| Tests | ❌ | 1 pasa · 2 fallan · 1 saltado (4 en 1 min 15 s) |");
    expect(md).toContain("| Cobertura | ❌ | 65,20 % · mínimo 70 % · con tests fallidos |");
    expect(md).toContain(
      "| Contrato API | ❌ | Desactualizado: 1 ruta nueva · 1 ruta quitada · 1 ruta cambiada · " +
        "1 esquema nuevo · 1 esquema quitado · 2 esquemas cambiados |",
    );
    expect(md).toContain("| Build | ❌ | No compiló |");
  });

  it("los tests que fallan van primero, con su primera línea", () => {
    const testsAt = md.indexOf("<summary>Tests que fallan (2)</summary>");
    expect(testsAt).toBeGreaterThan(md.indexOf("| Build |"));
    expect(testsAt).toBeLessThan(md.indexOf("<summary>ESLint"));
    expect(md).toContain(
      "src/lib/api/fetch.test.ts › refresh > dos 401 a la vez hacen un solo refresh\n" +
        "    expected 3 to be 4 // Object.is equality",
    );
    expect(md).toContain('refresh > con "comillas" & <html>\n    Error: CORS');
  });

  it("detalle de ESLint por regla, con archivo y línea relativos a frontend/", () => {
    expect(md).toContain(
      "<summary>ESLint: 2 errores · 1 advertencia (@typescript-eslint/no-floating-promises: 2, react-hooks/exhaustive-deps: 1)</summary>",
    );
    expect(md).toContain(
      "error  @typescript-eslint/no-floating-promises  src/features/auth/login-form.tsx:42:5  Promises must be awaited.",
    );
    expect(md).toContain(
      "aviso  react-hooks/exhaustive-deps  src/features/auth/login-form.tsx:30:6",
    );
  });

  it("Prettier, TypeScript, cobertura, contrato y build", () => {
    expect(md).toContain("src/components/ui/money.tsx\nsrc/lib/format/index.ts");
    expect(md).toContain("src/lib/api/session.ts:142:3  [TS2322] Type 'Promise<boolean> | null'");
    expect(md).toContain("Líneas 65,20 % · ramas 62,50 % · funciones 60,00 %");
    expect(md).toContain("  0,00 %  src/components/ui/app-shell.tsx (120 líneas)");
    expect(md).not.toContain("navigation/types.ts");
    expect(md).toContain("+ POST /api/v1/new\n- GET /api/v1/old\n~ GET /api/v1/auth/me");
    expect(md).toContain("~ esquema Me\n~ esquema Status");
    expect(md).toContain(
      "<summary>Contrato API: diff de schema.d.ts (primeras 50 líneas)</summary>",
    );
    expect(md).toContain("<summary>Build: últimas 50 líneas</summary>");
    expect(md).toContain("Type error: Property 'x' does not exist on type 'Y'.");
    expect(md).not.toContain("line 31 of the build log");
  });

  it("ESLint solo con warnings es ⚠️ y no cuenta como fallo", () => {
    const dir = tempDir({
      "eslint.json": JSON.stringify([
        {
          filePath: "/repo/frontend/src/a.ts",
          messages: [{ ruleId: "x/y", severity: 1, message: "ojo", line: 1, column: 1 }],
        },
      ]),
    });
    const { markdown } = buildReport(
      { ...ALL_SUCCESS, CI_REPORT_DIR: dir, OUTCOME_TESTS: "skipped", OUTCOME_COVERAGE: "" },
      BASE_DIR,
      NOW,
    );
    expect(markdown).toContain("| ESLint | ⚠️ | 1 advertencia en 1 archivo |");
    expect(markdown).toContain(
      "## Frontend CI · ✅ 5 de 7 pasaron · ⏭️ 2 no corrieron · ⚠️ 1 con advertencias",
    );
  });
});

describe("pasos que no corrieron", () => {
  it("falló la instalación: todo ⏭️", () => {
    const md = report("green", {
      OUTCOME_INSTALL: "failure",
      OUTCOME_ESLINT: "skipped",
      OUTCOME_PRETTIER: "skipped",
      OUTCOME_TYPECHECK: "skipped",
      OUTCOME_TESTS: "skipped",
      OUTCOME_COVERAGE: "",
      OUTCOME_API_CONTRACT: "skipped",
      OUTCOME_BUILD: "cancelled",
    });
    expect(md).toContain(
      "## Frontend CI · ❌ Falló la preparación del entorno · ⏭️ 7 no corrieron\n",
    );
    expect(md).toContain("| Cobertura | ⏭️ | No corrió |");
    expect(md).toContain("| Build | ⏭️ | Cancelado |");
  });

  it("cobertura sin datos cuando los tests sí corrieron", () => {
    const md = report("green", { ...ALL_SUCCESS, OUTCOME_COVERAGE: "" });
    expect(md).toContain("| Cobertura | ⏭️ | Sin datos de cobertura |");
  });

  it("CI_SKIPPED: una sola línea", () => {
    const md = report("green", { CI_SKIPPED: "true" });
    expect(md).toBe(
      `${MARKER}\n## Frontend CI · ⏭️ Sin cambios en el frontend: verificaciones omitidas\n`,
    );
  });
});

describe("límites y escape", () => {
  it("una salida larga se trunca con '… y N más' y el enlace al log", () => {
    const tsc = Array.from(
      { length: 120 },
      (_, i) => `src/f${i}.ts(1,1): error TS2322: Error número ${i}`,
    ).join("\n");
    const dir = tempDir({ "tsc.txt": tsc });
    const { markdown } = buildReport(
      { ...ALL_SUCCESS, ...RUN_ENV, CI_REPORT_DIR: dir, OUTCOME_TYPECHECK: "failure" },
      BASE_DIR,
      NOW,
    );
    expect(markdown).toContain("| TypeScript | ❌ | 120 errores en 120 archivos |");
    expect(markdown).toContain("src/f49.ts:1:1  [TS2322] Error número 49");
    expect(markdown).not.toContain("src/f50.ts:1:1");
    expect(markdown).toContain(
      "… y 70 más · [log completo](https://github.com/acme/mvp-backoffice/actions/runs/123)",
    );
  });

  it("un reporte enorme baja el límite de líneas hasta caber en 60 000 caracteres", () => {
    const long = "x".repeat(190);
    const tsc = Array.from({ length: 400 }, (_, i) => `src/f${i}.ts(1,1): error TS1: ${long}`).join(
      "\n",
    );
    const prettier = Array.from({ length: 400 }, (_, i) => `[warn] src/${long}${i}.ts`).join("\n");
    const dir = tempDir({ "tsc.txt": tsc, "prettier.txt": prettier });
    const { markdown } = buildReport(
      {
        ...ALL_SUCCESS,
        CI_REPORT_DIR: dir,
        OUTCOME_TYPECHECK: "failure",
        OUTCOME_PRETTIER: "failure",
      },
      BASE_DIR,
      NOW,
    );
    expect(markdown.length).toBeLessThanOrEqual(60_000);
  });

  it("escapa Markdown y HTML en la tabla y alarga la cerca de los bloques", () => {
    expect(mdInline("a|b <script> `x` *y* ")).toBe("a\\|b &lt;script&gt; \\`x\\` \\*y\\*");
    expect(mdInline("línea 1\nlínea 2")).toBe("línea 1 línea 2");
    expect(codeBlock(["texto con ```` comillas"])).toBe("`````\ntexto con ```` comillas\n`````");
  });

  it("la salida de una herramienta solo va dentro de bloques de código", () => {
    // El comentario se busca por el marcador al principio; dentro de un bloque de código
    // GitHub muestra el texto literal (igual que en el reporte del backend).
    const dir = tempDir({
      "prettier.txt": `[warn] src/<!-- ci-report:frontend -->.ts\n[error] <img src=x onerror=alert(1)>`,
      "tsc.txt": "src/a.ts(1,1): error TS1: <b>|x|</b>",
    });
    const { markdown } = buildReport(
      {
        ...ALL_SUCCESS,
        CI_REPORT_DIR: dir,
        OUTCOME_PRETTIER: "failure",
        OUTCOME_TYPECHECK: "failure",
      },
      BASE_DIR,
      NOW,
    );
    expect(markdown.startsWith(`${MARKER}\n`)).toBe(true);
    const outsideCode = markdown.replace(/^```[\s\S]*?^```$/gm, "");
    expect(outsideCode.split(MARKER)).toHaveLength(2);
    expect(outsideCode).not.toContain("<img");
    expect(outsideCode).not.toContain("<b>");
    expect(markdown).toContain("[error] <img src=x onerror=alert(1)>");
  });

  it("si un archivo está corrupto, la fila lo dice y el reporte sale igual", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const dir = tempDir({ "eslint.json": "{no es json" });
    const { markdown } = buildReport(
      { ...ALL_SUCCESS, CI_REPORT_DIR: dir, OUTCOME_ESLINT: "failure" },
      BASE_DIR,
      NOW,
    );
    expect(markdown).toContain("| ESLint | ❌ | No se pudo leer el detalle (ver el log) |");
  });
});

describe("--check-coverage", () => {
  it("por encima del mínimo sale con 0", () => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    const env = { CI_REPORT_DIR: join(FIXTURES, "green"), CI_COVERAGE_MIN: "70" };
    expect(checkCoverageStep(env, BASE_DIR)).toBe(0);
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining("81,20 % (mínimo 70 %)"));
  });

  it("por debajo del mínimo, o sin datos, sale con 1", () => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(checkCoverageStep({ CI_REPORT_DIR: join(FIXTURES, "failing") }, BASE_DIR)).toBe(1);
    expect(checkCoverageStep({ CI_REPORT_DIR: tempDir({}) }, BASE_DIR)).toBe(1);
  });
});

describe("piezas sueltas", () => {
  it("parseJUnit cuenta pasan, fallan y saltados", () => {
    const run = parseJUnit(readFileSync(join(FIXTURES, "failing", "vitest.xml"), "utf8"));
    expect(run).toMatchObject({ total: 4, passed: 1, failing: 2, skipped: 1, duration: 75.25 });
  });

  it("diffContract no ve cambios entre un archivo y sí mismo", () => {
    const real = readFileSync(resolve(import.meta.dirname, "../src/lib/api/schema.d.ts"), "utf8");
    expect(diffContract(real, real)).toEqual({
      routesAdded: [],
      routesRemoved: [],
      routesChanged: [],
      schemasAdded: [],
      schemasRemoved: [],
      schemasChanged: [],
    });
  });

  it("anota los errores de TypeScript con la ruta desde la raíz del repo", () => {
    const ctx = makeContext(
      { CI_REPORT_DIR: join(FIXTURES, "failing"), GITHUB_WORKSPACE: resolve("/repo") },
      BASE_DIR,
    );
    expect(annotations(ctx)).toEqual([
      expect.stringMatching(
        /^::error file=frontend\/src\/components\/ui\/money\.tsx,line=48,col=58,title=TypeScript \(TS2367\)::This comparison/,
      ),
      expect.stringMatching(/^::error file=frontend\/src\/lib\/api\/session\.ts,line=142,col=3,/),
    ]);
  });

  it("main escribe report.md y el resumen del run, y nunca falla", () => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    const dir = tempDir({});
    const summary = join(dir, "summary.md");
    const code = main(
      [],
      { ...ALL_SUCCESS, CI_REPORT_DIR: dir, GITHUB_STEP_SUMMARY: summary },
      NOW,
    );
    expect(code).toBe(0);
    expect(readFileSync(join(dir, "report.md"), "utf8")).toContain(MARKER);
    expect(readFileSync(summary, "utf8")).toContain("| Build | ✅ | Compiló |");
  });
});
