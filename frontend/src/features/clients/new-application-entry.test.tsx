import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import {
  ApplicationsListScreen,
  NEW_APPLICATION_HREF,
} from "@/features/applications/applications-list-screen";
import { CLIENTS_BOOTSTRAP, CLIENTS_ME, page } from "@/features/clients/clients.fixtures";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

// "Nueva solicitud" en `/solicitudes` (F4): lleva a elegir el cliente y su oportunidad.

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/solicitudes",
  useSearchParams: () => new URLSearchParams(),
}));

function useApi(permissions: string[]) {
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json({ ...CLIENTS_ME, permissions })),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(CLIENTS_BOOTSTRAP)),
    http.get(apiUrl("/applications/quick-filters"), () =>
      HttpResponse.json([{ code: "all", label: "Todas", statuses: [], count: 0 }]),
    ),
    http.get(apiUrl("/applications"), () => HttpResponse.json(page([]))),
  );
}

describe("'Nueva solicitud' en el listado de solicitudes", { timeout: 20_000 }, () => {
  it("con permiso de crear solicitudes y ver clientes, lleva a /clientes con la ayuda", async () => {
    useApi(["applications.read", "applications.create", "clients.read"]);
    const user = userEvent.setup();
    renderWithProviders(<ApplicationsListScreen />);
    await user.click(await screen.findByRole("button", { name: "Nueva solicitud" }));
    expect(nav.push).toHaveBeenCalledWith(NEW_APPLICATION_HREF);
    expect(NEW_APPLICATION_HREF).toBe("/clientes?nueva_solicitud=1");
  });

  it("sin ver clientes no aparece", async () => {
    useApi(["applications.read", "applications.create"]);
    renderWithProviders(<ApplicationsListScreen />);
    await screen.findByText("No hay solicitudes con estos filtros");
    expect(screen.queryByRole("button", { name: "Nueva solicitud" })).not.toBeInTheDocument();
  });
});
