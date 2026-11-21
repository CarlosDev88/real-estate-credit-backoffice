import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { barWidth } from "@/features/dashboard/bar-list";
import {
  ADMIN_ME,
  ADVISORS,
  BANK_RESULTS,
  BANKS,
  BOOTSTRAP,
  BROKER_ME,
  BROKER_SUMMARY,
  EMPTY_FUNNEL,
  FILTER_OUT_OF_SCOPE,
  FUNNEL,
  PERMISSION_DENIED,
  SUMMARY,
  WORKLOAD,
} from "@/features/dashboard/dashboard.fixtures";
import {
  apiFilters,
  EMPTY_FILTERS,
  hasActiveFilters,
  parseDashboardFilters,
  serializeDashboardFilters,
} from "@/features/dashboard/dashboard-params";
import { DashboardScreen } from "@/features/dashboard/dashboard-screen";
import { filterErrorsOf, isFilterError, isForbidden } from "@/features/dashboard/queries";
import { ApiError } from "@/lib/api/errors";
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
    usePathname: () => "/dashboard",
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

type Handler = Parameters<typeof server.use>[0];

/** Cada bloque guarda las query strings que recibió. */
function mockApi(
  overrides: Partial<Record<"me" | "summary" | "funnel" | "workload" | "bank", Handler>> = {},
) {
  const calls: Record<string, string[]> = { summary: [], funnel: [], workload: [], bank: [] };
  const block = (name: string, path: string, body: unknown) =>
    http.get(apiUrl(path), ({ request }) => {
      calls[name]?.push(new URL(request.url).search);
      return HttpResponse.json(body as object);
    });
  server.use(
    overrides.me ?? http.get(apiUrl("/auth/me"), () => HttpResponse.json(ADMIN_ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/banks"), () => HttpResponse.json(BANKS)),
    http.get(apiUrl("/users"), () => HttpResponse.json(ADVISORS)),
    overrides.summary ?? block("summary", "/dashboard/summary", SUMMARY),
    overrides.funnel ?? block("funnel", "/dashboard/funnel", FUNNEL),
    overrides.workload ?? block("workload", "/dashboard/workload", WORKLOAD),
    overrides.bank ?? block("bank", "/dashboard/bank-results", BANK_RESULTS),
  );
  return calls;
}

describe("filtros en la URL", () => {
  it("lee los filtros, ignora fechas mal escritas y no escribe los vacíos", () => {
    const parsed = parseDashboardFilters(
      new URLSearchParams("date_from=2026-11-01&date_to=18/11/2026&bank_id=b-1&purpose_code= "),
    );
    expect(parsed).toEqual({ ...EMPTY_FILTERS, date_from: "2026-11-01", bank_id: "b-1" });
    expect(serializeDashboardFilters(parsed)).toBe("date_from=2026-11-01&bank_id=b-1");
    expect(serializeDashboardFilters(EMPTY_FILTERS)).toBe("");
    expect(apiFilters(parsed)).toEqual({ date_from: "2026-11-01", bank_id: "b-1" });
    expect(hasActiveFilters(parsed)).toBe(true);
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
  });
});

describe("errores de los filtros", () => {
  const scope = new ApiError(403, "FILTER_OUT_OF_SCOPE", "Fuera", [
    { field: "advisor_id", code: "FILTER_OUT_OF_SCOPE", message: "Fuera de tu alcance." },
  ]);
  const invalid = new ApiError(400, "VALIDATION_ERROR", "Inválido", [
    { field: "date_from", code: "INVALID", message: "Debe ser anterior." },
    { field: "date_from", code: "INVALID", message: "Otro mensaje." },
    { field: "otro", code: "INVALID", message: "No es un filtro." },
  ]);
  const denied = new ApiError(403, "PERMISSION_DENIED", "Sin permiso");

  it("distingue el error de un filtro del permiso negado", () => {
    expect(isFilterError(scope)).toBe(true);
    expect(isFilterError(invalid)).toBe(true);
    expect(isFilterError(denied)).toBe(false);
    expect(isFilterError(new Error("x"))).toBe(false);
    expect(isForbidden(denied)).toBe(true);
    expect(isForbidden(scope)).toBe(false);
    expect(isForbidden(null)).toBe(false);
  });

  it("toma el primer mensaje de cada filtro del primer error de filtro", () => {
    expect(filterErrorsOf([null, denied, invalid, scope])).toEqual({
      date_from: "Debe ser anterior.",
    });
    expect(filterErrorsOf([null, denied])).toEqual({});
  });
});

describe("barras", () => {
  it("ancho proporcional, visible aunque sea pequeño y nunca más de 100 %", () => {
    expect(barWidth(5, 10)).toBe(50);
    expect(barWidth(1, 1000)).toBe(1.5);
    expect(barWidth(0, 10)).toBe(0);
    expect(barWidth(3, 0)).toBe(0);
    expect(barWidth(20, 10)).toBe(100);
  });
});

describe("DashboardScreen", { timeout: 30_000 }, () => {
  it("muestra las cifras, la foto por estado, el embudo y las tablas del administrador", async () => {
    mockApi();
    const user = userEvent.setup();
    renderWithProviders(<DashboardScreen />);

    expect(await screen.findByText("Periodo: 1 nov 2026 – 18 nov 2026")).toBeInTheDocument();
    const tiles = screen.getByRole("region", { name: "Cifras del periodo" });
    expect(within(tiles).getByText("1.234")).toBeInTheDocument();
    expect(within(tiles).getByText(/^\$\s?7\.938\.000\.000$/)).toBeInTheDocument();
    // Las tareas enlazan a "Mi día" con el filtro.
    expect(within(tiles).getByRole("link", { name: /Tareas vencidas/ })).toHaveAttribute(
      "href",
      "/mi-dia?tab=tareas&due=overdue",
    );
    expect(within(tiles).getByRole("link", { name: /Tareas para hoy/ })).toHaveAttribute(
      "href",
      "/mi-dia?tab=tareas&due=today",
    );

    // Foto por estado: los estados en 0 se ocultan hasta "Mostrar todos".
    const states = screen.getByRole("list", { name: "Solicitudes por estado" });
    expect(within(states).getAllByRole("listitem")).toHaveLength(3);
    expect(within(states).queryByText("Radicada")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mostrar todos (4)" }));
    expect(within(states).getByText("Radicada")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ocultar los que están en 0" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Embudo: la tabla es el gráfico.
    const funnel = screen.getByRole("table", { name: "Embudo de solicitudes del periodo" });
    const docs = within(funnel).getByRole("row", { name: /Documentos completos/ });
    expect(within(docs).getAllByText("49 %")).toHaveLength(2);
    expect(within(funnel).getByRole("row", { name: /Creadas/ })).toHaveTextContent("—");

    const workload = await screen.findByRole("table", { name: "Carga por asesor" });
    expect(within(workload).getByText("Andrés Patiño")).toBeInTheDocument();
    const banks = screen.getByRole("table", { name: "Resultados por banco" });
    expect(within(banks).getByRole("row", { name: /Bancolombia/ })).toHaveTextContent("0,8");
    expect(within(banks).getByRole("row", { name: /Banco de Bogotá/ })).toHaveTextContent("—");
  });

  it("mientras cargan, las cifras ya muestran sus tarjetas sin número (PERF-02)", async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    mockApi({
      summary: http.get(apiUrl("/dashboard/summary"), async () => {
        await held;
        return HttpResponse.json(SUMMARY);
      }),
    });
    renderWithProviders(<DashboardScreen />);

    const tiles = await screen.findByRole("region", { name: "Cifras del periodo" });
    await within(tiles).findByRole("status");
    expect(within(tiles).getByRole("status")).toHaveTextContent("Cargando cifras");
    // Las 7 tarjetas del administrador (con tareas y montos), con su etiqueta y sin enlace.
    for (const label of ["Clientes creados", "Tareas para hoy", "Monto desembolsado"]) {
      expect(within(tiles).getByText(label)).toBeInTheDocument();
    }
    expect(within(tiles).queryByRole("link")).toBeNull();

    release();
    expect(await within(tiles).findByText("1.234")).toBeInTheDocument();
    expect(within(tiles).getByRole("link", { name: /Tareas vencidas/ })).toBeInTheDocument();
  });

  it("cambiar un filtro lo escribe en la URL y vuelve a pedir los bloques con él", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<DashboardScreen />);

    await screen.findByRole("table", { name: "Carga por asesor" });
    await user.click(screen.getByRole("combobox", { name: "Filtrar por banco" }));
    await user.click(await screen.findByRole("option", { name: "Bancolombia" }));

    await waitFor(() => expect(window.location.search).toBe("?bank_id=b-1"));
    await waitFor(() => expect(calls.summary).toContain("?bank_id=b-1"));
    expect(calls.funnel).toContain("?bank_id=b-1");
    expect(calls.bank).toContain("?bank_id=b-1");

    // Fechas: el campo muestra el periodo de la API y escribe la que se cambia.
    const from = screen.getByLabelText("Desde");
    expect(from).toHaveValue("2026-11-01");
    // jsdom no escribe en `type="date"` tecla por tecla: el navegador manda la fecha completa.
    fireEvent.change(from, { target: { value: "2026-10-05" } });
    await waitFor(() => expect(window.location.search).toContain("date_from=2026-10-05"));

    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("un filtro fuera del alcance se muestra en el filtro, no como falla de la página", async () => {
    window.history.replaceState(null, "", "/dashboard?advisor_id=otro");
    const scoped = http.get(apiUrl("/dashboard/:block"), () =>
      HttpResponse.json(FILTER_OUT_OF_SCOPE, { status: 403 }),
    );
    mockApi({ summary: scoped, funnel: scoped, workload: scoped, bank: scoped });
    renderWithProviders(<DashboardScreen />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Asesor: Este filtro está fuera de tu alcance.");
    expect(screen.getByRole("combobox", { name: "Filtrar por asesor" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    // Los bloques avisan sin "Reintentar"; los de carga y bancos no se ocultan.
    expect(screen.getAllByText(/Corrige el filtro marcado/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Carga por asesor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("broker: solo conteos, sin montos ni tareas, y sin carga ni bancos (403)", async () => {
    const denied = http.get(apiUrl("/dashboard/:block"), () =>
      HttpResponse.json(PERMISSION_DENIED, { status: 403 }),
    );
    mockApi({
      me: http.get(apiUrl("/auth/me"), () => HttpResponse.json(BROKER_ME)),
      summary: http.get(apiUrl("/dashboard/summary"), () => HttpResponse.json(BROKER_SUMMARY)),
      funnel: http.get(apiUrl("/dashboard/funnel"), () => HttpResponse.json(EMPTY_FUNNEL)),
      workload: denied,
      bank: denied,
    });
    renderWithProviders(<DashboardScreen />);

    const tiles = await screen.findByRole("region", { name: "Cifras del periodo" });
    await within(tiles).findByText("Clientes creados");
    expect(within(tiles).queryByText(/Monto/)).not.toBeInTheDocument();
    expect(within(tiles).queryByText(/Tareas/)).not.toBeInTheDocument();
    expect(await screen.findByText("No se crearon solicitudes en el periodo")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Carga por asesor" })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("heading", { name: "Resultados por banco" })).not.toBeInTheDocument();
    // Sin `users.read` ni `banks.read`: solo el filtro de finalidad.
    expect(screen.queryByRole("combobox", { name: "Filtrar por asesor" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Filtrar por banco" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Filtrar por finalidad" })).toBeInTheDocument();
  });

  it("un bloque caído no tumba la página y se puede reintentar", async () => {
    let fail = true;
    mockApi({
      funnel: http.get(apiUrl("/dashboard/funnel"), () =>
        fail
          ? HttpResponse.json(
              { code: "SERVER_ERROR", message: "Falló", details: [], request_id: "r" },
              { status: 500, headers: { "X-Request-ID": "r" } },
            )
          : HttpResponse.json(FUNNEL),
      ),
    });
    const user = userEvent.setup();
    renderWithProviders(<DashboardScreen />);

    const retry = await screen.findByRole("button", { name: "Reintentar" }, { timeout: 8000 });
    expect(screen.getByText("No pudimos cargar el embudo.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Solicitudes por estado" })).toBeInTheDocument();

    fail = false;
    await user.click(retry);
    expect(
      await screen.findByRole("table", { name: "Embudo de solicitudes del periodo" }),
    ).toBeInTheDocument();
  });

  it("vacíos: sin asesores, sin radicaciones y sin solicitudes en ningún estado", async () => {
    mockApi({
      summary: http.get(apiUrl("/dashboard/summary"), () =>
        HttpResponse.json({ ...SUMMARY, snapshot: [SUMMARY.snapshot[2]] }),
      ),
      workload: http.get(apiUrl("/dashboard/workload"), () => HttpResponse.json({ advisors: [] })),
      bank: http.get(apiUrl("/dashboard/bank-results"), () =>
        HttpResponse.json({ ...BANK_RESULTS, banks: [] }),
      ),
    });
    renderWithProviders(<DashboardScreen />);

    expect(await screen.findByText("No hay solicitudes en ningún estado")).toBeInTheDocument();
    expect(await screen.findByText("No hay asesores con solicitudes abiertas")).toBeInTheDocument();
    expect(await screen.findByText("No hay radicaciones en el periodo")).toBeInTheDocument();
  });
});

describe("DashboardScreen en móvil", { timeout: 30_000 }, () => {
  it("filtros en una hoja inferior con chips, y tarjetas en lugar de tablas", async () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("max-width: 860px"),
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    );
    window.history.replaceState(null, "", "/dashboard?purpose_code=NEW&date_from=2026-11-01");
    mockApi();
    const user = userEvent.setup();
    renderWithProviders(<DashboardScreen />);

    expect(await screen.findByRole("list", { name: "Carga por asesor" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Resultados por banco" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Carga por asesor" })).not.toBeInTheDocument();

    const chips = screen.getByRole("list", { name: "Filtros activos" });
    await within(chips).findByText("Vivienda nueva");
    expect(within(chips).getByText("1 nov 2026 – 18 nov 2026")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Quitar filtro Periodo: 1 nov 2026 – 18 nov 2026" }),
    );
    await waitFor(() => expect(window.location.search).toBe("?purpose_code=NEW"));

    await user.click(screen.getByRole("button", { name: "Filtros (1)" }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByLabelText("Desde")).toHaveValue("2026-11-01");
    await user.click(within(sheet).getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });
});
