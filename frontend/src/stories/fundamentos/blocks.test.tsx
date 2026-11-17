import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ControlHeights,
  Palettes,
  RadiusScale,
  SemanticColors,
  ShadowRule,
  ShadowScale,
  SpacingScale,
  ToneLegend,
  ToneMapTable,
  ToneRule,
  TypeFamilies,
  TypeScale,
} from "./blocks";
import {
  DataFormatExample,
  DestructiveExample,
  LabelExample,
  LinkExample,
  PrimaryActionExample,
  SentenceCaseExample,
} from "./redaccion";
import { statusTones, tokens } from "./tokens";

// Los bloques se pintan con los archivos generados reales: si un token cambia de nombre o
// desaparece, estas pruebas lo notan.

describe("colores", () => {
  it("cada token semántico con su variable y su valor en los dos temas", () => {
    render(<SemanticColors />);
    const row = screen.getByText("text.secondary").closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText("--um-text-secondary")).toBeInTheDocument();
    expect(cells.getByText("text-text-secondary")).toBeInTheDocument();
    expect(cells.getByText(tokens.light.get("text-secondary") ?? "")).toBeInTheDocument();
    expect(cells.getByText(tokens.dark.get("text-secondary") ?? "")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tonos de estado" })).toBeInTheDocument();
  });

  it("paletas por familia", () => {
    render(<Palettes />);
    expect(screen.getByRole("region", { name: "Paleta blue" })).toBeInTheDocument();
    expect(screen.getByText("blue-600")).toBeInTheDocument();
  });
});

describe("tipografía, espaciado, radios y sombras", () => {
  it("familias con sus pesos y la escala completa", () => {
    render(
      <>
        <TypeFamilies />
        <TypeScale />
      </>,
    );
    expect(screen.getByText("font.sans")).toBeInTheDocument();
    expect(screen.getByText("font.mono")).toBeInTheDocument();
    expect(screen.getByText("text.md")).toBeInTheDocument();
    expect(
      screen.getByText(`${tokens.base.get("text-md")} / ${tokens.base.get("leading-md")}`),
    ).toBeInTheDocument();
  });

  it("espaciado con su equivalencia en Tailwind, alturas de control y radios", () => {
    render(
      <>
        <SpacingScale />
        <ControlHeights />
        <RadiusScale />
      </>,
    );
    expect(screen.getByText("space.4")).toBeInTheDocument();
    expect(screen.getByText("gap-4 · p-4")).toBeInTheDocument();
    expect(screen.getByText("control.height.lg")).toBeInTheDocument();
    expect(screen.getByText("radius.full")).toBeInTheDocument();
  });

  it("sombras en claro y en oscuro, y la regla del flujo", () => {
    render(
      <>
        <ShadowScale />
        <ShadowRule />
      </>,
    );
    const dark = screen.getByRole("region", { name: "Tema oscuro" });
    expect(dark).toHaveAttribute("data-theme", "dark");
    expect(within(dark).getByText(tokens.dark.get("shadow-lg") ?? "")).toBeInTheDocument();
    expect(screen.getByText("Así sí.")).toBeInTheDocument();
    expect(screen.getByText("Así no.")).toBeInTheDocument();
  });
});

describe("tonos de estado", () => {
  it("leyenda con el uso del README y un badge por código", () => {
    render(
      <>
        <ToneLegend />
        <ToneMapTable />
        <ToneRule />
      </>,
    );
    expect(screen.getAllByText(/Resultado negativo o riesgo/)).toHaveLength(2);
    const filing = screen.getByRole("region", { name: "Radicación" });
    for (const code of Object.keys(statusTones.filing)) {
      expect(within(filing).getByText(code)).toBeInTheDocument();
    }
    expect(screen.getByText("Aprobada").closest("[data-tone]")).toHaveAttribute(
      "data-tone",
      "success",
    );
  });
});

describe("redacción", () => {
  it("los ejemplos usan los formatos de lib/format", () => {
    render(
      <>
        <SentenceCaseExample />
        <LabelExample />
        <LinkExample />
        <DataFormatExample />
        <PrimaryActionExample />
        <DestructiveExample />
      </>,
    );
    expect(screen.getAllByText(/294\.000\.000/).length).toBeGreaterThan(0);
    expect(screen.getByText(/24 ago 2026, 3:45/)).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("button", { name: "Marcar lista para radicar" })
        .some((button) => button.getAttribute("aria-describedby")),
    ).toBe(true);
    expect(screen.getAllByRole("link", { name: "reenviar el enlace de acceso" })).toHaveLength(2);
  });
});
