import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CatalogScreen } from "@/features/admin-catalogs/catalog-screen";
import { CatalogsScreen, parseCatalogsParams } from "@/features/admin-catalogs/catalogs-screen";
import { move, orderChanged, positionText } from "@/features/admin-catalogs/order";
import type { Catalog, CatalogItem } from "@/features/admin-catalogs/queries";
import {
  dialog,
  meWith,
  page,
  recordWrite,
  setMobile,
  type WriteCall,
} from "@/features/admin-common/test-kit";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
    push: vi.fn(),
    replace: vi.fn((href: string) => {
      window.history.replaceState(null, "", href);
      notify();
    }),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useRouter: () => nav,
    usePathname: () => "/admin/catalogos",
    useSearchParams: () => {
      const search = useSyncExternalStore(
        (cb) => {
          nav.listeners.add(cb);
          return () => nav.listeners.delete(cb);
        },
        () => window.location.search,
      );
      return new URLSearchParams(search);
    },
  };
});

const PERMISSIONS = ["catalogs.read", "catalogs.create", "catalogs.update"];

function makeCatalog(n: number, overrides: Partial<Catalog> = {}): Catalog {
  return {
    id: `a0000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    code: n === 1 ? "lead_origin" : "application_status",
    name: n === 1 ? "Origen del cliente" : "Estado de solicitud",
    description: "",
    is_manageable: n === 1,
    is_public: false,
    version: 3,
    items_count: 3,
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
    ...overrides,
  };
}
const CATALOGS = [makeCatalog(1), makeCatalog(2)];

const item = (n: number, code: string, label: string, active = true): CatalogItem => ({
  id: `b0000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  catalog_id: CATALOGS[0]!.id,
  catalog_code: "lead_origin",
  code,
  label,
  description: "",
  parent_id: null,
  sort_order: n * 10,
  is_active: active,
  valid_from: null,
  valid_to: null,
  metadata: {},
  created_at: "2026-11-01T15:00:00Z",
  updated_at: "2026-11-01T15:00:00Z",
});
const ITEMS = [
  item(1, "DIRECT", "Directo"),
  item(2, "BROKER", "Broker"),
  item(3, "WEB", "Web", false),
];

function useApi({ permissions = PERMISSIONS } = {}) {
  const calls = { writes: [] as WriteCall[] };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions))),
    http.get(apiUrl("/catalogs"), ({ request }) =>
      HttpResponse.json(page(CATALOGS, new URL(request.url).searchParams)),
    ),
    http.get(apiUrl("/catalogs/:id"), ({ params }) =>
      HttpResponse.json(CATALOGS.find((c) => c.id === params.id)),
    ),
    http.get(apiUrl("/catalogs/:id/items"), () =>
      HttpResponse.json(page(ITEMS, new URLSearchParams("page_size=100"))),
    ),
    http.put(apiUrl("/catalogs/:id/items/order"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(page(ITEMS, new URLSearchParams("page_size=100")));
    }),
    http.post(apiUrl("/catalogs/:id/items"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(item(4, "EVENT", "Evento"), { status: 201 });
    }),
    http.patch(apiUrl("/catalog-items/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(ITEMS.find((i) => i.id === params.id));
    }),
    http.post(apiUrl("/catalog-items/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(ITEMS.find((i) => i.id === params.id));
    }),
  );
  return calls;
}

beforeEach(() => setMobile(false));

describe("orden de valores", () => {
  it("mueve de a un puesto y no sale del rango", () => {
    expect(move(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    expect(move(["a", "b"], 0, -1)).toEqual(["a", "b"]);
    expect(orderChanged([{ id: "1" }, { id: "2" }], [{ id: "2" }, { id: "1" }])).toBe(true);
    expect(orderChanged([{ id: "1" }], [{ id: "1" }])).toBe(false);
    expect(positionText("Web", 0, 3)).toBe("Web: puesto 1 de 3.");
    expect(parseCatalogsParams(new URLSearchParams("public=x&ordering=-name"))).toMatchObject({
      public: "",
      ordering: "-name",
    });
  });
});

describe("catálogos", { timeout: 20_000 }, () => {
  it("listado: valores, visibilidad y los del sistema", async () => {
    useApi();
    renderWithProviders(<CatalogsScreen />);
    const row = (await screen.findByRole("link", { name: "Estado de solicitud" })).closest("tr")!;
    expect(within(row).getByText("Del sistema")).toBeInTheDocument();
    expect(within(row).getByText("application_status")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Origen del cliente" })).toHaveAttribute(
      "href",
      `/admin/catalogos/${CATALOGS[0]!.id}`,
    );
  });

  it("reordenar con subir y bajar, anunciarlo y guardar todo junto", async () => {
    const calls = useApi();
    const user = userEvent.setup();
    renderWithProviders(<CatalogScreen catalogId={CATALOGS[0]!.id} />);
    const list = await screen.findByRole("list", { name: "Valores del catálogo" });
    expect(within(list).getByRole("button", { name: "Subir Directo" })).toBeDisabled();
    expect(within(list).getByRole("button", { name: "Bajar Web" })).toBeDisabled();

    await user.click(within(list).getByRole("button", { name: "Subir Web" }));
    expect(screen.getByText("Web: puesto 2 de 3.")).toBeInTheDocument();
    const labels = within(list)
      .getAllByRole("listitem")
      .map((li) => li.querySelector(".font-medium")?.textContent);
    expect(labels).toEqual(["Directo", "Web", "Broker"]);

    const pending = screen.getByRole("region", { name: "Orden sin guardar" });
    await user.click(within(pending).getByRole("button", { name: "Guardar orden" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PUT",
        path: `/api/v1/catalogs/${CATALOGS[0]!.id}/items/order`,
        body: { item_ids: [ITEMS[0]!.id, ITEMS[2]!.id, ITEMS[1]!.id] },
      }),
    );
    expect(await screen.findByText("Orden guardado")).toBeInTheDocument();
  });

  it("descartar el orden vuelve al original", async () => {
    useApi();
    const user = userEvent.setup();
    renderWithProviders(<CatalogScreen catalogId={CATALOGS[0]!.id} />);
    const list = await screen.findByRole("list", { name: "Valores del catálogo" });
    await user.click(within(list).getByRole("button", { name: "Bajar Directo" }));
    await user.click(screen.getByRole("button", { name: "Descartar" }));
    expect(screen.queryByRole("region", { name: "Orden sin guardar" })).not.toBeInTheDocument();
  });

  it("nuevo valor y desactivar con confirmación", async () => {
    const calls = useApi();
    const user = userEvent.setup();
    renderWithProviders(<CatalogScreen catalogId={CATALOGS[0]!.id} />);
    await screen.findByRole("list", { name: "Valores del catálogo" });
    await user.click(screen.getByRole("button", { name: "Nuevo valor" }));
    const modal = await dialog("Nuevo valor");
    await user.type(within(modal).getByLabelText("Código"), "evento");
    await user.click(within(modal).getByRole("button", { name: "Crear valor" }));
    expect(await within(modal).findByText("Usa mayúsculas, números y _.")).toBeInTheDocument();
    await user.clear(within(modal).getByLabelText("Código"));
    await user.type(within(modal).getByLabelText("Código"), "EVENTO");
    await user.type(within(modal).getByLabelText("Etiqueta"), "Evento");
    await user.click(within(modal).getByRole("button", { name: "Crear valor" }));
    await waitFor(() =>
      expect(calls.writes.at(-1)).toEqual({
        method: "POST",
        path: `/api/v1/catalogs/${CATALOGS[0]!.id}/items`,
        body: {
          code: "EVENTO",
          label: "Evento",
          description: "",
          valid_from: null,
          valid_to: null,
        },
      }),
    );

    await user.click(screen.getByRole("button", { name: "Desactivar Broker" }));
    const confirm = await dialog("Desactivar Broker");
    await user.click(within(confirm).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/catalog-items/${ITEMS[1]!.id}/deactivate`,
        body: null,
      }),
    );
  });

  it("catálogo del sistema: solo lectura", async () => {
    useApi();
    renderWithProviders(<CatalogScreen catalogId={CATALOGS[1]!.id} />);
    expect(await screen.findByText("Catálogo del sistema: solo lectura")).toBeInTheDocument();
    await screen.findByRole("list", { name: "Valores del catálogo" });
    expect(screen.queryByRole("button", { name: /Subir/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuevo valor" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar catálogo" })).not.toBeInTheDocument();
  });

  it("nuevo catálogo (código en minúsculas) y editar un valor sin cambiar su código", async () => {
    const calls = useApi();
    server.use(
      http.post(apiUrl("/catalogs"), async ({ request }) => {
        await recordWrite(calls.writes, request);
        return HttpResponse.json(makeCatalog(3, { code: "event_type" }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<CatalogsScreen />);
    await user.click(await screen.findByRole("button", { name: "Nuevo catálogo" }));
    const modal = await dialog("Nuevo catálogo");
    await user.type(within(modal).getByLabelText("Código"), "Tipo Evento");
    await user.click(within(modal).getByRole("button", { name: "Crear catálogo" }));
    expect(await within(modal).findByText(/Usa minúsculas/)).toBeInTheDocument();
    expect(within(modal).getByText("Escribe el nombre.")).toBeInTheDocument();
    await user.clear(within(modal).getByLabelText("Código"));
    await user.type(within(modal).getByLabelText("Código"), "event_type");
    await user.type(within(modal).getByLabelText("Nombre"), "Tipo de evento");
    await user.click(within(modal).getByRole("checkbox", { name: /Público/ }));
    await user.click(within(modal).getByRole("button", { name: "Crear catálogo" }));
    await waitFor(() =>
      expect(calls.writes.at(-1)).toEqual({
        method: "POST",
        path: "/api/v1/catalogs",
        body: { code: "event_type", name: "Tipo de evento", description: "", is_public: true },
      }),
    );
    await waitFor(() =>
      expect(nav.push).toHaveBeenCalledWith(`/admin/catalogos/${makeCatalog(3).id}`),
    );
    unmount();

    renderWithProviders(<CatalogScreen catalogId={CATALOGS[0]!.id} />);
    await user.click(await screen.findByRole("button", { name: "Editar Broker" }));
    const edit = await dialog("Editar Broker");
    expect(within(edit).getByLabelText("Código")).toBeDisabled();
    await user.type(within(edit).getByLabelText(/Vigente hasta/), "2027-12-31");
    await user.click(within(edit).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/catalog-items/${ITEMS[1]!.id}`,
        body: { valid_to: "2027-12-31" },
      }),
    );
  });

  it("en móvil, tarjetas", async () => {
    setMobile(true);
    useApi();
    renderWithProviders(<CatalogsScreen />);
    const list = await screen.findByRole("list", { name: "Catálogos" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});
