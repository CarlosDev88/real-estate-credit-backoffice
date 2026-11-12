import { describe, expect, it } from "vitest";

import { loginUrl, readCookie, safeNextPath } from "@/lib/api/session";

describe("safeNextPath", () => {
  it.each([
    ["/solicitudes", "/solicitudes"],
    ["/solicitudes/abc?tab=docs#x", "/solicitudes/abc?tab=docs#x"],
  ])("acepta la ruta interna %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });

  it.each([
    "https://evil.example/x",
    "//evil.example/x",
    "/\\evil.example",
    "javascript:alert(1)",
    "solicitudes",
    "",
    null,
    undefined,
  ])("ignora el next externo o inválido %s", (input) => {
    expect(safeNextPath(input)).toBeNull();
  });
});

describe("loginUrl", () => {
  it("lleva el next interno codificado", () => {
    expect(loginUrl("/solicitudes?page=2")).toBe("/login?next=%2Fsolicitudes%3Fpage%3D2");
  });

  it("ignora un next externo", () => {
    expect(loginUrl("https://evil.example")).toBe("/login");
    expect(loginUrl("//evil.example")).toBe("/login");
  });

  it("no vuelve a mandar al login como next", () => {
    expect(loginUrl("/login?next=%2Fx")).toBe("/login");
  });
});

describe("readCookie", () => {
  it("lee y decodifica la cookie pedida", () => {
    document.cookie = "app_csrf=a%20b; Path=/";
    document.cookie = "otra=1; Path=/";
    expect(readCookie("app_csrf")).toBe("a b");
    expect(readCookie("falta")).toBeNull();
  });
});
