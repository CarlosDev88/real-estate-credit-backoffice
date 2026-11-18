import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClientsListScreen } from "@/features/clients/clients-list-screen";
import {
  apiError,
  CLIENTS_BOOTSTRAP,
  CLIENTS_ME,
  makeClient,
} from "@/features/clients/clients.fixtures";
import {
  parseClientListParams,
  parseClientOrdering,
  serializeClientListParams,
} from "@/features/clients/list-params";
import type { Client } from "@/features/clients/queries";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

// Router de prueba: `replace` escribe en la URL de jsdom y avisa a `useSearchParams`.
const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
    notify,
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
    usePathname: () => "/clientes",
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

const ALL = Array.from({ length: 45 }, (_, i) => makeClient(i + 1));

function useApi(rows: Client[] = ALL, me: typeof CLIENTS_ME = CLIENTS_ME): URLSearchParams[] {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(me)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(CLIENTS_BOOTSTRAP)),
    http.get(apiUrl("/clients"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      requests.push(query);
      const page = Number(query.get("page") ?? 1);
      const size = Number(query.get("page_size") ?? 25);
      const items = rows.slice((page - 1) * size, page * size);
      if (page > 1 && items.length === 0) {
        return HttpResponse.json(apiError("NOT_FOUND", "Página inválida."), { status: 404 });
      }
      return HttpResponse.json({
        items,
        page,
        page_size: size,
        total: rows.length,
        next: null,
        previous: null,
      });
    }),
  );
  return requests;
}

const last = (list: URLSearchParams[]) => list[list.length - 1];

/** Fila de la tabla a partir del enlace con el nombre del cliente. */
const rowOf = (name: string) => screen.getByRole("link", { name }).closest("tr")!;

function setMobile(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matches && query.includes("max-width: 860px"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

function go(search: string) {
  window.history.replaceState(null, "", `/clientes${search}`);
}

async function renderList() {
  const user = userEvent.setup();
  renderWithProviders(<ClientsListScreen />);
  await screen.findByText("Persona Número 1");
  return user;
}

beforeEach(() => {
  setMobile(false);
  nav.push.mockClear();
  nav.replace.mockClear();
});

describe("parámetros del listado de clientes", () => {
  it("lee la URL con valores por defecto y descarta los inválidos", () => {
    expect(parseClientListParams(new URLSearchParams(""))).toEqual({
      search: "",
      origin: "",
      nueva_solicitud: "",
      ordering: "-created_at",
      page: 1,
      page_size: 20,
    });
    expect(
      parseClientListParams(
        new URLSearchParams(
          "search=%20ana%20&origin=BROKER&ordering=last_names&page=3&page_size=50",
        ),
      ),
    ).toEqual({
      search: "ana",
      origin: "BROKER",
      nueva_solicitud: "",
      ordering: "last_names",
      page: 3,
      page_size: 50,
    });
    expect(
      parseClientListParams(new URLSearchParams("ordering=-phone&page=0&page_size=7")),
    ).toMatchObject({ ordering: "-created_at", page: 1, page_size: 20 });
  });

  it("no escribe en la URL los valores por defecto", () => {
    const params = parseClientListParams(new URLSearchParams(""));
    expect(serializeClientListParams(params)).toBe("");
    expect(serializeClientListParams({ ...params, origin: "BROKER", page: 2 })).toBe(
      "origin=BROKER&page=2",
    );
  });

  it("un orden desconocido vuelve al por defecto", () => {
    expect(parseClientOrdering("-last_names")).toEqual({ field: "last_names", desc: true });
    expect(parseClientOrdering("email")).toEqual({ field: "created_at", desc: true });
  });
});

describe("listado de clientes", { timeout: 20_000 }, () => {
  it("muestra las columnas con su formato y pide el orden por defecto", async () => {
    const requests = useApi([makeClient(1), makeClient(2, { email: "", phone: "", origin: null })]);
    await renderList();

    expect(screen.getByRole("heading", { name: "Clientes" })).toBeInTheDocument();
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    // La flecha de "Nombre" está oculta (solo al pasar el mouse); "Creado" es el orden activo.
    expect(headers).toEqual(["Nombre↕", "Documento", "Correo", "Teléfono", "Origen", "Creado↓"]);

    const first = rowOf("Persona Número 1");
    expect(within(first).getByText("CC")).toHaveAttribute("title", "Cédula de ciudadanía");
    expect(within(first).getByText("1000001")).toBeInTheDocument();
    expect(within(first).getByText("persona1@example.com")).toBeInTheDocument();
    expect(within(first).getByText("+573001234567")).toBeInTheDocument();
    expect(within(first).getByText("Directo")).toBeInTheDocument();
    expect(within(first).getByText("10 nov 2026")).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Persona Número 1" })).toHaveAttribute(
      "href",
      "/clientes/cl-1",
    );

    const second = rowOf("Persona Número 2");
    expect(within(second).getAllByText("—")).toHaveLength(3);

    expect(last(requests)?.get("ordering")).toBe("-created_at");
    expect(last(requests)?.get("page_size")).toBe("20");
  });

  it("la búsqueda espera y va a `search`, en la URL", async () => {
    const requests = useApi();
    const user = await renderList();

    await user.type(screen.getByRole("searchbox", { name: /Buscar clientes/ }), " laura ");
    expect(window.location.search).toBe("");
    await waitFor(() => expect(window.location.search).toBe("?search=laura"));
    await waitFor(() => expect(last(requests)?.get("search")).toBe("laura"));
    expect(requests.filter((q) => q.has("search"))).toHaveLength(1);
  });

  it("filtra por origen con los valores activos del catálogo y limpia", async () => {
    const requests = useApi();
    const user = await renderList();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por origen" }));
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["todos", "Directo", "Broker"]);
    await user.click(screen.getAllByTitle("Broker").at(-1)!);
    await waitFor(() => expect(window.location.search).toBe("?origin=BROKER"));
    await waitFor(() => expect(last(requests)?.get("origin")).toBe("BROKER"));

    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("ordena por nombre y por fecha desde el encabezado", async () => {
    const requests = useApi();
    const user = await renderList();

    const name = screen.getByRole("columnheader", { name: /Nombre/ });
    expect(name).toHaveAttribute("aria-sort", "none");
    expect(screen.getByRole("columnheader", { name: /Creado/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: "Documento" })).not.toHaveAttribute(
      "aria-sort",
    );

    await user.click(within(name).getByRole("button"));
    await waitFor(() => expect(window.location.search).toBe("?ordering=-last_names"));
    await waitFor(() => expect(last(requests)?.get("ordering")).toBe("-last_names"));
    await user.click(
      within(screen.getByRole("columnheader", { name: /Nombre/ })).getByRole("button"),
    );
    await waitFor(() => expect(window.location.search).toBe("?ordering=last_names"));
  });

  it("pagina con el rango y una página que ya no existe vuelve a la primera", async () => {
    go("?page=9");
    const requests = useApi();
    renderWithProviders(<ClientsListScreen />);
    await waitFor(() => expect(window.location.search).toBe(""));
    await screen.findByText("Persona Número 1");
    expect(screen.getByText("Mostrando 1–20 de 45")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Clientes por página" })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Page 2" }));
    await waitFor(() => expect(window.location.search).toBe("?page=2"));
    await waitFor(() => expect(last(requests)?.get("page")).toBe("2"));
    expect(await screen.findByText("Mostrando 21–40 de 45")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Clientes por página" }));
    await user.click((await screen.findAllByTitle("50")).at(-1)!);
    await waitFor(() => expect(window.location.search).toBe("?page_size=50"));
    expect(await screen.findByText("Mostrando 1–45 de 45")).toBeInTheDocument();
  });

  it("un clic o Enter en la fila abre el detalle", async () => {
    useApi();
    const user = await renderList();
    await user.click(within(rowOf("Persona Número 2")).getByText("persona2@example.com"));
    expect(nav.push).toHaveBeenCalledWith("/clientes/cl-2");

    rowOf("Persona Número 3").focus();
    await user.keyboard("{Enter}");
    expect(nav.push).toHaveBeenCalledWith("/clientes/cl-3");
  });

  it("'Nuevo cliente' solo con permiso de crear", async () => {
    useApi();
    const user = await renderList();
    await user.click(await screen.findByRole("button", { name: "Nuevo cliente" }));
    expect(nav.push).toHaveBeenCalledWith("/clientes/nuevo");
  });

  it("sin permiso de crear no muestra 'Nuevo cliente'", async () => {
    useApi(ALL, { ...CLIENTS_ME, permissions: ["clients.read"] });
    await renderList();
    expect(screen.queryByRole("button", { name: "Nuevo cliente" })).not.toBeInTheDocument();
  });

  it("vacío sin filtros invita a registrar; con filtros, a limpiarlos", async () => {
    useApi([]);
    renderWithProviders(<ClientsListScreen />);
    expect(await screen.findByText("Todavía no hay clientes")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Registrar un cliente" })).toHaveAttribute(
      "href",
      "/clientes/nuevo",
    );
  });

  it("desde 'Nueva solicitud' ayuda a elegir y abre el cliente en Oportunidades", async () => {
    go("?nueva_solicitud=1");
    const requests = useApi();
    const user = await renderList();

    expect(screen.getByText("Elige el cliente y su oportunidad")).toBeInTheDocument();
    expect(rowOf("Persona Número 1").querySelector("a")).toHaveAttribute(
      "href",
      "/clientes/cl-1?tab=oportunidades",
    );
    // No va a la API.
    expect(last(requests)?.has("nueva_solicitud")).toBe(false);

    // Se conserva al filtrar y se quita al cerrar la ayuda.
    await user.type(screen.getByRole("searchbox", { name: /Buscar clientes/ }), "ana");
    await waitFor(() => expect(window.location.search).toBe("?nueva_solicitud=1&search=ana"));
    await user.click(screen.getByRole("button", { name: "Cerrar ayuda" }));
    await waitFor(() => expect(window.location.search).toBe("?search=ana"));
  });

  it("vacío con filtros ofrece 'Limpiar filtros'", async () => {
    go("?origin=BROKER");
    useApi([]);
    const user = userEvent.setup();
    renderWithProviders(<ClientsListScreen />);
    expect(await screen.findByText("No hay clientes con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("muestra el esqueleto mientras carga y el error con 'Reintentar'", async () => {
    let fail = true;
    server.use(
      http.get(apiUrl("/auth/me"), () => HttpResponse.json(CLIENTS_ME)),
      http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(CLIENTS_BOOTSTRAP)),
      http.get(apiUrl("/clients"), () =>
        fail
          ? HttpResponse.json(apiError("PERMISSION_DENIED", "No tienes permiso."), { status: 403 })
          : HttpResponse.json({
              items: [makeClient(1)],
              page: 1,
              page_size: 20,
              total: 1,
              next: null,
              previous: null,
            }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<ClientsListScreen />);
    expect(screen.getByRole("status", { name: "Cargando clientes" })).toBeInTheDocument();
    expect(await screen.findByText("No pudimos cargar los clientes")).toBeInTheDocument();
    expect(screen.getByText("No tienes permiso.")).toBeInTheDocument();

    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Persona Número 1")).toBeInTheDocument();
  });

  it("en móvil muestra tarjetas, el botón de filtros y el chip del origen", async () => {
    setMobile(true);
    go("?origin=DIRECT");
    useApi([makeClient(1), makeClient(2, { email: "", phone: "" })]);
    const user = userEvent.setup();
    renderWithProviders(<ClientsListScreen />);

    const cards = await screen.findByRole("list", { name: "Clientes" });
    expect(within(cards).getByText("Persona Número 1")).toBeInTheDocument();
    expect(within(cards).getByText("persona1@example.com · +573001234567")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    expect(await screen.findByText("Directo", { selector: "b" })).toBeInTheDocument();
    await user.click(within(cards).getAllByText("Directo")[0]!);
    expect(nav.push).toHaveBeenCalledWith("/clientes/cl-1");

    await user.click(screen.getByRole("button", { name: "Filtros (1)" }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("combobox", { name: "Filtrar por origen" })).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Ver resultados" }));

    await user.click(screen.getByRole("button", { name: "Quitar filtro Origen: Directo" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });
});
