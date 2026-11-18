import { describe, expect, it } from "vitest";

import { isForbiddenPath, visibleNav } from "@/lib/navigation/access";
import { NAV_ITEMS } from "@/lib/navigation/nav-config";

describe("entrada 'Clientes' del menú", () => {
  it("va en 'Comercial' con el permiso de lectura de clientes", () => {
    const clients = NAV_ITEMS.find((item) => item.href === "/clientes");
    expect(clients).toMatchObject({
      label: "Clientes",
      group: "Comercial",
      permission: "clients.read",
    });
  });

  it("solo se ve con `clients.read`, y protege las rutas de clientes", () => {
    expect(visibleNav(["applications.read"]).map((i) => i.href)).toEqual(["/solicitudes"]);
    expect(visibleNav(["applications.read", "clients.read"]).map((i) => i.href)).toEqual([
      "/solicitudes",
      "/clientes",
    ]);
    expect(isForbiddenPath("/clientes/nuevo", ["applications.read"])).toBe(true);
    expect(isForbiddenPath("/clientes/abc/editar", ["clients.read"])).toBe(false);
  });
});
