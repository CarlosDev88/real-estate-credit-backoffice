import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { workspaceKeys } from "@/features/applications/workspace-queries";
import { prefetchRoute } from "@/features/auth/route-prefetch";

function spyClient() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, "prefetchQuery").mockResolvedValue();
  return { client, keys: () => spy.mock.calls.map(([options]) => options.queryKey) };
}

describe("prefetchRoute (PERF-01)", () => {
  it("el expediente pide detalle, participantes e inmueble con las claves de la página", () => {
    const { client, keys } = spyClient();
    prefetchRoute(client, "/solicitudes/app-1");
    expect(keys()).toEqual([
      workspaceKeys.detail("app-1"),
      workspaceKeys.participants("app-1"),
      workspaceKeys.property("app-1"),
    ]);
  });

  it.each(["/solicitudes", "/solicitudes/app-1/otra", "/dashboard"])(
    "otras rutas no piden nada (%s)",
    (path) => {
      const { client, keys } = spyClient();
      prefetchRoute(client, path);
      expect(keys()).toEqual([]);
    },
  );
});
