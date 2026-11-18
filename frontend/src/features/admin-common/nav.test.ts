import { describe, expect, it } from "vitest";

import { isForbiddenPath, visibleNav } from "@/lib/navigation/access";
import { NAV_ITEMS } from "@/lib/navigation/nav-config";

describe("grupo 'Administración' del menú (F6)", () => {
  it("cada entrada pide su permiso", () => {
    const admin = NAV_ITEMS.filter((item) => item.group === "Administración").map((item) => [
      item.href,
      item.permission,
    ]);
    expect(admin).toEqual([
      ["/admin/usuarios", "users.read"],
      ["/admin/constructoras", "partners.create"],
      ["/proyectos", "projects.read"],
    ]);
  });

  it("el asesor y la constructora ven Proyectos, no Usuarios ni Constructoras", () => {
    const advisor = ["applications.read", "clients.read", "partners.read", "projects.read"];
    expect(visibleNav(advisor).map((item) => item.href)).toEqual([
      "/solicitudes",
      "/clientes",
      "/proyectos",
    ]);
    expect(isForbiddenPath("/admin/constructoras", advisor)).toBe(true);
    expect(isForbiddenPath("/admin/usuarios", advisor)).toBe(true);
    expect(isForbiddenPath("/proyectos", advisor)).toBe(false);
  });
});
