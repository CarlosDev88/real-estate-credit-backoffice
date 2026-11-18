import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { parseBrokerParams, serializeBrokerParams } from "@/features/broker/broker-params";
import { BrokerScreen } from "@/features/broker/broker-screen";
import type { ApplicationSummary, BrokerOpportunity } from "@/features/broker/queries";
import { apiError, CLIENTS_BOOTSTRAP, page } from "@/features/clients/clients.fixtures";
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
    usePathname: () => "/prospectos",
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

// Datos inventados con la forma del contrato.
const BROKER_ME = {
  id: "u-bruno",
  name: "Bruno Salas",
  email: "bruno@example.com",
  role: "INDEPENDENT_BROKER",
  role_label: "Broker independiente",
  roles: ["INDEPENDENT_BROKER"],
  permissions: [
    "applications.read",
    "buyer_access.create",
    "clients.create",
    "clients.read",
    "dashboard.read",
    "opportunities.create",
    "opportunities.read",
    "projects.read",
  ],
  scope: { assigned_applications_only: false, partner_id: null },
};

const OPPORTUNITY: BrokerOpportunity = {
  id: "op-1",
  client_id: "cl-1",
  client_name: "Laura Gómez Vélez",
  project_id: "pr-1",
  project_name: "Torres del Parque",
  status: "NEW",
  advisor_name: null,
  created_at: "2026-11-12T15:00:00Z",
  updated_at: "2026-11-14T15:00:00Z",
};

const SUMMARY: ApplicationSummary = {
  id: "app-12",
  code: "SOL-000012",
  status: "WAITING_DOCUMENTS",
  status_label: "Esperando documentos",
  opportunity_id: "op-2",
  purpose: { code: "NEW_HOME", label: "Vivienda nueva" },
  client_name: "Andrés Mora",
  client_document_number: "****4521",
  bank_name: "Bancolombia",
  product_name: "Crédito hipotecario",
  advisor_name: "Lucía Rojas",
  current_stage_started_at: "2026-11-15T10:00:00Z",
  days_in_stage: 3,
  created_at: "2026-11-10T10:00:00Z",
  updated_at: "2026-11-15T10:00:00Z",
};

const BOOTSTRAP = {
  ...CLIENTS_BOOTSTRAP,
  catalogs: {
    ...CLIENTS_BOOTSTRAP.catalogs,
    buyer_access_channel: [
      {
        id: "ch-1",
        code: "COPY_LINK",
        label: "Copiar enlace",
        description: "",
        order: 1,
        active: true,
        parent_id: null,
        parent_code: null,
        metadata: {},
      },
    ],
  },
};

interface Calls {
  opportunities: string[];
  clients: unknown[];
  created: unknown[];
  links: { body: unknown; key: string | null }[];
}

function mockApi(
  options: {
    clientError?: object;
    opportunityFails?: number;
    opportunities?: BrokerOpportunity[];
  } = {},
): Calls {
  const calls: Calls = { opportunities: [], clients: [], created: [], links: [] };
  let failures = options.opportunityFails ?? 0;
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(BROKER_ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/dashboard/summary"), () =>
      HttpResponse.json({
        period: { date_from: "2026-11-01", date_to: "2026-11-18" },
        clients_created: 2,
        applications_created: 1,
        snapshot: [
          { status: "WAITING_DOCUMENTS", status_label: "Esperando documentos", count: 2 },
          { status: "FILED", status_label: "Radicada", count: 1 },
          { status: "DRAFT", status_label: "Borrador", count: 0 },
        ],
        tasks: { overdue: 0, due_today: 0 },
      }),
    ),
    http.get(apiUrl("/broker/opportunities"), ({ request }) => {
      calls.opportunities.push(new URL(request.url).search);
      return HttpResponse.json(page(options.opportunities ?? [OPPORTUNITY]));
    }),
    http.get(apiUrl("/applications"), () => HttpResponse.json(page([SUMMARY]))),
    http.get(apiUrl("/projects"), () =>
      HttpResponse.json(
        page([{ id: "pr-1", name: "Torres del Parque", partner: { id: "pa-1", name: "Andes" } }]),
      ),
    ),
    http.post(apiUrl("/clients"), async ({ request }) => {
      calls.clients.push(await request.json());
      if (options.clientError) return HttpResponse.json(options.clientError, { status: 409 });
      return HttpResponse.json({ id: "cl-new" }, { status: 201 });
    }),
    http.post(apiUrl("/opportunities"), async ({ request }) => {
      calls.created.push(await request.json());
      if (failures > 0) {
        failures -= 1;
        return HttpResponse.json(apiError("SERVICE_UNAVAILABLE", "Intenta de nuevo."), {
          status: 503,
          headers: { "X-Request-ID": "r-1" },
        });
      }
      return HttpResponse.json({ id: "op-new" }, { status: 201 });
    }),
    http.post(apiUrl("/applications/:id/buyer-access-links"), async ({ request }) => {
      calls.links.push({
        body: await request.json(),
        key: request.headers.get("Idempotency-Key"),
      });
      return HttpResponse.json(
        {
          id: "ln-1",
          application_id: "app-12",
          client_id: "cl-2",
          status: "PENDING",
          status_label: "Pendiente",
          delivery_channel: { code: "COPY_LINK", label: "Copiar enlace" },
          created_by: { id: "u-bruno", name: "Bruno Salas" },
          created_at: "2026-11-18T15:00:00Z",
          expires_at: "2026-11-21T15:00:00Z",
          consumed_at: null,
          revoked_at: null,
          session: null,
          url: "https://umbral.example/acceso?token=abc",
        },
        { status: 201 },
      );
    }),
  );
  return calls;
}

async function dialogNamed(title: string): Promise<HTMLElement> {
  const heading = await screen.findByText(title, { selector: ".ant-modal-title" });
  const dialog = heading.closest<HTMLElement>('[role="dialog"]');
  if (!dialog) throw new Error(`Sin dialog para ${title}`);
  return dialog;
}

function at(search: string) {
  window.history.replaceState(null, "", `/prospectos${search}`);
}

describe("parámetros de /prospectos", () => {
  it("el estado solo vale en la pestaña de prospectos", () => {
    const params = parseBrokerParams(new URLSearchParams("status=LOST&page=2"));
    expect(params).toMatchObject({ tab: "prospectos", status: "LOST", page: 2 });
    expect(serializeBrokerParams(params)).toBe("status=LOST&page=2");
    expect(parseBrokerParams(new URLSearchParams("tab=solicitudes&status=LOST")).status).toBe("");
    expect(parseBrokerParams(new URLSearchParams("status=OTRO")).status).toBe("");
  });
});

describe("inicio del broker", { timeout: 20_000 }, () => {
  it("muestra el resumen de estados y sus prospectos; el filtro va a la URL y a la API", async () => {
    at("");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<BrokerScreen />);

    const summary = await screen.findByRole("region", { name: "Estado de tus solicitudes" });
    expect(within(summary).getByText("Esperando documentos")).toBeInTheDocument();
    expect(within(summary).getByText("3 en total")).toBeInTheDocument();
    // Un estado en 0 no se lista.
    expect(within(summary).queryByText("Borrador")).toBeNull();

    const table = await screen.findByRole("table", { name: "Prospectos" });
    expect(within(table).getByText("Laura Gómez Vélez")).toBeInTheDocument();
    // `BrokerOpportunity` no trae `status_label`: el texto es del catálogo.
    expect(within(table).getByText("Nueva")).toBeInTheDocument();
    expect(within(table).getByText("Sin asesor todavía")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por estado" }));
    await user.click(await screen.findByRole("option", { name: "Asignada" }));
    await waitFor(() => expect(window.location.search).toBe("?status=ASSIGNED"));
    await waitFor(() => expect(calls.opportunities.at(-1)).toContain("status=ASSIGNED"));
  });

  it("lista sus solicitudes en resumen y envía el enlace con Idempotency-Key", async () => {
    at("?tab=solicitudes");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<BrokerScreen />);

    const table = await screen.findByRole("table", { name: "Solicitudes" });
    expect(within(table).getByText("SOL-000012")).toBeInTheDocument();
    expect(within(table).getByText("Esperando documentos")).toBeInTheDocument();
    expect(within(table).getByText("Bancolombia · Crédito hipotecario")).toBeInTheDocument();
    expect(within(table).getByText("3 días")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "Enviar enlace de SOL-000012" }));
    const modal = await dialogNamed("Enviar enlace al comprador");
    expect(within(modal).getByText("SOL-000012 · Andrés Mora")).toBeInTheDocument();
    await user.click(within(modal).getByRole("button", { name: "Generar enlace" }));

    expect(
      await within(modal).findByDisplayValue("https://umbral.example/acceso?token=abc"),
    ).toBeInTheDocument();
    expect(calls.links).toHaveLength(1);
    expect(calls.links[0]!.body).toEqual({ delivery_channel: "COPY_LINK", expires_in_hours: 72 });
    expect(calls.links[0]!.key).toMatch(/[0-9a-f-]{36}/);
  });

  it("registra un prospecto: cliente y oportunidad con origen broker", async () => {
    at("");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<BrokerScreen />);

    await user.click(await screen.findByRole("button", { name: "Nuevo prospecto" }));
    const modal = await dialogNamed("Nuevo prospecto");
    await user.click(within(modal).getByRole("button", { name: "Registrar prospecto" }));
    expect(await within(modal).findByText("Elige el tipo de documento.")).toBeInTheDocument();
    expect(calls.clients).toHaveLength(0);

    await user.click(within(modal).getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Cédula de ciudadanía" }));
    await user.type(within(modal).getByLabelText("Número de documento"), "1032445908");
    await user.type(within(modal).getByLabelText("Nombres"), "Laura");
    await user.type(within(modal).getByLabelText("Apellidos"), "Gómez");
    await user.type(within(modal).getByLabelText(/Celular/), "+57 300 123 4567");
    await user.type(within(modal).getByLabelText(/Nota para el asesor/), "Llamar en la tarde");
    await user.click(within(modal).getByRole("button", { name: "Registrar prospecto" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.clients[0]).toEqual({
      document_type_code: "CC",
      document_number: "1032445908",
      first_names: "Laura",
      last_names: "Gómez",
      phone: "+573001234567",
    });
    expect(calls.created[0]).toEqual({
      client_id: "cl-new",
      origin_type: "BROKER",
      project_id: null,
      notes: "Llamar en la tarde",
    });
    expect(await screen.findByText("Prospecto registrado")).toBeInTheDocument();
  });

  it("con un cliente que ya existe y ve, le agrega la oportunidad; si falla, reintenta sin crearlo otra vez", async () => {
    at("");
    const calls = mockApi({
      clientError: apiError("DUPLICATE_CLIENT_DOCUMENT", "Ya existe un cliente.", [
        {
          field: "document_number",
          code: "EXISTING_CLIENT",
          message: "Usa el cliente existente.",
          resource_id: "cl-1",
        },
      ]),
      opportunityFails: 1,
    });
    const user = userEvent.setup();
    renderWithProviders(<BrokerScreen />);

    await user.click(await screen.findByRole("button", { name: "Nuevo prospecto" }));
    const modal = await dialogNamed("Nuevo prospecto");
    await user.click(within(modal).getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Cédula de ciudadanía" }));
    await user.type(within(modal).getByLabelText("Número de documento"), "1032445908");
    await user.type(within(modal).getByLabelText("Nombres"), "Laura");
    await user.type(within(modal).getByLabelText("Apellidos"), "Gómez");
    await user.click(within(modal).getByRole("button", { name: "Registrar prospecto" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    // La oportunidad falló: el botón pasa a "Reintentar" y los datos del cliente se fijan.
    const retry = (await within(modal).findByText("Reintentar")).closest("button")!;
    expect(within(modal).getByLabelText("Nombres")).toBeDisabled();
    await user.click(retry);

    await waitFor(() => expect(calls.created).toHaveLength(2));
    expect(calls.clients).toHaveLength(1);
    expect(calls.created[1]).toMatchObject({ client_id: "cl-1", origin_type: "BROKER" });
    expect(await screen.findByText("Prospecto registrado")).toBeInTheDocument();
  });

  it("un documento que existe y no puede ver: el mensaje de la API va al campo", async () => {
    at("");
    const calls = mockApi({
      clientError: apiError("DUPLICATE_CLIENT_DOCUMENT", "Ya existe un cliente con ese documento."),
    });
    const user = userEvent.setup();
    renderWithProviders(<BrokerScreen />);

    await user.click(await screen.findByRole("button", { name: "Nuevo prospecto" }));
    const modal = await dialogNamed("Nuevo prospecto");
    await user.click(within(modal).getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Cédula de ciudadanía" }));
    await user.type(within(modal).getByLabelText("Número de documento"), "1032445908");
    await user.type(within(modal).getByLabelText("Nombres"), "Laura");
    await user.type(within(modal).getByLabelText("Apellidos"), "Gómez");
    await user.click(within(modal).getByRole("button", { name: "Registrar prospecto" }));

    expect(
      await within(modal).findByText("Ya existe un cliente con ese documento."),
    ).toBeInTheDocument();
    expect(calls.created).toHaveLength(0);
  });
});
