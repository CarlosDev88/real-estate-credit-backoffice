import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClientDetailScreen } from "@/features/clients/client-detail-screen";
import {
  action,
  apiError,
  CLIENTS_BOOTSTRAP,
  CLIENTS_ME,
  makeAddress,
  makeClientApplication,
  makeClientDetail,
  makeOpportunity,
  MUNICIPALITIES,
  page,
} from "@/features/clients/clients.fixtures";
import { toAddressBody } from "@/features/clients/summary-tab";
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
    usePathname: () => "/clientes/cl-1",
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

type User = ReturnType<typeof userEvent.setup>;

const ALL_PERMISSIONS = [
  ...CLIENTS_ME.permissions,
  "opportunities.read",
  "opportunities.create",
  "opportunities.assign",
  "applications.create",
  "users.read",
];
const ME = { ...CLIENTS_ME, permissions: ALL_PERMISSIONS };

const ADVISORS = page([
  { id: "u-1", name: "Asesora", email: "asesora@example.com" },
  { id: "u-2", name: "Asesor Dos", email: "dos@example.com" },
]);

interface Recorded {
  addresses: unknown[];
  opportunities: unknown[];
  assignments: unknown[];
  applications: unknown[];
}

function useApi(
  opts: {
    me?: typeof ME;
    addresses?: ReturnType<typeof makeAddress>[];
    opportunities?: ReturnType<typeof makeOpportunity>[];
    applications?: ReturnType<typeof makeClientApplication>[];
  } = {},
): Recorded {
  const recorded: Recorded = {
    addresses: [],
    opportunities: [],
    assignments: [],
    applications: [],
  };
  const opportunities = opts.opportunities ?? [makeOpportunity(1)];
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(opts.me ?? ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(CLIENTS_BOOTSTRAP)),
    http.get(apiUrl("/metadata/catalogs/municipality"), () => HttpResponse.json(MUNICIPALITIES)),
    http.get(apiUrl("/clients/cl-1"), () => HttpResponse.json(makeClientDetail())),
    http.get(apiUrl("/clients/cl-1/addresses"), () =>
      HttpResponse.json(page(opts.addresses ?? [makeAddress(1)])),
    ),
    http.post(apiUrl("/clients/cl-1/addresses"), async ({ request }) => {
      recorded.addresses.push(await request.json());
      return HttpResponse.json(makeAddress(9), { status: 201 });
    }),
    http.get(apiUrl("/clients/cl-1/opportunities"), () => HttpResponse.json(page(opportunities))),
    http.get(apiUrl("/opportunities/:id"), ({ params }) => {
      const found = opportunities.find((o) => o.id === params.id);
      return found
        ? HttpResponse.json(found)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.post(apiUrl("/opportunities"), async ({ request }) => {
      recorded.opportunities.push(await request.json());
      return HttpResponse.json(makeOpportunity(7, { id: "op-new" }), { status: 201 });
    }),
    http.post(apiUrl("/opportunities/:id/assignments"), async ({ request, params }) => {
      recorded.assignments.push(await request.json());
      const base = opportunities.find((o) => o.id === params.id) ?? makeOpportunity(1);
      return HttpResponse.json({ ...base, assigned_advisor: { id: "u-2", name: "Asesor Dos" } });
    }),
    http.get(apiUrl("/users"), () => HttpResponse.json(ADVISORS)),
    http.get(apiUrl("/projects"), () =>
      HttpResponse.json(
        page([
          { id: "pr-1", name: "Torres del Parque", partner: { id: "pa-1", name: "Andes" } },
          { id: "pr-2", name: "Mirador", partner: { id: "pa-1", name: "Andes" } },
        ]),
      ),
    ),
    http.get(apiUrl("/clients/cl-1/applications"), () =>
      HttpResponse.json(page(opts.applications ?? [makeClientApplication(1)])),
    ),
    http.post(apiUrl("/applications"), async ({ request }) => {
      const body = (await request.json()) as { opportunity_id: string };
      recorded.applications.push(body);
      // Como la API: la oportunidad queda convertida y ya no ofrece acciones.
      const index = opportunities.findIndex((o) => o.id === body.opportunity_id);
      if (index >= 0) {
        opportunities[index] = {
          ...opportunities[index]!,
          status: "CONVERTED",
          status_label: "Convertida",
          available_actions: [],
        };
      }
      return HttpResponse.json({ id: "app-new", code: "SOL-000099" }, { status: 201 });
    }),
  );
  return recorded;
}

function go(search: string) {
  window.history.replaceState(null, "", `/clientes/cl-1${search}`);
}

async function renderDetail(search = "") {
  go(search);
  const user = userEvent.setup();
  renderWithProviders(<ClientDetailScreen id="cl-1" />);
  await screen.findByRole("heading", { name: "Laura Gómez Vélez", level: 1 });
  return user;
}

async function pick(user: User, label: string | RegExp, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click((await screen.findAllByTitle(option)).at(-1)!);
}

/**
 * Modal abierto sobre el panel lateral. En las pruebas, Ant Design pone el mismo
 * `aria-labelledby` a todos los diálogos: se busca el último con ese título.
 */
async function modalTitled(title: string): Promise<HTMLElement> {
  return waitFor(() => {
    const dialog = screen.getAllByRole("dialog").at(-1)!;
    expect(within(dialog).getByText(title)).toBeInTheDocument();
    return dialog;
  });
}

beforeEach(() => {
  nav.push.mockClear();
  nav.replace.mockClear();
});

describe("cuerpo de una dirección", () => {
  it("la primera no pide ser principal; las demás, si se marca", () => {
    const values = {
      address_type_code: "WORK",
      city_code: "11001",
      line1: "Calle 1",
      line2: "",
      postal_code: "",
      is_primary: true,
    };
    expect(toAddressBody(values, true).is_primary).toBe(false);
    expect(toAddressBody(values, false).is_primary).toBe(true);
  });
});

describe("detalle del cliente", { timeout: 20_000 }, () => {
  it("muestra el encabezado y las pestañas, y la pestaña va a la URL", async () => {
    useApi();
    const user = await renderDetail();

    expect(screen.getByText("Origen: Directo")).toBeInTheDocument();
    const tabs = await screen.findAllByRole("tab");
    await waitFor(() =>
      expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
        "Resumen",
        "Oportunidades",
        "Solicitudes",
      ]),
    );
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Resumen" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Solicitudes" }));
    await waitFor(() => expect(window.location.search).toBe("?tab=solicitudes"));
    expect(await screen.findByRole("link", { name: "SOL-000001" })).toHaveAttribute(
      "href",
      "/solicitudes/app-1",
    );
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });

  it("sin permisos de oportunidades ni solicitudes solo queda el resumen", async () => {
    useApi({ me: { ...ME, permissions: ["clients.read"] } });
    await renderDetail("?tab=oportunidades");
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Resumen"]);
    expect(screen.getByRole("tabpanel", { name: "Resumen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
  });

  it("muestra las direcciones, con la principal marcada", async () => {
    useApi({ addresses: [makeAddress(1), makeAddress(2, { line2: "Apto 301" })] });
    await renderDetail();
    expect(await screen.findByText("Calle 1 # 10-20")).toBeInTheDocument();
    expect(screen.getByText("Principal")).toBeInTheDocument();
    expect(screen.getAllByText(/Residencia · Bogotá D.C./)).toHaveLength(2);
    expect(screen.getByText("Residencia · Bogotá D.C. · Apto 301")).toBeInTheDocument();
  });

  it("agrega la primera dirección (queda como principal)", async () => {
    const recorded = useApi({ addresses: [] });
    const user = await renderDetail();
    expect(await screen.findByText("Todavía no tiene direcciones.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agregar dirección" }));
    const dialog = await screen.findByRole("dialog", { name: "Agregar dirección" });
    expect(within(dialog).getByText(/queda como principal/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Agregar dirección" }));
    expect(await within(dialog).findByText("Elige el tipo de dirección.")).toBeInTheDocument();
    expect(within(dialog).getByText("Elige el municipio.")).toBeInTheDocument();
    expect(within(dialog).getByText("Escribe la dirección.")).toBeInTheDocument();

    await pick(user, "Tipo de dirección", "Trabajo");
    await pick(user, "Municipio", "Medellín");
    await user.type(within(dialog).getByRole("textbox", { name: "Dirección" }), "Cra 43A # 1-50");
    await user.click(within(dialog).getByRole("button", { name: "Agregar dirección" }));

    await waitFor(() =>
      expect(recorded.addresses).toEqual([
        {
          address_type_code: "WORK",
          city_code: "05001",
          line1: "Cra 43A # 1-50",
          line2: "",
          postal_code: "",
          is_primary: false,
        },
      ]),
    );
    expect(await screen.findByText("Dirección agregada")).toBeInTheDocument();
  });

  it("lista las oportunidades con su estado, proyecto, origen y asesor", async () => {
    useApi({
      opportunities: [
        makeOpportunity(1),
        makeOpportunity(2, {
          project: null,
          assigned_advisor: null,
          status: "LOST",
          status_label: "Perdida",
        }),
      ],
    });
    await renderDetail("?tab=oportunidades");
    const list = await screen.findByRole("list", { name: "Oportunidades" });
    const rows = within(list).getAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("Asignada")).toBeInTheDocument();
    expect(
      within(rows[0]!).getByText("Torres del Parque · Constructora Andes"),
    ).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Directo")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Asesora")).toBeInTheDocument();
    // El texto del estado es el `status_label` de la API.
    expect(within(rows[1]!).getByText("Perdida")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Sin proyecto")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Sin asesor")).toBeInTheDocument();
  });

  it("sin oportunidades muestra el estado vacío", async () => {
    useApi({ opportunities: [] });
    await renderDetail("?tab=oportunidades");
    expect(await screen.findByText("Este cliente no tiene oportunidades")).toBeInTheDocument();
  });

  it("crea una oportunidad con el origen del cliente y abre su panel", async () => {
    const recorded = useApi();
    const user = await renderDetail("?tab=oportunidades");
    await user.click(await screen.findByRole("button", { name: "Nueva oportunidad" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva oportunidad" });
    expect(within(dialog).getByText("Directo")).toBeInTheDocument();
    await pick(user, /Proyecto/, "Mirador · Andes");
    await user.click(within(dialog).getByRole("button", { name: "Crear oportunidad" }));

    await waitFor(() =>
      expect(recorded.opportunities).toEqual([
        { client_id: "cl-1", origin_type: "DIRECT", project_id: "pr-2" },
      ]),
    );
    await waitFor(() =>
      expect(window.location.search).toBe("?tab=oportunidades&oportunidad=op-new"),
    );
  });

  it("una oportunidad duplicada marca el proyecto", async () => {
    useApi();
    server.use(
      http.post(apiUrl("/opportunities"), () =>
        HttpResponse.json(
          apiError(
            "DUPLICATE_OPPORTUNITY",
            "El cliente ya tiene una oportunidad abierta para ese proyecto.",
          ),
          { status: 409 },
        ),
      ),
    );
    const user = await renderDetail("?tab=oportunidades");
    await user.click(await screen.findByRole("button", { name: "Nueva oportunidad" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva oportunidad" });
    await user.click(within(dialog).getByRole("button", { name: "Crear oportunidad" }));
    expect(
      await within(dialog).findByText(
        "El cliente ya tiene una oportunidad abierta para ese proyecto.",
      ),
    ).toBeInTheDocument();
  });

  it("abre el panel desde la URL con el detalle y las asignaciones, y lo cierra", async () => {
    useApi();
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    expect(await within(panel).findByText("Zona norte")).toBeInTheDocument();
    expect(
      within(panel).getByRole("heading", { name: "Torres del Parque · Constructora Andes" }),
    ).toBeInTheDocument();
    expect(within(panel).getByText(/por Admin/)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));
    await waitFor(() => expect(window.location.search).toBe("?tab=oportunidades"));
  });

  it("un clic en la fila abre el panel", async () => {
    useApi();
    const user = await renderDetail("?tab=oportunidades");
    const list = await screen.findByRole("list", { name: "Oportunidades" });
    await user.click(within(list).getByRole("button"));
    await waitFor(() => expect(window.location.search).toBe("?tab=oportunidades&oportunidad=op-1"));
  });

  it("una oportunidad que no existe lo dice en el panel", async () => {
    useApi();
    await renderDetail("?tab=oportunidades&oportunidad=op-x");
    expect(
      await screen.findByText("No encontramos esta oportunidad o no tienes acceso"),
    ).toBeInTheDocument();
  });

  it("cambia el asesor con permiso", async () => {
    const recorded = useApi();
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(await within(panel).findByRole("button", { name: "Cambiar asesor" }));
    const dialog = await modalTitled("Cambiar asesor");
    await pick(user, "Asesor", "Asesor Dos");
    await user.click(within(dialog).getByRole("button", { name: "Asignar" }));
    await waitFor(() => expect(recorded.assignments).toEqual([{ advisor_id: "u-2", reason: "" }]));
    expect(await screen.findByText("Asesor asignado")).toBeInTheDocument();
  });

  it("sin `users.read` no ofrece elegir asesor; si ya es suya, tampoco 'Asignarme'", async () => {
    useApi({ me: { ...ME, permissions: ALL_PERMISSIONS.filter((p) => p !== "users.read") } });
    await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await within(panel).findByRole("button", { name: "Crear solicitud de crédito" });
    expect(within(panel).queryByRole("button", { name: /asesor/ })).not.toBeInTheDocument();
    // La oportunidad ya es de este usuario (u-1).
    expect(within(panel).queryByRole("button", { name: "Asignarme" })).not.toBeInTheDocument();
  });

  it("sin `users.read`, el asesor puede asignarse una oportunidad sin asesor", async () => {
    const recorded = useApi({
      me: { ...ME, permissions: ALL_PERMISSIONS.filter((p) => p !== "users.read") },
      opportunities: [makeOpportunity(1, { assigned_advisor: null, status: "NEW" })],
    });
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(await within(panel).findByRole("button", { name: "Asignarme" }));
    await waitFor(() => expect(recorded.assignments).toEqual([{ advisor_id: "u-1", reason: "" }]));
    expect(await screen.findByText("Te asignaste la oportunidad")).toBeInTheDocument();
  });

  it("muestra las transiciones de `available_actions` y marca como contactada sin confirmar", async () => {
    useApi();
    const sent: unknown[] = [];
    server.use(
      http.post(apiUrl("/opportunities/:id/transitions"), async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(
          makeOpportunity(1, { status: "CONTACTED", status_label: "Contactada" }),
        );
      }),
    );
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    // La conversión va por "Crear solicitud"; el resto, un botón por acción con su texto.
    await within(panel).findByRole("button", { name: "Crear solicitud de crédito" });
    expect(within(panel).queryByRole("button", { name: "Convertir en solicitud" })).toBeNull();
    expect(within(panel).getByRole("button", { name: "Marcar como perdida" })).toHaveClass(
      "ant-btn-dangerous",
    );
    await user.click(within(panel).getByRole("button", { name: "Marcar como contactada" }));
    await waitFor(() => expect(sent).toEqual([{ target_status: "CONTACTED", comment: "" }]));
    // El panel queda con la respuesta (`status_label` de la API).
    expect(await within(panel).findByText("Contactada")).toBeInTheDocument();
  });

  it("marcar como perdida pide confirmación y el motivo del catálogo", async () => {
    useApi();
    const sent: unknown[] = [];
    server.use(
      http.post(apiUrl("/opportunities/:id/transitions"), async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(
          makeOpportunity(1, { status: "LOST", status_label: "Perdida", available_actions: [] }),
        );
      }),
    );
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(await within(panel).findByRole("button", { name: "Marcar como perdida" }));
    const dialog = await modalTitled("Perdida");
    await user.click(within(dialog).getByRole("button", { name: "Marcar como perdida" }));
    expect(await within(dialog).findByText("Elige el motivo.")).toBeInTheDocument();
    expect(sent).toHaveLength(0);

    await pick(user, "Motivo", "Eligió otro banco");
    await user.type(within(dialog).getByLabelText(/Comentario/), "Tasa más baja");
    await user.click(within(dialog).getByRole("button", { name: "Marcar como perdida" }));
    await waitFor(() =>
      expect(sent).toEqual([
        { target_status: "LOST", reason_code: "OTHER_BANK", comment: "Tasa más baja" },
      ]),
    );
  });

  it("sin la conversión en `available_actions` no ofrece crear la solicitud", async () => {
    useApi({
      opportunities: [
        makeOpportunity(1, {
          status: "NEW",
          assigned_advisor: null,
          available_actions: [
            action("CANCEL_NEW", "Cancelar", "destructive", "CANCELLED", "Cancelada"),
            action("ASSIGN", "Asignar asesor", "secondary", "ASSIGNED", "Asignada"),
          ],
        }),
      ],
    });
    await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await within(panel).findByRole("button", { name: "Cancelar" });
    expect(within(panel).queryByRole("button", { name: "Crear solicitud de crédito" })).toBeNull();
    // `ASSIGN` va por "Asignar asesor" (`/assignments`), no como transición.
    expect(within(panel).getAllByRole("button", { name: "Asignar asesor" })).toHaveLength(1);
  });

  it("sin asesor ni `users.read`, el error de asesor de la API va al aviso", async () => {
    useApi({
      me: { ...ME, permissions: ALL_PERMISSIONS.filter((p) => p !== "users.read") },
      opportunities: [makeOpportunity(1, { assigned_advisor: null })],
    });
    server.use(
      http.post(apiUrl("/applications"), () =>
        HttpResponse.json(
          apiError("VALIDATION_ERROR", "Revisa los datos.", [
            {
              field: "assigned_advisor_id",
              code: "invalid",
              message: "La oportunidad no tiene asesor: indica uno.",
            },
          ]),
          { status: 400 },
        ),
      ),
    );
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(
      await within(panel).findByRole("button", { name: "Crear solicitud de crédito" }),
    );
    const dialog = await modalTitled("Crear solicitud de crédito");
    expect(within(dialog).getByText(/la solicitud necesita uno/)).toBeInTheDocument();
    await pick(user, "Finalidad del crédito", "Vivienda nueva");
    await user.click(within(dialog).getByRole("button", { name: "Crear solicitud" }));
    expect(
      await screen.findByText("La oportunidad no tiene asesor: indica uno."),
    ).toBeInTheDocument();
  });

  it("crea la solicitud desde la oportunidad y va al expediente", async () => {
    const recorded = useApi();
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(
      await within(panel).findByRole("button", { name: "Crear solicitud de crédito" }),
    );
    const dialog = await modalTitled("Crear solicitud de crédito");

    await user.click(within(dialog).getByRole("button", { name: "Crear solicitud" }));
    expect(await within(dialog).findByText("Elige la finalidad del crédito.")).toBeInTheDocument();

    await pick(user, "Finalidad del crédito", "Vivienda usada");
    await user.click(within(dialog).getByRole("button", { name: "Crear solicitud" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/solicitudes/app-new"));
    expect(recorded.applications).toEqual([{ opportunity_id: "op-1", purpose_code: "USED_HOME" }]);
  });

  it("si ya hay una solicitud en curso, lo dice con enlace a ella", async () => {
    useApi();
    server.use(
      http.post(apiUrl("/applications"), () =>
        HttpResponse.json(
          apiError("APPLICATION_ALREADY_OPEN", "La oportunidad ya tiene una solicitud en curso.", [
            {
              field: "opportunity_id",
              code: "OPEN_APPLICATION",
              message: "Continúa la solicitud en curso.",
              resource_id: "app-7",
            },
          ]),
          { status: 409 },
        ),
      ),
    );
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(
      await within(panel).findByRole("button", { name: "Crear solicitud de crédito" }),
    );
    const dialog = await modalTitled("Crear solicitud de crédito");
    await pick(user, "Finalidad del crédito", "Vivienda nueva");
    await user.click(within(dialog).getByRole("button", { name: "Crear solicitud" }));

    expect(
      await within(dialog).findByText("La oportunidad ya tiene una solicitud en curso."),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "Ir a la solicitud en curso" }),
    ).toHaveAttribute("href", "/solicitudes/app-7");
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("sin asesor en la oportunidad pide uno al crear la solicitud", async () => {
    const recorded = useApi({ opportunities: [makeOpportunity(1, { assigned_advisor: null })] });
    const user = await renderDetail("?tab=oportunidades&oportunidad=op-1");
    const panel = await screen.findByRole("dialog");
    await user.click(
      await within(panel).findByRole("button", { name: "Crear solicitud de crédito" }),
    );
    const dialog = await modalTitled("Crear solicitud de crédito");
    await pick(user, "Finalidad del crédito", "Vivienda nueva");
    await pick(user, "Asesor de la solicitud", "Asesor Dos");
    await user.click(within(dialog).getByRole("button", { name: "Crear solicitud" }));
    await waitFor(() =>
      expect(recorded.applications).toEqual([
        { opportunity_id: "op-1", purpose_code: "NEW_HOME", assigned_advisor_id: "u-2" },
      ]),
    );
  });

  it("sin solicitudes muestra el estado vacío", async () => {
    useApi({ applications: [] });
    await renderDetail("?tab=solicitudes");
    expect(await screen.findByText("Este cliente no tiene solicitudes")).toBeInTheDocument();
  });

  it("un error de las oportunidades se ve con 'Reintentar'", async () => {
    useApi();
    let fail = true;
    server.use(
      http.get(apiUrl("/clients/cl-1/opportunities"), () =>
        fail
          ? HttpResponse.json(apiError("SERVER", "Falló."), { status: 409 })
          : HttpResponse.json(page([makeOpportunity(1)])),
      ),
    );
    const user = await renderDetail("?tab=oportunidades");
    expect(await screen.findByText("No pudimos cargar las oportunidades")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("list", { name: "Oportunidades" })).toBeInTheDocument();
  });
});
