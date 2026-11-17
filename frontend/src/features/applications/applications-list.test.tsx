import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationsListScreen } from "@/features/applications/applications-list-screen";
import type { Application } from "@/features/applications/queries";
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
    usePathname: () => "/solicitudes",
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

const ME = {
  id: "u-1",
  name: "Asesora",
  email: "asesor@example.com",
  role: "ADVISOR",
  roles: ["ADVISOR"],
  permissions: ["applications.read", "banks.read"],
  scope: { assigned_applications_only: true, partner_id: null },
};

const FNA = { id: "b-fna", code: "FNA", name: "Fondo Nacional del Ahorro", short_name: "FNA" };
const BOGOTA = { id: "b-bog", code: "BOG", name: "Banco de Bogotá", short_name: "" };

const item = (code: string, label: string, order: number) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active: true,
  parent_id: null,
  parent_code: null,
  metadata: {},
});

const BOOTSTRAP = {
  metadata_version: 1,
  actor: "INTERNAL",
  permissions: [],
  on_demand_catalogs: [],
  features: {},
  catalogs: {
    bank_product_type: [
      item("LEASING", "Leasing habitacional", 2),
      item("MORTGAGE", "Crédito hipotecario", 1),
      { ...item("OLD", "Tipo retirado", 3), active: false },
    ],
    loan_purpose: [item("NEW", "Vivienda nueva", 1), item("USED", "Vivienda usada", 2)],
  },
};

const TABS = [
  { code: "all", label: "Todas", statuses: [], count: 48 },
  { code: "waiting", label: "Esperando al comprador", statuses: ["WAITING_DOCUMENTS"], count: 14 },
  { code: "review", label: "En revisión", statuses: ["DOCUMENTS_REVIEW"], count: 7 },
];

function makeApp(n: number, overrides: Partial<Application> = {}): Application {
  return {
    id: `app-${n}`,
    code: `SOL-${String(n).padStart(6, "0")}`,
    status: "DOCUMENTS_REVIEW",
    status_label: "Documentos en revisión",
    opportunity_id: `op-${n}`,
    applicant: {
      id: `cl-${n}`,
      full_name: `Persona ${n}`,
      document_type: "CC",
      document_number: String(n),
    },
    participants_summary: { co_applicants: 0, solidary_debtors: 0 },
    purpose: { code: "NEW", label: "Vivienda nueva" },
    bank_product: {
      id: "p-1",
      code: "P1",
      name: "Hipoteca",
      product_type: { code: "MORTGAGE", label: "Crédito hipotecario" },
      bank: FNA,
    },
    requested_amount_cop: 294_000_000,
    completeness_pct: 62,
    ready_to_file_blocked: null,
    last_buyer_activity_at: null,
    buyer_inactive: null,
    assigned_advisor: { id: "u-1", name: "Asesora" },
    origin: { code: "DIRECT", label: "Directo" },
    project: null,
    version: 1,
    current_stage_started_at: "2026-11-01T10:00:00Z",
    ready_to_file_at: null,
    withdrawn_at: null,
    withdrawal_reason: null,
    closed_at: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-10T10:00:00Z",
    ...overrides,
  } as Application;
}

const ALL = Array.from({ length: 48 }, (_, i) => makeApp(i + 1));

interface Requests {
  list: URLSearchParams[];
  tabs: URLSearchParams[];
}

/** Handlers con un backend falso que pagina `rows`; guarda la query de cada petición. */
function useApi(rows: Application[] = ALL, opts: { tabs?: typeof TABS } = {}): Requests {
  const requests: Requests = { list: [], tabs: [] };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/banks"), () =>
      HttpResponse.json({
        items: [BOGOTA, FNA],
        page: 1,
        page_size: 100,
        total: 2,
        next: null,
        previous: null,
      }),
    ),
    http.get(apiUrl("/applications/quick-filters"), ({ request }) => {
      requests.tabs.push(new URL(request.url).searchParams);
      return HttpResponse.json(opts.tabs ?? TABS);
    }),
    http.get(apiUrl("/applications"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      requests.list.push(query);
      const page = Number(query.get("page") ?? 1);
      const size = Number(query.get("page_size") ?? 25);
      const items = rows.slice((page - 1) * size, page * size);
      if (page > 1 && items.length === 0) {
        return HttpResponse.json(
          { code: "NOT_FOUND", message: "Página inválida.", details: [], request_id: "r" },
          { status: 404 },
        );
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
  window.history.replaceState(null, "", `/solicitudes${search}`);
}

async function renderList() {
  const user = userEvent.setup();
  renderWithProviders(<ApplicationsListScreen />);
  await screen.findByText("SOL-000001");
  return user;
}

async function pickOption(user: ReturnType<typeof userEvent.setup>, combo: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: combo }));
  const options = await screen.findAllByTitle(option);
  await user.click(options[options.length - 1]!);
}

beforeEach(() => {
  setMobile(false);
  nav.push.mockClear();
  nav.replace.mockClear();
});

// Pruebas largas (varios selects de Ant Design): bajo carga superan los 5 s por defecto.
describe("listado de solicitudes", { timeout: 20_000 }, () => {
  it("muestra el encabezado y las pestañas de la API con sus conteos, en su orden", async () => {
    const requests = useApi();
    await renderList();

    expect(screen.getByRole("heading", { name: "Solicitudes" })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Todas 48",
      "Esperando al comprador 14",
      "En revisión 7",
    ]);
    expect(screen.getByRole("tab", { name: "Todas 48" })).toHaveAttribute("aria-selected", "true");
    // Las pestañas no reciben `quick_filter`; el listado va con el orden por defecto.
    expect(last(requests.tabs)?.has("quick_filter")).toBe(false);
    expect(last(requests.list)?.get("ordering")).toBe("-updated_at");
    expect(last(requests.list)?.get("page_size")).toBe("20");
  });

  it("al elegir una pestaña va a la URL y al listado, y vuelve a la página 1", async () => {
    go("?page=2");
    const requests = useApi();
    const user = userEvent.setup();
    renderWithProviders(<ApplicationsListScreen />);
    await screen.findByText("SOL-000021");

    await user.click(screen.getByRole("tab", { name: "En revisión 7" }));
    await waitFor(() => expect(window.location.search).toBe("?quick_filter=review"));
    await waitFor(() => expect(last(requests.list)?.get("quick_filter")).toBe("review"));
    expect(last(requests.list)?.get("page")).toBe("1");
    expect(screen.getByRole("tab", { name: "En revisión 7" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("cada filtro sale de la URL y vuelve a la URL", async () => {
    go("?bank_id=b-fna&product_type=MORTGAGE&purpose=NEW");
    const requests = useApi();
    const user = await renderList();

    // Desde la URL: los controles muestran el valor y las peticiones lo llevan.
    expect(await screen.findByText("Banco: FNA")).toBeInTheDocument();
    expect(await screen.findByText("Tipo de crédito: Crédito hipotecario")).toBeInTheDocument();
    expect(screen.getByText("Finalidad: Vivienda nueva")).toBeInTheDocument();
    for (const query of [last(requests.list), last(requests.tabs)]) {
      expect(query?.get("bank_id")).toBe("b-fna");
      expect(query?.get("product_type")).toBe("MORTGAGE");
      expect(query?.get("purpose")).toBe("NEW");
    }

    // Hacia la URL: el banco sin nombre corto se ve con `name`.
    await pickOption(user, "Filtrar por banco", "Banco de Bogotá");
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("bank_id")).toBe("b-bog"),
    );
    await pickOption(user, "Filtrar por tipo de crédito", "Leasing habitacional");
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("product_type")).toBe("LEASING"),
    );
    await pickOption(user, "Filtrar por finalidad", "todas");
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).has("purpose")).toBe(false),
    );
    await waitFor(() => expect(last(requests.list)?.get("bank_id")).toBe("b-bog"));

    // "Limpiar" quita todo.
    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("solo ofrece los valores activos del catálogo, en el orden de la API", async () => {
    useApi();
    const user = await renderList();
    await user.click(screen.getByRole("combobox", { name: "Filtrar por tipo de crédito" }));
    const listbox = await screen.findByRole("listbox");
    expect(listbox).toBeInTheDocument();
    expect(screen.queryByTitle("Tipo retirado")).not.toBeInTheDocument();
    const titles = Array.from(document.querySelectorAll(".ant-select-item-option")).map((el) =>
      el.getAttribute("title"),
    );
    expect(titles).toEqual(["todos", "Crédito hipotecario", "Leasing habitacional"]);
  });

  it("sin permiso de bancos no muestra ese filtro", async () => {
    useApi();
    server.use(
      http.get(apiUrl("/auth/me"), () =>
        HttpResponse.json({ ...ME, permissions: ["applications.read"] }),
      ),
    );
    await renderList();
    await screen.findByRole("combobox", { name: "Filtrar por finalidad" });
    expect(screen.queryByRole("combobox", { name: "Filtrar por banco" })).not.toBeInTheDocument();
  });

  it("la búsqueda espera 300 ms y va a `search`", async () => {
    const requests = useApi();
    const user = await renderList();
    const before = requests.list.length;

    await user.type(screen.getByRole("searchbox", { name: /Buscar en solicitudes/ }), " laura ");
    expect(window.location.search).toBe("");
    await waitFor(() => expect(window.location.search).toBe("?search=laura"));
    await waitFor(() => expect(last(requests.list)?.get("search")).toBe("laura"));
    expect(last(requests.tabs)?.get("search")).toBe("laura");
    // Una sola petición por la búsqueda completa, no una por letra.
    expect(requests.list.filter((q) => q.has("search"))).toHaveLength(1);
    expect(requests.list.length).toBe(before + 1);
  });

  it("ordena desde el encabezado, alternando descendente y ascendente", async () => {
    const requests = useApi();
    const user = await renderList();

    const updated = screen.getByRole("columnheader", { name: /Actualizada/ });
    expect(updated).toHaveAttribute("aria-sort", "descending");
    const amount = screen.getByRole("columnheader", { name: /Monto/ });
    expect(amount).toHaveAttribute("aria-sort", "none");
    expect(screen.getByRole("columnheader", { name: "Estado" })).not.toHaveAttribute("aria-sort");

    await user.click(within(amount).getByRole("button"));
    await waitFor(() => expect(window.location.search).toBe("?ordering=-requested_amount"));
    await waitFor(() => expect(last(requests.list)?.get("ordering")).toBe("-requested_amount"));
    expect(screen.getByRole("columnheader", { name: /Monto/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: /Actualizada/ })).toHaveAttribute(
      "aria-sort",
      "none",
    );

    await user.click(
      within(screen.getByRole("columnheader", { name: /Monto/ })).getByRole("button"),
    );
    await waitFor(() => expect(window.location.search).toBe("?ordering=requested_amount"));
    expect(screen.getByRole("columnheader", { name: /Monto/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );

    await user.click(
      within(screen.getByRole("columnheader", { name: /Monto/ })).getByRole("button"),
    );
    await waitFor(() => expect(window.location.search).toBe("?ordering=-requested_amount"));
  });

  it("pagina con el rango, cambia de página y de tamaño", async () => {
    const requests = useApi();
    const user = await renderList();

    expect(screen.getByText("Mostrando 1–20 de 48")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Page 2" }));
    await waitFor(() => expect(window.location.search).toBe("?page=2"));
    expect(await screen.findByText("Mostrando 21–40 de 48")).toBeInTheDocument();
    expect(await screen.findByText("SOL-000021")).toBeInTheDocument();

    await pickOption(user, "Solicitudes por página", "50");
    await waitFor(() => expect(window.location.search).toBe("?page_size=50"));
    await waitFor(() => expect(last(requests.list)?.get("page_size")).toBe("50"));
    expect(await screen.findByText("Mostrando 1–48 de 48")).toBeInTheDocument();
  });

  it("una página que ya no existe vuelve a la primera", async () => {
    go("?page=9");
    useApi();
    renderWithProviders(<ApplicationsListScreen />);
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(await screen.findByText("SOL-000001")).toBeInTheDocument();
  });

  it("sin resultados muestra el estado vacío, con 'Limpiar filtros' si hay filtros", async () => {
    go("?search=nadie");
    useApi([]);
    renderWithProviders(<ApplicationsListScreen />);
    expect(await screen.findByText("No hay solicitudes con estos filtros")).toBeInTheDocument();
    expect(screen.getByText("Prueba con otro estado o limpia los filtros.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("un error de la API se ve en línea y 'Reintentar' vuelve a pedir", async () => {
    useApi();
    let fail = true;
    server.use(
      http.get(apiUrl("/applications"), () =>
        fail
          ? HttpResponse.json(
              {
                code: "VALIDATION_ERROR",
                message: "Filtro inválido.",
                details: [],
                request_id: "r",
              },
              { status: 400 },
            )
          : HttpResponse.json({
              items: [makeApp(1)],
              page: 1,
              page_size: 20,
              total: 1,
              next: null,
              previous: null,
            }),
      ),
    );
    renderWithProviders(<ApplicationsListScreen />);
    expect(await screen.findByText("No pudimos cargar las solicitudes")).toBeInTheDocument();
    expect(screen.getByText("Filtro inválido.")).toBeInTheDocument();

    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("SOL-000001")).toBeInTheDocument();
  });

  it("muestra el esqueleto mientras carga", async () => {
    useApi();
    renderWithProviders(<ApplicationsListScreen />);
    expect(screen.getByRole("status", { name: "Cargando solicitudes" })).toBeInTheDocument();
    await screen.findByText("SOL-000001");
  });

  it("avisa la inactividad del comprador y la solicitud que ya no cumple para radicar", async () => {
    useApi([
      makeApp(1, { buyer_inactive: true, last_buyer_activity_at: "2026-11-08T15:00:00Z" }),
      makeApp(2, { buyer_inactive: true, last_buyer_activity_at: null }),
      makeApp(3, {
        status: "READY_TO_FILE",
        status_label: "Lista para radicar",
        ready_to_file_blocked: true,
      }),
      makeApp(4, { buyer_inactive: false, ready_to_file_blocked: false }),
    ]);
    await renderList();

    const row = (code: string) => screen.getByText(code).closest("tr")!;
    expect(
      within(row("SOL-000001")).getByText("Sin actividad del comprador desde 8 nov 2026"),
    ).toBeInTheDocument();
    expect(within(row("SOL-000002")).getByText("El comprador aún no entra")).toBeInTheDocument();
    expect(within(row("SOL-000003")).getByText("Ya no cumple para radicar")).toBeInTheDocument();
    expect(within(row("SOL-000003")).getByText("Lista para radicar")).toHaveAttribute(
      "data-tone",
      "accent",
    );
    expect(row("SOL-000004").querySelector("[data-flag]")).toBeNull();
  });

  it("sin banco, monto, completitud ni tipo muestra 'Sin banco' y '—'", async () => {
    useApi([
      makeApp(1, {
        bank_product: null,
        requested_amount_cop: null,
        completeness_pct: null,
        participants_summary: { co_applicants: 1, solidary_debtors: 2 },
      }),
    ]);
    await renderList();
    const row = screen.getByText("SOL-000001").closest("tr")!;
    expect(within(row).getByText("Sin banco")).toBeInTheDocument();
    expect(within(row).getAllByText("—")).toHaveLength(3);
    expect(
      within(row).getByText("+ 1 co-solicitante · + 2 deudores solidarios"),
    ).toBeInTheDocument();
    expect(within(row).getByText("Vivienda nueva")).toBeInTheDocument();
  });

  it("muestra los datos de la fila con su formato", async () => {
    useApi([
      makeApp(1, {
        bank_product: { ...makeApp(1).bank_product!, bank: BOGOTA },
        participants_summary: { co_applicants: 2, solidary_debtors: 1 },
      }),
    ]);
    await renderList();
    const row = screen.getByText("SOL-000001").closest("tr")!;
    expect(within(row).getByRole("link", { name: "SOL-000001" })).toHaveAttribute(
      "href",
      "/solicitudes/app-1",
    );
    expect(within(row).getByText("Banco de Bogotá")).toHaveAttribute("title", "Banco de Bogotá");
    expect(within(row).getByText("+ 2 co-solicitantes · + 1 deudor solidario")).toBeInTheDocument();
    expect(within(row).getByText("Crédito hipotecario")).toBeInTheDocument();
    expect(within(row).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "62");
    expect(row.textContent).toContain("294.000.000");
  });

  it("un clic o Enter en la fila abre el expediente", async () => {
    useApi();
    const user = await renderList();
    const row = screen.getByText("SOL-000002").closest("tr")!;

    await user.click(within(row).getByText("Persona 2"));
    expect(nav.push).toHaveBeenCalledWith("/solicitudes/app-2");

    nav.push.mockClear();
    act(() => row.focus());
    await user.keyboard("{Enter}");
    expect(nav.push).toHaveBeenCalledWith("/solicitudes/app-2");
  });

  it("en móvil muestra tarjetas, el botón de filtros y los chips activos", async () => {
    setMobile(true);
    go("?purpose=NEW");
    useApi([makeApp(1, { buyer_inactive: true, completeness_pct: null })]);
    const user = userEvent.setup();
    renderWithProviders(<ApplicationsListScreen />);

    const cards = await screen.findByRole("list", { name: "Solicitudes" });
    expect(within(cards).getByText("SOL-000001")).toBeInTheDocument();
    expect(within(cards).getByText("Persona 1")).toBeInTheDocument();
    expect(within(cards).getByText("Documentos en revisión")).toBeInTheDocument();
    expect(within(cards).getByText("El comprador aún no entra")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    // Chip del filtro activo, con su etiqueta del catálogo.
    expect(await screen.findByText("Vivienda nueva", { selector: "b" })).toBeInTheDocument();
    await user.click(within(cards).getByText("Persona 1"));
    expect(nav.push).toHaveBeenCalledWith("/solicitudes/app-1");

    // Hoja de filtros.
    await user.click(screen.getByRole("button", { name: "Filtros (1)" }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("combobox", { name: "Filtrar por banco" })).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Ver resultados" }));

    await user.click(
      screen.getByRole("button", { name: "Quitar filtro Finalidad: Vivienda nueva" }),
    );
    await waitFor(() => expect(window.location.search).toBe(""));
  });
});
