// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, proxy } from "@/proxy";

const request = (path: string, cookie?: string) =>
  new NextRequest(new URL(path, "http://localhost:3000"), {
    headers: cookie ? { cookie } : undefined,
  });

describe("proxy", () => {
  it("sin cookies de sesión redirige al login con next", () => {
    const response = proxy(request("/solicitudes?page=2"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?next=%2Fsolicitudes%3Fpage%3D2",
    );
  });

  it.each(["app_access=x", "app_refresh=x", "__Host-app_access=x", "__Host-app_refresh=x"])(
    "con %s deja pasar (no valida la cookie)",
    (cookie) => {
      const response = proxy(request("/solicitudes", cookie));
      expect(response.headers.get("location")).toBeNull();
    },
  );

  it("la raíz no redirige: la decide su página", () => {
    expect(proxy(request("/")).headers.get("location")).toBeNull();
  });

  it("el matcher deja fuera lo público", () => {
    const matcher = new RegExp(`^${config.matcher[0]}$`);
    for (const path of [
      "/login",
      "/acceso",
      "/portal/documentos",
      "/dev/ui",
      "/api/v1/auth/me",
      "/_next/static/x.js",
      "/favicon.ico",
    ]) {
      expect(matcher.test(path), path).toBe(false);
    }
    for (const path of ["/solicitudes", "/solicitudes/abc", "/sin-modulos"]) {
      expect(matcher.test(path), path).toBe(true);
    }
  });
});
