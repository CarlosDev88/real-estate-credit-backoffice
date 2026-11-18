// @vitest-environment node
// Regla del design system: en `src/` no se escriben colores a mano. Los colores salen de los
// tokens (`bg-bg-surface`, `var(--um-*)`, `lightTheme`/`darkTheme`), generados en
// design/generated/. Esta prueba falla si aparece un hexadecimal, `rgb()` o `hsl()`.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(import.meta.dirname, "..");

/**
 * Archivos donde un color escrito es válido. Cada entrada, con su motivo. Agregar una aquí
 * es una decisión del dueño de `components/ui`, no un atajo.
 */
const ALLOWED: { pattern: RegExp; why: string }[] = [
  { pattern: /\.test\.tsx?$/, why: "datos de prueba (por ejemplo, el lector de tokens)" },
  { pattern: /^lib\/api\/schema\.d\.ts$/, why: "generado desde el contrato de la API" },
];

const EXTENSIONS = /\.(ts|tsx|css|mdx)$/;
// `#abc`, `#aabbcc`, `#aabbccdd` (no `&#123;` de MDX ni anclas como `#contenido`), `rgb(`, `rgba(`, `hsl(`.
const COLOR = /(?<![&\w/-])#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})\b|\b(?:rgba?|hsla?)\(/gi;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : EXTENSIONS.test(name) ? [path] : [];
  });
}

export function findHardcodedColors(source: string): { line: number; match: string }[] {
  return source
    .split("\n")
    .flatMap((text, index) =>
      [...text.matchAll(COLOR)].map((m) => ({ line: index + 1, match: m[0] })),
    );
}

describe("colores escritos a mano en src/", () => {
  it("la expresión encuentra hex, rgb() y hsl(), y no anclas ni entidades", () => {
    expect(findHardcodedColors('className="bg-[#1f4e91]"').map((f) => f.match)).toEqual([
      "#1f4e91",
    ]);
    expect(findHardcodedColors("fill: rgba(0, 0, 0, 0.5); color: hsl(210 50% 40%)")).toHaveLength(
      2,
    );
    expect(findHardcodedColors('stroke="#fff"')).toHaveLength(1);
    expect(findHardcodedColors('<a href="#contenido">')).toEqual([]);
    expect(findHardcodedColors("blocks=&#123;[]&#125;")).toEqual([]);
    expect(findHardcodedColors("SOL-#12 · var(--um-bg-surface)")).toEqual([]);
  });

  it("no hay colores fuera de los archivos permitidos", () => {
    const found: string[] = [];
    for (const path of files(SRC)) {
      const rel = relative(SRC, path).split(sep).join("/");
      if (ALLOWED.some((allowed) => allowed.pattern.test(rel))) continue;
      for (const { line, match } of findHardcodedColors(readFileSync(path, "utf8"))) {
        found.push(`src/${rel}:${line}  ${match}`);
      }
    }
    // Usa un token (design/README.md, "Reglas"). Si de verdad falta uno, se agrega en
    // design/tokens/tokens.json y se regenera con `node design/scripts/build-tokens.mjs`.
    expect(found).toEqual([]);
  });
});
