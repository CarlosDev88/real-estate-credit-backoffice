import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { MyDayScreen } from "@/features/workday/my-day-screen";
import { tasksQuery } from "@/features/workday/queries";
import {
  ADMIN_ME,
  ADVISOR_ME,
  ADVISORS,
  APPLICATION,
  APPLICATION_2,
  BANKS,
  BOOTSTRAP,
  COMPLETED_TASK,
  OPPORTUNITY_TASK,
  SUMMARY,
  TASK,
  taskPage,
  trayPage,
} from "@/features/workday/workday.fixtures";
import {
  parseMyDayParams,
  parseOrdering,
  serializeMyDayParams,
  tasksOf,
} from "@/features/workday/workday-params";
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
    usePathname: () => "/mi-dia",
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

const TITLE_SELECTOR = ".ant-modal-title, .ant-drawer-title";

/** El modal o la hoja con ese título (Ant Design no le da nombre accesible al `dialog`). */
async function dialogNamed(title: string): Promise<HTMLElement> {
  const heading = await screen.findByText(title, { selector: TITLE_SELECTOR });
  const dialog = heading.closest<HTMLElement>('[role="dialog"]');
  if (!dialog) throw new Error(`Sin dialog para ${title}`);
  return dialog;
}

interface Calls {
  tray: string[];
  summary: string[];
  tasks: string[];
  posts: { url: string; body: unknown }[];
  patches: { url: string; body: unknown }[];
}

function mockApi(overrides: Partial<Record<"me" | "tray" | "tasks", Handler>> = {}): Calls {
  const calls: Calls = { tray: [], summary: [], tasks: [], posts: [], patches: [] };
  server.use(
    overrides.me ?? http.get(apiUrl("/auth/me"), () => HttpResponse.json(ADVISOR_ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/banks"), () => HttpResponse.json(BANKS)),
    http.get(apiUrl("/users"), () => HttpResponse.json(ADVISORS)),
    http.get(apiUrl("/workday/summary"), ({ request }) => {
      calls.summary.push(new URL(request.url).search);
      return HttpResponse.json(SUMMARY);
    }),
    overrides.tray ??
      http.get(apiUrl("/workday/applications"), ({ request }) => {
        calls.tray.push(new URL(request.url).search);
        return HttpResponse.json(trayPage([APPLICATION, APPLICATION_2], 35));
      }),
    overrides.tasks ??
      http.get(apiUrl("/tasks"), ({ request }) => {
        const url = new URL(request.url);
        calls.tasks.push(url.search);
        if (url.searchParams.get("page_size") === "1") return HttpResponse.json(taskPage([], 2));
        return HttpResponse.json(taskPage([TASK, OPPORTUNITY_TASK, COMPLETED_TASK]));
      }),
    http.post(apiUrl("/tasks"), async ({ request }) => {
      calls.posts.push({ url: request.url, body: await request.json() });
      return HttpResponse.json(TASK, { status: 201 });
    }),
    http.post(apiUrl("/tasks/:id/:action"), async ({ request }) => {
      const text = await request.text();
      calls.posts.push({ url: request.url, body: text ? JSON.parse(text) : null });
      return HttpResponse.json({ ...TASK, status: "COMPLETED" });
    }),
    http.patch(apiUrl("/tasks/:id"), async ({ request }) => {
      calls.patches.push({ url: request.url, body: await request.json() });
      return HttpResponse.json(TASK);
    }),
  );
  return calls;
}

describe("estado de Mi día en la URL", () => {
  it("lee los valores por defecto, abre las tareas con `due` y no escribe lo por defecto", () => {
    const params = parseMyDayParams(new URLSearchParams("due=overdue&page=0&page_size=7"));
    expect(params.tab).toBe("tareas");
    expect(params.page).toBe(1);
    expect(params.page_size).toBe(20);
    expect(params.task_status).toBe("PENDING");
    expect(serializeMyDayParams(params)).toBe("tab=tareas&due=overdue");

    const tray = parseMyDayParams(new URLSearchParams("tab=bandeja&due=today&task_status=x"));
    expect(tray.tab).toBe("bandeja");
    expect(tray.task_status).toBe("PENDING");
    // `bandeja` con `due` se escribe, para no saltar a las tareas al recargar.
    expect(serializeMyDayParams(tray)).toBe("tab=bandeja&due=today");
    expect(serializeMyDayParams(parseMyDayParams(new URLSearchParams("due=nunca")))).toBe("");
  });

  it("solo acepta los campos de orden de la API", () => {
    expect(parseOrdering("-days_in_stage")).toBe("-days_in_stage");
    expect(parseOrdering("code")).toBe("code");
    expect(parseOrdering("-client")).toBe("");
    expect(parseOrdering(null)).toBe("");
  });

  it("arma la consulta de tareas: el usuario actual por defecto, `all` sin filtro", () => {
    const base = tasksOf(parseMyDayParams(new URLSearchParams("")));
    expect(tasksQuery(base, "u-1")).toEqual({
      assigned_to_id: "u-1",
      status: "PENDING",
      page: 1,
      page_size: 20,
    });
    const all = tasksOf(
      parseMyDayParams(new URLSearchParams("assigned_to_id=all&task_status=all&priority=HIGH")),
    );
    expect(tasksQuery(all, "u-1")).toEqual({ priority: "HIGH", page: 1, page_size: 20 });
  });
});

describe("Mi día: bandeja", { timeout: 30_000 }, () => {
  it("muestra los segmentos y la bandeja; un segmento filtra y vuelve a la página 1", async () => {
    window.history.replaceState(null, "", "/mi-dia?page=2");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);

    const table = await screen.findByRole("table", { name: "Bandeja de solicitudes" });
    const row = within(table).getByRole("row", { name: /SOL-000008/ });
    expect(within(row).getByRole("link", { name: "SOL-000008" })).toHaveAttribute(
      "href",
      "/solicitudes/app-8",
    );
    expect(row).toHaveTextContent("Hacer seguimiento a los datos del comprador");
    expect(row).toHaveTextContent("11 días");
    expect(row).toHaveTextContent("Comprador sin actividad");
    expect(row).toHaveTextContent("3 tareas pendientes");
    expect(within(table).getByRole("row", { name: /SOL-000001/ })).toHaveTextContent("1 día");

    const segments = screen.getByRole("group", { name: "Segmentos de atención" });
    expect(within(segments).getByRole("button", { name: /35\s*Todas/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(within(segments).getByRole("button", { name: /Listas para radicar/ }));
    await waitFor(() => expect(window.location.search).toBe("?attention=READY_TO_FILE"));
    await waitFor(() =>
      expect(calls.tray).toContain("?attention=READY_TO_FILE&page=1&page_size=20"),
    );
    // El resumen no recibe el segmento.
    expect(calls.summary.every((q) => !q.includes("attention"))).toBe(true);

    // Otro clic en el mismo segmento lo quita.
    await user.click(within(segments).getByRole("button", { name: /Listas para radicar/ }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("filtros y orden en la URL: etapa del catálogo (solo no terminales), orden y búsqueda", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);
    await screen.findByRole("table", { name: "Bandeja de solicitudes" });

    await user.click(screen.getByRole("combobox", { name: "Filtrar por etapa" }));
    expect(screen.queryByRole("option", { name: "Desembolsada" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("option", { name: "Borrador" }));
    await waitFor(() => expect(window.location.search).toBe("?stage=DRAFT"));
    await waitFor(() => expect(calls.summary).toContain("?stage=DRAFT"));

    // Ordenar por la columna.
    await user.click(screen.getByRole("button", { name: /Días en la etapa/ }));
    await waitFor(() => expect(window.location.search).toContain("ordering=-days_in_stage"));

    await user.type(screen.getByRole("searchbox", { name: /Buscar en la bandeja/ }), "Mariana");
    await waitFor(() => expect(window.location.search).toContain("search=Mariana"));

    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe("?ordering=-days_in_stage"));
  });

  it("crea una tarea desde una fila, vinculada a esa solicitud", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);

    await user.click(await screen.findByRole("button", { name: "Nueva tarea para SOL-000008" }));
    const dialog = await dialogNamed("Nueva tarea");
    expect(dialog).toHaveTextContent("SOL-000008 · Mariana Cárdenas Ríos");

    // Sin título no se envía.
    await user.click(within(dialog).getByRole("button", { name: "Crear tarea" }));
    expect(await within(dialog).findByText("Escribe el título.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Título"), "Llamar al banco");
    fireEvent.change(within(dialog).getByLabelText(/Vence/), {
      target: { value: "2026-11-20T09:30" },
    });
    await user.click(within(dialog).getByRole("button", { name: "Crear tarea" }));

    await waitFor(() => expect(calls.posts).toHaveLength(1));
    const body = calls.posts[0]?.body as Record<string, unknown>;
    expect(body).toMatchObject({
      title: "Llamar al banco",
      application_id: "app-8",
      priority_code: "MEDIUM",
    });
    expect(typeof body.due_at).toBe("string");
    expect(body).not.toHaveProperty("assigned_to_id");
    expect(await screen.findByText("Tarea creada")).toBeInTheDocument();
  });

  it("una página que ya no existe vuelve a la primera", async () => {
    window.history.replaceState(null, "", "/mi-dia?page=9");
    mockApi({
      tray: http.get(apiUrl("/workday/applications"), ({ request }) =>
        new URL(request.url).searchParams.get("page") === "9"
          ? HttpResponse.json(
              { code: "NOT_FOUND", message: "Página inválida.", details: [], request_id: "r" },
              { status: 404 },
            )
          : HttpResponse.json(trayPage([APPLICATION])),
      ),
    });
    renderWithProviders(<MyDayScreen />);
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(
      await screen.findByRole("table", { name: "Bandeja de solicitudes" }),
    ).toBeInTheDocument();
  });

  it("bandeja vacía y bandeja con error", async () => {
    let fail = true;
    mockApi({
      tray: http.get(apiUrl("/workday/applications"), () =>
        fail
          ? HttpResponse.json(
              { code: "SERVER_ERROR", message: "Falló", details: [], request_id: "r" },
              { status: 500, headers: { "X-Request-ID": "r" } },
            )
          : HttpResponse.json(trayPage([])),
      ),
    });
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);
    const retry = await screen.findByRole("button", { name: "Reintentar" }, { timeout: 8000 });
    expect(screen.getByText("No pudimos cargar la bandeja")).toBeInTheDocument();
    fail = false;
    await user.click(retry);
    expect(await screen.findByText("No tienes solicitudes abiertas")).toBeInTheDocument();
  });
});

describe("Mi día: tareas", { timeout: 30_000 }, () => {
  it("lista las tareas del usuario con sus filtros, y completa una", async () => {
    window.history.replaceState(null, "", "/mi-dia?tab=tareas&due=overdue");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);

    const table = await screen.findByRole("table", { name: "Tareas" });
    expect(calls.tasks).toContain(
      "?assigned_to_id=u-lucia&due=overdue&status=PENDING&page=1&page_size=20",
    );
    expect(screen.getByRole("tab", { name: /Mis tareas/ })).toHaveTextContent("2");

    const first = within(table).getByRole("row", { name: /Llamar a Mariana/ });
    expect(first).toHaveTextContent("Vencida");
    expect(within(first).getByRole("link", { name: "SOL-000008" })).toHaveAttribute(
      "href",
      "/solicitudes/app-8",
    );
    const opportunity = within(table).getByRole("row", { name: /Enviar simulación/ });
    expect(opportunity).toHaveTextContent("Oportunidad");
    expect(opportunity).toHaveTextContent("Sin fecha");
    // Una tarea que ya no está pendiente no tiene acciones.
    const done = within(table).getByRole("row", { name: /Tarea hecha/ });
    expect(within(done).queryByRole("button")).not.toBeInTheDocument();
    // Sin `users.read` no hay filtro de responsable.
    expect(
      screen.queryByRole("combobox", { name: "Filtrar por responsable" }),
    ).not.toBeInTheDocument();

    await user.click(within(first).getByRole("button", { name: "Completar Llamar a Mariana" }));
    const dialog = await dialogNamed("Completar tarea");
    await user.click(within(dialog).getByRole("button", { name: "Completar" }));
    await waitFor(() =>
      expect(calls.posts.map((p) => p.url)).toContain(apiUrl("/tasks/t-1/complete")),
    );
    expect(await screen.findByText("Tarea completada")).toBeInTheDocument();
  });

  it("cancelar pide el motivo; editar manda los cambios", async () => {
    window.history.replaceState(null, "", "/mi-dia?tab=tareas");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);
    const table = await screen.findByRole("table", { name: "Tareas" });
    const first = within(table).getByRole("row", { name: /Llamar a Mariana/ });

    await user.click(within(first).getByRole("button", { name: "Cancelar Llamar a Mariana" }));
    const cancel = await dialogNamed("Cancelar tarea");
    await user.click(within(cancel).getByRole("button", { name: "Cancelar tarea" }));
    expect(await within(cancel).findByText("Escribe el motivo.")).toBeInTheDocument();
    await user.type(within(cancel).getByLabelText("Motivo"), "Ya no aplica");
    await user.click(within(cancel).getByRole("button", { name: "Cancelar tarea" }));
    await waitFor(() =>
      expect(calls.posts).toContainEqual({
        url: apiUrl("/tasks/t-1/cancel"),
        body: { reason: "Ya no aplica" },
      }),
    );
    expect(await screen.findByText("Tarea cancelada")).toBeInTheDocument();

    await user.click(within(first).getByRole("button", { name: "Editar Llamar a Mariana" }));
    const edit = await dialogNamed("Editar tarea");
    expect(edit).toHaveTextContent("Solicitud SOL-000008 · Mariana Cárdenas Ríos");
    const title = within(edit).getByLabelText("Título");
    expect(title).toHaveValue("Llamar a Mariana");
    await user.clear(title);
    await user.type(title, "Llamar a Mariana hoy");
    fireEvent.change(within(edit).getByLabelText(/Vence/), { target: { value: "" } });
    await user.click(within(edit).getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(calls.patches).toHaveLength(1));
    expect(calls.patches[0]).toEqual({
      url: apiUrl("/tasks/t-1"),
      body: {
        title: "Llamar a Mariana hoy",
        description: "Confirmar ingresos.",
        due_at: null,
        priority_code: "HIGH",
      },
    });
  });

  it("el administrador elige el responsable y puede ver las de otro asesor", async () => {
    window.history.replaceState(null, "", "/mi-dia?tab=tareas");
    const calls = mockApi({ me: http.get(apiUrl("/auth/me"), () => HttpResponse.json(ADMIN_ME)) });
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);
    await screen.findByRole("table", { name: "Tareas" });

    await user.click(screen.getByRole("combobox", { name: "Filtrar por responsable" }));
    await user.click(await screen.findByRole("option", { name: "Lucía Rojas" }));
    await waitFor(() => expect(window.location.search).toContain("assigned_to_id=u-lucia"));
    await waitFor(() =>
      expect(calls.tasks.some((q) => q.startsWith("?assigned_to_id=u-lucia&status=PENDING"))).toBe(
        true,
      ),
    );
    // Con otro responsable, se ve la columna.
    expect(await screen.findByRole("columnheader", { name: "Responsable" })).toBeInTheDocument();

    // "Nueva tarea" sin fila: hay que elegir la solicitud; el responsable es el admin.
    await user.click(screen.getByRole("button", { name: "Nueva tarea" }));
    const dialog = await dialogNamed("Nueva tarea");
    await user.type(within(dialog).getByLabelText("Título"), "Revisar");
    await user.click(within(dialog).getByRole("button", { name: "Crear tarea" }));
    expect(await within(dialog).findByText("Elige la solicitud.")).toBeInTheDocument();

    await user.click(within(dialog).getByLabelText("Solicitud"));
    await user.click(
      await screen.findByRole("option", { name: "SOL-000001 · Laura Rincón Castaño" }),
    );
    expect(within(dialog).getByLabelText("Responsable")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Crear tarea" }));
    await waitFor(() => expect(calls.posts).toHaveLength(1));
    expect(calls.posts[0]?.body).toMatchObject({
      title: "Revisar",
      application_id: "app-1",
      assigned_to_id: "u-admin",
    });
  });

  it("sin tareas: vacío con y sin filtros", async () => {
    window.history.replaceState(null, "", "/mi-dia?tab=tareas&priority=LOW");
    mockApi({ tasks: http.get(apiUrl("/tasks"), () => HttpResponse.json(taskPage([]))) });
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);
    expect(await screen.findByText("No hay tareas con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    expect(await screen.findByText("No tienes tareas pendientes")).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=tareas");
  });
});

describe("Mi día en móvil", { timeout: 30_000 }, () => {
  it("tarjetas en lugar de tablas y filtros en la hoja inferior", async () => {
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
    window.history.replaceState(null, "", "/mi-dia?purpose=NEW");
    mockApi();
    const user = userEvent.setup();
    renderWithProviders(<MyDayScreen />);

    const list = await screen.findByRole("list", { name: "Bandeja de solicitudes" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
    const chips = screen.getByRole("list", { name: "Filtros activos" });
    expect(await within(chips).findByText("Vivienda nueva")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Quitar filtro Finalidad: Vivienda nueva" }),
    );
    await waitFor(() => expect(window.location.search).toBe(""));

    await user.click(screen.getByRole("button", { name: "Filtros" }));
    expect(await dialogNamed("Filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ver resultados" }));

    await user.click(screen.getByRole("tab", { name: /Mis tareas/ }));
    expect(await screen.findByRole("list", { name: "Tareas" })).toBeInTheDocument();
  });
});
