import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  APP_ID,
  makeCompleteness,
  makeDetail,
  makeEvaluation,
  useWorkspaceApi,
} from "@/features/applications/workspace.fixtures";
import { WorkspaceScreen } from "@/features/applications/workspace-screen";
import { apiUrl, server } from "@/test/msw-server";
import { QueryProvider } from "@/providers/query-provider";

const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  return {
    listeners,
    push: vi.fn(),
    replace: vi.fn((href: string) => {
      window.history.replaceState(null, "", href);
      listeners.forEach((l) => l());
    }),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useRouter: () => nav,
    usePathname: () => `/solicitudes/app-1`,
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

const base = `/applications/${APP_ID}`;

/** Con el `QueryProvider` real: incluye el toast global de errores de escritura. */
function renderScreen(ui: ReactElement = <WorkspaceScreen id={APP_ID} />) {
  const user = userEvent.setup();
  render(
    <App>
      <QueryProvider>{ui}</QueryProvider>
    </App>,
  );
  return user;
}

async function ready() {
  await screen.findByRole("heading", { name: "SOL-000182" });
  await screen.findByText("Inmueble registrado.");
}

const card = (title: string) => screen.getByRole("heading", { name: title }).closest("article")!;

beforeEach(() => {
  window.history.replaceState(null, "", "/solicitudes/app-1");
  nav.push.mockClear();
  nav.replace.mockClear();
});

describe("expediente: encabezado", { timeout: 20_000 }, () => {
  it("muestra código, estado, subtítulo y datos clave", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();

    expect(screen.getByText("Documentos en revisión", { selector: "span" })).toHaveAttribute(
      "data-tone",
      "info",
    );
    const head = screen.getByRole("heading", { name: "SOL-000182" }).closest("section")!;
    expect(head).toHaveTextContent(
      "Sofía Herrera y Daniel Mejía · Vivienda nueva · Torres del Parque",
    );
    expect(screen.getByRole("link", { name: "Volver a solicitudes" })).toHaveAttribute(
      "href",
      "/solicitudes",
    );

    const facts = within(head).getByText("Monto solicitado").closest("dl")!;
    await waitFor(() => expect(facts).toHaveTextContent("70,2"));
    expect(facts).toHaveTextContent("365.000.000");
    expect(facts).toHaveTextContent("520.000.000");
    expect(facts).toHaveTextContent("del valor");
    expect(facts).toHaveTextContent("Banco de BogotáLeasing habitacional");
    expect(facts).toHaveTextContent("240meses");
    expect(facts).toHaveTextContent("Broker");
  });

  it("sin inmueble ni financiación muestra '—' en lo que no se puede calcular", async () => {
    useWorkspaceApi({ property: null, detail: makeDetail({ bank_product: null }) });
    server.use(
      http.get(apiUrl(`${base}/financing`), () =>
        HttpResponse.json(
          { code: "RESOURCE_NOT_FOUND", message: "x", details: [], request_id: "r" },
          { status: 404 },
        ),
      ),
    );
    renderScreen();
    await ready();
    await screen.findByText("Todavía no se registra el inmueble.");
    const facts = screen.getByText("Monto solicitado").closest("dl")!;
    expect(within(facts).getAllByText("—").length).toBeGreaterThanOrEqual(4);
  });

  it("un 404 dice que no existe o no hay acceso, con enlace al listado", async () => {
    server.use(
      http.get(apiUrl("/auth/me"), () => HttpResponse.json({})),
      http.get(apiUrl(base), () =>
        HttpResponse.json(
          { code: "RESOURCE_NOT_FOUND", message: "x", details: [], request_id: "r" },
          { status: 404 },
        ),
      ),
    );
    renderScreen();
    expect(
      await screen.findByText("No encontramos esta solicitud o no tienes acceso"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al listado de solicitudes" })).toHaveAttribute(
      "href",
      "/solicitudes",
    );
  });

  it("otro error se ve en línea con 'Reintentar'", async () => {
    let fail = true;
    useWorkspaceApi();
    server.use(
      http.get(apiUrl(base), () =>
        fail
          ? HttpResponse.json(
              { code: "PERMISSION_DENIED", message: "Sin permiso.", details: [], request_id: "r" },
              { status: 403 },
            )
          : HttpResponse.json(makeDetail()),
      ),
    );
    const user = renderScreen();
    expect(await screen.findByText("No pudimos cargar la solicitud")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { name: "SOL-000182" })).toBeInTheDocument();
  });
});

describe("expediente: acciones", { timeout: 20_000 }, () => {
  it("la primera transición es la principal y las demás van en 'Más acciones'", async () => {
    useWorkspaceApi();
    const user = renderScreen();
    await ready();

    expect(screen.getByRole("button", { name: "Marcar lista para radicar" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    const menu = await screen.findByRole("menu");
    const items = within(menu)
      .getAllByRole("menuitem")
      .map((i) => i.textContent);
    expect(items).toEqual([
      "Devolver a carga de documentos",
      "Cancelar solicitud",
      "Evaluar reglas del banco",
      "Reasignar asesor",
      "Registrar desistimiento",
    ]);
  });

  it("una transición sin motivo envía la versión del ETag y refresca el expediente", async () => {
    const api = useWorkspaceApi();
    let body: unknown = null;
    server.use(
      http.post(apiUrl(`${base}/status-transitions`), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          application_id: APP_ID,
          previous_status: "DOCUMENTS_REVIEW",
          status: "READY_TO_FILE",
          version: 16,
          transitioned_at: "2026-11-12T10:00:00Z",
        });
      }),
    );
    const user = renderScreen();
    await ready();
    const before = api.calls.detail;

    await user.click(screen.getByRole("button", { name: "Marcar lista para radicar" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Comentario/), " Todo revisado ");
    await user.click(within(dialog).getByRole("button", { name: "Marcar lista para radicar" }));

    await waitFor(() =>
      expect(body).toEqual({
        target_status: "READY_TO_FILE",
        comment: "Todo revisado",
        expected_version: 15,
      }),
    );
    expect(await screen.findByText("Cambio de estado registrado")).toBeInTheDocument();
    await waitFor(() => expect(api.calls.detail).toBeGreaterThan(before));
  });

  it("si la API exige el motivo, el error va al campo; con motivo se envía", async () => {
    useWorkspaceApi();
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post(apiUrl(`${base}/status-transitions`), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if (!body.reason_code) {
          return HttpResponse.json(
            {
              code: "VALIDATION_ERROR",
              message: "Revisa los datos.",
              details: [
                { field: "reason_code", code: "required", message: "El motivo es obligatorio." },
              ],
              request_id: "r",
            },
            { status: 400 },
          );
        }
        return HttpResponse.json({
          application_id: APP_ID,
          previous_status: "DOCUMENTS_REVIEW",
          status: "CANCELLED",
          version: 16,
          transitioned_at: "2026-11-12T10:00:00Z",
        });
      }),
    );
    const user = renderScreen();
    await ready();

    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cancelar solicitud" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar solicitud" }));
    expect(await within(dialog).findByText("El motivo es obligatorio.")).toBeInTheDocument();
    // Sin toast: el único detalle fue al campo.
    expect(screen.queryByText("Revisa los datos.")).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("No fue posible contactar al cliente"));
    // En jsdom el ícono de carga de Ant Design no termina de salir: el nombre lo incluye.
    await user.click(within(dialog).getByRole("button", { name: /Cancelar solicitud$/ }));
    await waitFor(() => expect(bodies.at(-1)?.reason_code).toBe("CLIENT_UNREACHABLE"));
    expect(bodies.at(-1)?.target_status).toBe("CANCELLED");
  });

  it("409 STALE_VERSION muestra el aviso global con 'Recargar'", async () => {
    const api = useWorkspaceApi();
    server.use(
      http.post(apiUrl(`${base}/status-transitions`), () =>
        HttpResponse.json(
          { code: "STALE_VERSION", message: "Versión vieja.", details: [], request_id: "r-9" },
          { status: 409 },
        ),
      ),
    );
    const user = renderScreen();
    await ready();
    await user.click(screen.getByRole("button", { name: "Marcar lista para radicar" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Marcar lista para radicar" }));

    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    const before = api.calls.detail;
    await user.click(screen.getByRole("button", { name: "Recargar" }));
    await waitFor(() => expect(api.calls.detail).toBeGreaterThan(before));
  });

  it("si no cumple para radicar: botón deshabilitado con la razón y la principal es revisar", async () => {
    useWorkspaceApi({
      completeness: makeCompleteness({
        ready_to_file: false,
        ready_to_file_problems: [
          { field: "documents", code: "DOCUMENT_PENDING", message: "Falta la cédula." },
          { field: "documents", code: "DOCUMENT_PENDING", message: "Falta el extracto." },
          { field: "documents", code: "DOCUMENT_EXPIRED", message: "Venció la certificación." },
          { field: "documents", code: "DOCUMENT_PENDING", message: "Falta la promesa." },
        ],
      }),
      slotsTotal: 3,
    });
    const user = renderScreen();
    await ready();

    const blocked = await screen.findByRole("button", { name: "Marcar lista para radicar" });
    expect(blocked).toBeDisabled();
    const reason = document.getElementById(blocked.getAttribute("aria-describedby")!)!;
    expect(reason).toHaveTextContent("Falta la cédula.");
    expect(reason).toHaveTextContent("Venció la certificación.");
    expect(reason).not.toHaveTextContent("Falta la promesa.");
    expect(reason).toHaveTextContent("Y 1 motivo más.");

    await user.click(screen.getByRole("button", { name: "Revisar 3 documentos" }));
    expect(window.location.search).toBe("?tab=documentos&slot=s-1");
  });

  it("enviar enlace al comprador: muestra la URL y la copia", async () => {
    useWorkspaceApi();
    let body: unknown = null;
    server.use(
      http.post(apiUrl(`${base}/buyer-access-links`), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            id: "l-2",
            application_id: APP_ID,
            client_id: "cl-1",
            status: "PENDING",
            delivery_channel: { code: "EMAIL", label: "Correo" },
            created_by: null,
            created_at: "2026-11-12T10:00:00Z",
            expires_at: "2026-11-15T10:00:00Z",
            consumed_at: null,
            revoked_at: null,
            session: null,
            url: "http://localhost:3000/acceso?token=abc",
          },
          { status: 201 },
        );
      }),
    );
    // userEvent.setup() instala su propio portapapeles: se espía después.
    const user = renderScreen();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    await ready();

    await user.click(screen.getByRole("button", { name: "Enviar enlace al comprador" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("El enlace anterior queda revocado")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Generar enlace" }));

    expect(
      await within(dialog).findByDisplayValue("http://localhost:3000/acceso?token=abc"),
    ).toBeInTheDocument();
    expect(body).toEqual({ delivery_channel: "EMAIL", expires_in_hours: 72 });
    await user.click(within(dialog).getByRole("button", { name: "Copiar" }));
    expect(writeText).toHaveBeenCalledWith("http://localhost:3000/acceso?token=abc");
    expect(await screen.findByText("Enlace copiado")).toBeInTheDocument();
  });

  it("sin permiso de usuarios no aparece 'Reasignar asesor' ni el enlace sin su permiso", async () => {
    useWorkspaceApi({
      permissions: ["applications.read", "applications.assign", "applications.transition"],
    });
    const user = renderScreen();
    await ready();
    expect(screen.queryByRole("button", { name: "Enviar enlace al comprador" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByText("Reasignar asesor")).toBeNull();
    expect(within(menu).queryByText("Registrar desistimiento")).toBeNull();
    expect(within(menu).queryByText("Evaluar reglas del banco")).toBeNull();
    // Sin permisos de enlaces ni consentimientos, no hay tarjeta de acceso.
    expect(screen.queryByRole("heading", { name: "Acceso del comprador" })).toBeNull();
  });

  it("reasigna el asesor; si quien reasigna pierde el acceso, vuelve al listado", async () => {
    useWorkspaceApi();
    let body: unknown = null;
    server.use(
      http.get(apiUrl("/users"), ({ request }) => {
        const q = new URL(request.url).searchParams;
        expect(q.get("role")).toBe("ADVISOR");
        return HttpResponse.json({
          items: [
            { id: "u-1", name: "Paula Rincón", email: "p@x.co" },
            { id: "u-2", name: "Carlos Méndez", email: "c@x.co" },
          ],
          page: 1,
          page_size: 100,
          total: 2,
          next: null,
          previous: null,
        });
      }),
      http.post(apiUrl(`${base}/assignments`), async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = renderScreen();
    await ready();
    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    await user.click(await screen.findByRole("menuitem", { name: "Reasignar asesor" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Reasignar" }));
    expect(await within(dialog).findByText("Elige el asesor.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox"));
    expect(screen.queryByTitle("Paula Rincón")).toBeNull();
    await user.click(await screen.findByTitle("Carlos Méndez"));
    await user.type(within(dialog).getByLabelText(/Motivo/), "Vacaciones");
    await user.click(within(dialog).getByRole("button", { name: "Reasignar" }));

    await waitFor(() => expect(body).toEqual({ advisor_id: "u-2", reason: "Vacaciones" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/solicitudes"));
  });

  it("registra el desistimiento con su motivo (obligatorio)", async () => {
    useWorkspaceApi();
    let body: unknown = null;
    server.use(
      http.post(apiUrl(`${base}/withdrawals`), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          application_id: APP_ID,
          previous_status: "DOCUMENTS_REVIEW",
          status: "WITHDRAWN",
          version: 16,
          transitioned_at: "2026-11-12T10:00:00Z",
        });
      }),
    );
    const user = renderScreen();
    await ready();
    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    await user.click(await screen.findByRole("menuitem", { name: "Registrar desistimiento" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Registrar desistimiento" }));
    expect(await within(dialog).findByText("Elige el motivo.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("Compró con otra entidad"));
    await user.click(within(dialog).getByRole("button", { name: "Registrar desistimiento" }));

    await waitFor(() =>
      expect(body).toEqual({ reason_code: "OTHER_FINANCING", comment: "", expected_version: 15 }),
    );
    expect(await screen.findByText("Desistimiento registrado")).toBeInTheDocument();
  });

  it("evalúa las reglas del banco y refresca la tarjeta", async () => {
    useWorkspaceApi();
    server.use(
      http.post(apiUrl(`${base}/bank-rule-evaluations`), () =>
        HttpResponse.json(
          makeEvaluation({
            eligible: false,
            warnings: [],
            blocking: [
              {
                rule_code: "LTV",
                outcome: "FAILED",
                message: "El monto supera el 70 % del valor.",
                field: null,
                unresolved_fields: [],
              },
            ],
          }),
          { status: 201 },
        ),
      ),
    );
    const user = renderScreen();
    await ready();
    await screen.findByText("Elegible");
    await user.click(screen.getByRole("button", { name: "Más acciones" }));
    await user.click(await screen.findByRole("menuitem", { name: "Evaluar reglas del banco" }));

    expect(await screen.findByText("Reglas del banco evaluadas")).toBeInTheDocument();
    const evaluation = card("Evaluación del banco");
    expect(within(evaluation).getByText("No elegible")).toBeInTheDocument();
    expect(within(evaluation).getByText("El monto supera el 70 % del valor.")).toBeInTheDocument();
  });

  it("una solicitud cerrada no ofrece enlace, evaluación ni reasignación", async () => {
    useWorkspaceApi({
      detail: makeDetail({
        status: "CANCELLED",
        status_label: "Cancelada",
        closed_at: "2026-11-11T10:00:00Z",
        available_actions: [],
      }),
    });
    renderScreen();
    await ready();
    expect(screen.queryByRole("button", { name: "Enviar enlace al comprador" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
  });
});

describe("expediente: resumen", { timeout: 20_000 }, () => {
  it("completitud con total, datos, documentos y lo que falta", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();
    const completeness = card("Completitud del expediente");
    expect(completeness).toHaveTextContent("81 % en total");
    expect(completeness).toHaveTextContent("10 de 16 · 62 %");
    expect(
      within(completeness).getByText("Registra el perfil financiero de Daniel Mejía."),
    ).toBeInTheDocument();
    expect(
      within(completeness).getByText("Faltan 6 de 16 documentos obligatorios."),
    ).toBeInTheDocument();
    expect(within(completeness).getAllByText("Pendiente:", { exact: false })).toHaveLength(2);
    // La pestaña Documentos lleva los pendientes.
    expect(screen.getByRole("tab", { name: "Documentos 6" })).toBeInTheDocument();
  });

  it("por revisar: lista los cargados y lleva al documento o a la pestaña", async () => {
    useWorkspaceApi();
    const user = renderScreen();
    await ready();
    const toReview = await waitFor(() => card("Por revisar"));
    expect(
      within(toReview).getByText("Certificado laboral", { selector: "div" }),
    ).toBeInTheDocument();
    expect(toReview).toHaveTextContent("Sofía Herrera · archivo-1.pdf");

    await user.click(within(toReview).getByRole("button", { name: "Revisar Certificado laboral" }));
    expect(window.location.search).toBe("?tab=documentos&slot=s-1");
  });

  it("por revisar vacío y 'Ver todos los documentos'", async () => {
    useWorkspaceApi({ slots: [], slotsTotal: 0 });
    const user = renderScreen();
    await ready();
    const toReview = await waitFor(() => card("Por revisar"));
    expect(
      within(toReview).getByText("No hay documentos cargados esperando revisión."),
    ).toBeInTheDocument();
    await user.click(within(toReview).getByRole("button", { name: "Ver todos los documentos" }));
    expect(window.location.search).toBe("?tab=documentos");
    expect(screen.getByRole("tabpanel", { name: "Documentos" })).toBeInTheDocument();
  });

  it("evaluación: elegible y vigente, con avisos", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();
    const evaluation = await waitFor(() => card("Evaluación del banco"));
    expect(within(evaluation).getByText("Elegible")).toHaveAttribute("data-tone", "success");
    expect(evaluation).toHaveTextContent("vigente para la versión actual");
    expect(evaluation).toHaveTextContent("Banco de Bogotá · Leasing habitacional");
    expect(
      within(evaluation).getByText("Ingreso del hogar cercano al mínimo del producto."),
    ).toBeInTheDocument();
  });

  it("evaluación vencida sin reglas, y sin evaluar", async () => {
    useWorkspaceApi({ evaluation: makeEvaluation({ is_current: false, warnings: [] }) });
    renderScreen();
    await ready();
    const evaluation = await waitFor(() => card("Evaluación del banco"));
    expect(evaluation).toHaveTextContent("vencida: la solicitud cambió después");
    expect(evaluation).toHaveTextContent("Cumple todas las reglas del producto.");
  });

  it("evaluación nunca hecha", async () => {
    useWorkspaceApi({ evaluation: null });
    renderScreen();
    await ready();
    expect(
      await screen.findByText("Todavía no se evalúan las reglas del banco para esta solicitud."),
    ).toBeInTheDocument();
  });

  it("participantes con perfil, sin perfil y los totales del hogar", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();
    const people = await waitFor(() => card("Participantes"));
    await waitFor(() => expect(people).toHaveTextContent("Empleada · Perfil confirmado"));
    expect(people).toHaveTextContent("Daniel MejíaSin perfil financiero");
    expect(people).toHaveTextContent("7.800.000");
    expect(within(people).getByText("Ingreso del hogar").nextSibling).toHaveTextContent(
      "7.800.000",
    );
    expect(within(people).getByText("Gastos del hogar").nextSibling).toHaveTextContent("2.350.000");
    expect(within(people).queryByRole("button", { name: "Agregar" })).toBeNull();
  });

  it("inmueble con proyecto, unidad, ciudad, condición y valor", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();
    const property = await waitFor(() => card("Inmueble"));
    expect(property).toHaveTextContent("Torres del Parque");
    expect(property).toHaveTextContent("Apartamento 1204");
    expect(property).toHaveTextContent("Floridablanca");
    expect(property).toHaveTextContent("Nueva · Apartamento");
    expect(property).toHaveTextContent("520.000.000");
  });

  it("acceso del comprador: enlace, sesión, consentimientos vigentes y actividad", async () => {
    useWorkspaceApi();
    renderScreen();
    await ready();
    const access = card("Acceso del comprador");
    await waitFor(() => expect(access).toHaveTextContent("Tratamiento de datos"));
    expect(access).toHaveTextContent("Usado");
    expect(access).toHaveTextContent("Activa hasta 12 nov 2026");
    // El de "Autorización de consulta" se retiró después de aceptarlo.
    expect(access).not.toHaveTextContent("Autorización de consulta");
  });

  it("acceso del comprador sin enlace ni consentimientos ni actividad", async () => {
    useWorkspaceApi({ detail: makeDetail({ last_buyer_activity_at: null }) });
    server.use(
      http.get(apiUrl(`${base}/buyer-access-links`), () =>
        HttpResponse.json({
          items: [],
          page: 1,
          page_size: 1,
          total: 0,
          next: null,
          previous: null,
        }),
      ),
      http.get(apiUrl(`${base}/consents`), () =>
        HttpResponse.json({
          items: [],
          page: 1,
          page_size: 1,
          total: 0,
          next: null,
          previous: null,
        }),
      ),
    );
    renderScreen();
    await ready();
    const access = card("Acceso del comprador");
    await waitFor(() => expect(access).toHaveTextContent("Todavía no se envía"));
    expect(access).toHaveTextContent("Ninguno aceptado");
    expect(access).toHaveTextContent("El comprador aún no entra");
  });

  it("últimos cambios de estado con etiquetas del catálogo y 'Ver historial'", async () => {
    useWorkspaceApi();
    const user = renderScreen();
    await ready();
    const recent = await waitFor(() => card("Últimos cambios de estado"));
    expect(recent).toHaveTextContent("Pasó de Esperando documentos a Documentos en revisión");
    expect(recent).toHaveTextContent("portal del comprador");
    expect(recent).toHaveTextContent("Se creó en Borrador");
    await user.click(within(recent).getByRole("button", { name: "Ver historial" }));
    expect(window.location.search).toBe("?tab=historial");
  });

  it("una sección que falla se ve en línea y se reintenta", async () => {
    useWorkspaceApi();
    let fail = true;
    server.use(
      http.get(apiUrl(`${base}/completeness`), () =>
        fail
          ? HttpResponse.json(
              { code: "X", message: "x", details: [], request_id: "r" },
              { status: 400 },
            )
          : HttpResponse.json(makeCompleteness()),
      ),
    );
    const user = renderScreen();
    await screen.findByRole("heading", { name: "SOL-000182" });
    const failed = await screen.findByText("No pudimos cargar esta sección.");
    fail = false;
    await user.click(
      within(failed.closest("article")!).getByRole("button", { name: "Reintentar" }),
    );
    expect(await screen.findByText("Inmueble registrado.")).toBeInTheDocument();
  });
});

describe("expediente: pestañas e historial", { timeout: 20_000 }, () => {
  it("la pestaña sale de la URL y vuelve a la URL", async () => {
    window.history.replaceState(null, "", "/solicitudes/app-1?tab=historial");
    useWorkspaceApi();
    const user = renderScreen();
    await screen.findByRole("heading", { name: "SOL-000182" });
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");

    const panel = await screen.findByRole("tabpanel", { name: "Historial" });
    await within(panel).findByText("Datos completos por teléfono.");
    expect(panel).toHaveTextContent("Pasó de Borrador a Esperando documentos");
    expect(panel).toHaveTextContent("Paula Rincón · versión 5");
    expect(panel).toHaveTextContent("Motivo: Otro");
    expect(panel).toHaveTextContent("portal del comprador · versión 14");

    await user.click(screen.getByRole("tab", { name: "Resumen" }));
    expect(window.location.search).toBe("");
    await user.click(screen.getByRole("tab", { name: /Documentos/ }));
    expect(window.location.search).toBe("?tab=documentos");
  });

  it("historial paginado y con error", async () => {
    window.history.replaceState(null, "", "/solicitudes/app-1?tab=historial");
    useWorkspaceApi();
    const pages: string[] = [];
    server.use(
      http.get(apiUrl(`${base}/status-history`), ({ request }) => {
        const p = new URL(request.url).searchParams.get("page") ?? "1";
        pages.push(p);
        if (p === "3") {
          return HttpResponse.json(
            { code: "X", message: "Falló.", details: [], request_id: "r" },
            { status: 400 },
          );
        }
        const entry = { ...makeHistoryEntry(), id: `h-${p}`, comment: `página ${p}` };
        return HttpResponse.json({
          items: [entry],
          page: Number(p),
          page_size: 20,
          total: 45,
          next: null,
          previous: null,
        });
      }),
    );
    const user = renderScreen();
    const panel = await screen.findByRole("tabpanel", { name: "Historial" });
    await within(panel).findByText("página 1");
    await user.click(within(panel).getByRole("button", { name: "Page 2" }));
    expect(await within(panel).findByText("página 2")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Page 3" }));
    expect(await within(panel).findByText("No pudimos cargar el historial")).toBeInTheDocument();
  });
});

function makeHistoryEntry() {
  return {
    id: "h",
    from_status: "DRAFT",
    to_status: "WAITING_DOCUMENTS",
    transition_code: null,
    reason: null,
    comment: "",
    actor: null,
    buyer_session_id: null,
    application_version: 2,
    created_at: "2026-11-02T10:00:00Z",
  };
}
