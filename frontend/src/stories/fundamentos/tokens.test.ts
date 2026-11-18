import { toneFor } from "@design/status-tones";
import { describe, expect, it } from "vitest";

import {
  palettes,
  parseStatusTones,
  parseTokensCss,
  scale,
  semanticColorGroups,
  shadows,
  statusTones,
  tailwindClass,
  tailwindColorNames,
  tailwindColors,
  TONE_ORDER,
  tokenName,
  tokens,
  toneUses,
  parseToneUses,
  typeScale,
} from "./tokens";

const SAMPLE = `/* comentario { con llaves } */
:root {
  --um-color-blue-50: #EEF4FB;
  --um-color-neutral-0: #FFFFFF;
  --um-space-2: 8px;
  --um-text-md: 14px;
  --um-leading-md: 22px;
}
:root,
[data-theme="light"] {
  color-scheme: light;
  --um-bg-canvas: #F4F6F8;
  --um-tone-danger-on-solid: #FFFFFF;
  --um-shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.06);
}
[data-theme="dark"] {
  --um-bg-canvas: #0D1117;
  --um-tone-danger-on-solid: #FFFFFF;
  --um-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
}`;

describe("parseTokensCss", () => {
  const parsed = parseTokensCss(SAMPLE);

  it("separa base, claro y oscuro, sin el prefijo --um-", () => {
    expect(parsed.base.get("space-2")).toBe("8px");
    expect(parsed.light.get("bg-canvas")).toBe("#F4F6F8");
    expect(parsed.dark.get("bg-canvas")).toBe("#0D1117");
    expect(parsed.light.has("color-scheme")).toBe(false);
  });

  it("agrupa colores semánticos con su valor en los dos temas y deja las sombras aparte", () => {
    expect(semanticColorGroups(parsed)).toEqual([
      {
        id: "bg",
        tokens: [{ token: "bg.canvas", cssVar: "um-bg-canvas", light: "#F4F6F8", dark: "#0D1117" }],
      },
      {
        id: "tone",
        tokens: [
          {
            token: "tone.danger.onSolid",
            cssVar: "um-tone-danger-on-solid",
            light: "#FFFFFF",
            dark: "#FFFFFF",
          },
        ],
      },
    ]);
    expect(shadows(parsed)).toEqual([
      {
        token: "shadow.sm",
        cssVar: "um-shadow-sm",
        light: "0 1px 2px rgba(16, 24, 40, 0.06)",
        dark: "0 1px 2px rgba(0, 0, 0, 0.4)",
      },
    ]);
  });

  it("paletas por familia, escalas y tipografía con su interlineado", () => {
    expect(palettes(parsed).map((p) => p.family)).toEqual(["blue", "neutral"]);
    expect(scale(parsed, "space")).toEqual([{ step: "2", cssVar: "um-space-2", value: "8px" }]);
    expect(typeScale(parsed)).toEqual([
      {
        step: "md",
        cssVar: "um-text-md",
        value: "14px",
        leading: "22px",
        leadingVar: "um-leading-md",
      },
    ]);
  });
});

describe("tokenName", () => {
  it("convierte la variable CSS en el nombre de tokens.json", () => {
    expect(tokenName("bg-canvas")).toBe("bg.canvas");
    expect(tokenName("brand-primary-hover")).toBe("brand.primaryHover");
    expect(tokenName("text-on-sidebar-strong")).toBe("text.onSidebarStrong");
    expect(tokenName("sidebar-item-hover")).toBe("sidebar.itemHover");
    expect(tokenName("tone-info-fg")).toBe("tone.info.fg");
    expect(tokenName("tone-danger-on-solid")).toBe("tone.danger.onSolid");
  });
});

describe("tailwindClass y parseToneUses", () => {
  const available = tailwindColors(
    "--color-bg-canvas: x;\n--color-text-link: x;\n--color-tone-info-fg: x;\n--color-tone-info-border: x;\n--color-tone-danger-on-solid: x;\n--color-focus-ring: x;\n--color-sidebar-divider: x;",
  );

  it("elige el prefijo según el uso del color", () => {
    expect(tailwindClass("bg-canvas", available)).toBe("bg-bg-canvas");
    expect(tailwindClass("text-link", available)).toBe("text-text-link");
    expect(tailwindClass("tone-info-fg", available)).toBe("text-tone-info-fg");
    expect(tailwindClass("tone-info-border", available)).toBe("border-tone-info-border");
    expect(tailwindClass("tone-danger-on-solid", available)).toBe("text-tone-danger-on-solid");
    expect(tailwindClass("focus-ring", available)).toBe("outline-focus-ring");
    expect(tailwindClass("sidebar-divider", available)).toBe("border-sidebar-divider");
    expect(tailwindClass("brand-primary", available)).toBeNull();
  });

  it("lee la tabla de la sección Estados", () => {
    const readme =
      "## Otra\n\n| `info` | no |\n\n## Estados\n\n| Tono | Uso |\n| --- | --- |\n| `info` | En proceso. |\n| `raro` | x |\n";
    expect(parseToneUses(readme)).toEqual({ info: "En proceso." });
  });
});

describe("archivos generados reales", () => {
  it("tokens.css: cada color semántico tiene valor en claro y en oscuro", () => {
    const groups = semanticColorGroups(tokens);
    expect(groups.map((g) => g.id)).toEqual(
      expect.arrayContaining(["bg", "border", "text", "brand", "tone"]),
    );
    for (const { tokens: list } of groups) {
      for (const token of list) expect(token.dark, token.token).not.toBe("");
    }
    expect(shadows(tokens).map((s) => s.token)).toEqual(["shadow.sm", "shadow.md", "shadow.lg"]);
    expect(typeScale(tokens).every((step) => step.leading !== "")).toBe(true);
    expect(scale(tokens, "radius").length).toBeGreaterThan(0);
  });

  it("status-tones.ts: el mapa leído coincide con toneFor", () => {
    for (const [kind, codes] of Object.entries(statusTones)) {
      for (const [code, tone] of Object.entries(codes)) {
        expect(toneFor(kind as keyof typeof statusTones, code)).toBe(tone);
      }
    }
    expect(Object.keys(statusTones)).toContain("application");
  });

  it("tailwind-theme.css: cada color semántico tiene su clase", () => {
    for (const { tokens: list } of semanticColorGroups(tokens)) {
      for (const token of list) {
        const cssName = token.cssVar.slice("um-".length);
        expect(tailwindClass(cssName, tailwindColorNames), token.token).not.toBeNull();
      }
    }
  });

  it("README: los seis tonos tienen su uso", () => {
    expect(Object.keys(toneUses).sort()).toEqual([...TONE_ORDER].sort());
  });

  it("status-tones.ts sin el mapa da un error claro", () => {
    expect(() => parseStatusTones("export {}")).toThrow(/TONES/);
  });
});
