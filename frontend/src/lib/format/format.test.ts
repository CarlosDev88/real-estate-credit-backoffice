import { describe, expect, it } from "vitest";

import {
  formatCOP,
  formatDate,
  formatDateOnly,
  formatDateTime,
  formatInteger,
  formatPercent,
  formatRelative,
  parseInteger,
  TIME_ZONE,
} from "@/lib/format";

const NBSP = String.fromCharCode(0xa0); // espacio de no separación

describe("montos y porcentajes", () => {
  it("formatea COP entero con separador de miles", () => {
    expect(formatCOP(294000000)).toMatch(/^\$\s?294\.000\.000$/);
    expect(formatCOP(0)).toMatch(/^\$\s?0$/);
    expect(formatCOP(null)).toBeNull();
    expect(formatCOP(Number.NaN)).toBeNull();
  });

  it("nunca muestra decimales", () => {
    expect(formatCOP(1500.9)).toMatch(/1\.500$/);
    expect(formatInteger(180500000)).toBe("180.500.000");
    expect(formatInteger(null)).toBe("");
  });

  it("lee solo los dígitos", () => {
    expect(parseInteger("$ 294.000.000")).toBe(294000000);
    expect(parseInteger("")).toBeNull();
    expect(parseInteger("abc")).toBeNull();
  });

  it('porcentaje entero "62 %"', () => {
    expect(formatPercent(62)).toBe(`62${NBSP}%`);
    expect(formatPercent(61.6)).toBe(`62${NBSP}%`);
    expect(formatPercent(null)).toBeNull();
  });
});

describe("fechas en la zona horaria de la app", () => {
  it("usa America/Bogota", () => {
    expect(TIME_ZONE).toBe("America/Bogota");
  });

  it("convierte desde UTC", () => {
    // 03:30 UTC del 25 es todavía el 24 en Bogotá (UTC−5).
    expect(formatDate("2026-08-25T03:30:00Z")).toBe("24 ago 2026");
    expect(formatDateTime("2026-08-24T15:30:00Z")).toBe(`24 ago 2026, 10:30${NBSP}a.${NBSP}m.`);
  });

  it("la hora va en 12 h como es-CO", () => {
    // 20:45 UTC = 3:45 p. m. en Bogotá; mediodía y medianoche son las 12.
    expect(formatDateTime("2026-08-24T20:45:00Z")).toBe(`24 ago 2026, 3:45${NBSP}p.${NBSP}m.`);
    expect(formatDateTime("2026-08-24T17:00:00Z")).toBe(`24 ago 2026, 12:00${NBSP}p.${NBSP}m.`);
    expect(formatDateTime("2026-08-24T05:05:00Z")).toBe(`24 ago 2026, 12:05${NBSP}a.${NBSP}m.`);
    expect(formatDate("no-es-fecha")).toBeNull();
  });

  it("muestra las fechas sin hora tal cual", () => {
    expect(formatDateOnly("2026-08-01")).toBe("1 ago 2026");
    expect(formatDateOnly("2026-08-01T00:00:00Z")).toBeNull();
  });
});

describe("formatRelative", () => {
  // 11 nov 2026, 10:00 en Bogotá.
  const now = new Date("2026-11-11T15:00:00Z");
  const ago = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();

  it.each([
    [0, "Hace un momento"],
    [12, "Hace 12 min"],
    [65, "Hace 1 h"],
    [9 * 60, "Hace 9 h"],
  ])("hace %i min → %s", (minutes, text) => {
    expect(formatRelative(ago(minutes), now)).toBe(text);
  });

  it("Ayer según el calendario de Bogotá, aunque hayan pasado menos de 24 h", () => {
    // 10 nov, 23:00 en Bogotá: 11 h antes, pero ya es otro día.
    expect(formatRelative("2026-11-11T04:00:00Z", now)).toBe("Ayer");
  });

  it("hasta 3 días y después la fecha", () => {
    expect(formatRelative("2026-11-09T15:00:00Z", now)).toBe("Hace 2 días");
    expect(formatRelative("2026-11-08T15:00:00Z", now)).toBe("Hace 3 días");
    expect(formatRelative("2026-11-07T15:00:00Z", now)).toBe("7 nov");
    expect(formatRelative("2025-11-07T15:00:00Z", now)).toBe("7 nov 2025");
  });
});
