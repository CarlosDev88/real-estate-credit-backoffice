import { describe, expect, it } from "vitest";

import {
  defaultDestination,
  isForbiddenPath,
  NO_MODULES_PATH,
  resolveDestination,
  visibleNav,
} from "@/lib/navigation/access";
import { NAV_ITEMS, type NavItem } from "@/lib/navigation/nav-config";

const ITEMS: NavItem[] = [
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: null,
    group: "Comercial",
    permission: "applications.read",
  },
  {
    href: "/clientes",
    label: "Clientes",
    icon: null,
    group: "Comercial",
    permission: "clients.read",
  },
];

describe("visibleNav y defaultDestination", () => {
  it("muestra solo las entradas con permiso, nunca por rol", () => {
    expect(visibleNav(["clients.read"], ITEMS).map((i) => i.href)).toEqual(["/clientes"]);
    expect(defaultDestination(["clients.read", "applications.read"], ITEMS)).toBe("/solicitudes");
  });

  it("el dashboard es el inicio para quien tiene dashboard.read (menú real)", () => {
    expect(defaultDestination(["applications.read", "dashboard.read"])).toBe("/dashboard");
    expect(defaultDestination(["applications.read"])).toBe("/solicitudes");
    expect(NAV_ITEMS[0]).toMatchObject({ href: "/dashboard", group: "Operación" });
  });

  it("sin entradas visibles el destino es la pantalla de sin módulos", () => {
    expect(defaultDestination(["projects.read"], ITEMS)).toBe(NO_MODULES_PATH);
  });
});

describe("resolveDestination", () => {
  const perms = ["applications.read"];

  it("usa next si es interno y el usuario puede verlo", () => {
    expect(resolveDestination("/solicitudes/abc?tab=docs", perms, ITEMS)).toBe(
      "/solicitudes/abc?tab=docs",
    );
  });

  it("ignora un next que el usuario no puede ver", () => {
    expect(resolveDestination("/clientes", perms, ITEMS)).toBe("/solicitudes");
  });

  it("ignora un next externo", () => {
    expect(resolveDestination("https://evil.example/solicitudes", perms, ITEMS)).toBe(
      "/solicitudes",
    );
    expect(resolveDestination("//evil.example/solicitudes", perms, ITEMS)).toBe("/solicitudes");
  });

  it("no confunde un prefijo parecido con la entrada", () => {
    expect(resolveDestination("/solicitudes-falsas", perms, ITEMS)).toBe("/solicitudes");
  });
});

describe("isForbiddenPath", () => {
  it("marca las rutas de entradas sin permiso", () => {
    expect(isForbiddenPath("/clientes/1", ["applications.read"], ITEMS)).toBe(true);
    expect(isForbiddenPath("/solicitudes", ["applications.read"], ITEMS)).toBe(false);
  });

  it("no marca rutas que no son del menú", () => {
    expect(isForbiddenPath("/sin-modulos", [], ITEMS)).toBe(false);
  });
});
