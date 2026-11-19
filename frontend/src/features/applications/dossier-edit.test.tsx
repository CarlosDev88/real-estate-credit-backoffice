import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  APP_ID,
  BOOTSTRAP,
  makeDetail,
  PROFILE,
  useWorkspaceApi,
} from "@/features/applications/workspace.fixtures";
import { WorkspaceScreen } from "@/features/applications/workspace-screen";
import { QueryProvider } from "@/providers/query-provider";
import { apiUrl, server } from "@/test/msw-server";

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

const item = (code: string, label: string, order = 1) => ({
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

/** El bootstrap del expediente con los catálogos de los formularios de edición. */
const EDIT_BOOTSTRAP = {
  ...BOOTSTRAP,
  catalogs: {
    ...BOOTSTRAP.catalogs,
    property_type: [item("APARTMENT", "Apartamento"), item("HOUSE", "Casa", 2)],
    property_condition: [item("NEW", "Nueva"), item("USED", "Usada", 2)],
    financing_mode: [
      item("BANK_CREDIT", "Crédito bancario"),
      item("OWN_FUNDS", "Recursos propios", 2),
      item("EXTERNAL_CREDIT", "Crédito externo aprobado", 3),
    ],
    currency_mode: [item("COP", "Pesos")],
    amortization_mode: [item("FIXED", "Cuota fija")],
    employment_profile: [item("EMPLOYEE", "Empleado"), item("INDEPENDENT", "Independiente", 2)],
    contract_type: [item("INDEFINITE", "Término indefinido")],
    funds_origin: [item("SALARY", "Salario")],
    income_source_type: [item("SALARY", "Salario"), item("RENTAL", "Arriendos", 2)],
    identity_document_type: [item("CC", "Cédula de ciudadanía")],
  },
};

interface Write {
  method: string;
  path: string;
  body: unknown;
  ifMatch: string | null;
}

/** Expediente con las rutas de escritura; cada escritura sube la versión (`ETag`). */
function useEditApi(options: { lock?: boolean } = {}) {
  const detail = makeDetail({
    purpose: { code: "PURCHASE_NEW", label: "Compra de vivienda nueva" },
  });
  const api = useWorkspaceApi({ detail });
  const writes: Write[] = [];
  // Versión de la solicitud: sube con cada escritura y el detalle la responde en `ETag`.
  const state = { version: 15 };
  const record = async (request: Request) => {
    const text = await request.text();
    writes.push({
      method: request.method,
      path: new URL(request.url).pathname.replace("/api/v1", ""),
      body: text ? JSON.parse(text) : null,
      ifMatch: request.headers.get("If-Match"),
    });
  };
  const answer = (body: unknown, status = 200) => {
    if (options.lock) {
      return HttpResponse.json(
        {
          code: "APPLICATION_NOT_EDITABLE",
          message: "La solicitud ya se radicó: no admite cambios.",
          details: [],
          request_id: "r-1",
        },
        { status: 409 },
      );
    }
    state.version += 1;
    return HttpResponse.json(body as object, {
      status,
      headers: { ETag: `"${state.version}"` },
    });
  };
  server.use(
    http.get(apiUrl(base), () =>
      HttpResponse.json(
        { ...detail, version: state.version },
        { headers: { ETag: `"${state.version}"` } },
      ),
    ),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(EDIT_BOOTSTRAP)),
    http.get(apiUrl("/metadata/catalogs/municipality"), () =>
      HttpResponse.json({
        catalog: "municipality",
        name: "Municipio",
        version: 1,
        items: [item("68276", "Floridablanca"), item("11001", "Bogotá D.C.", 2)],
      }),
    ),
    http.get(apiUrl("/projects"), () =>
      HttpResponse.json({
        items: [{ id: "pj-1", name: "Torres del Parque", partner: { id: "pa", name: "Andes" } }],
        page: 1,
        page_size: 100,
        total: 1,
        next: null,
        previous: null,
      }),
    ),
    http.get(apiUrl(`${base}/eligible-bank-products`), () =>
      HttpResponse.json({
        items: [
          {
            id: "bp-1",
            code: "HIP",
            name: "Crédito hipotecario",
            bank: { id: "b-1", code: "BC", name: "Bancolombia", short_name: "" },
            product_type_code: "MORTGAGE",
            product_type_label: "Hipotecario",
            min_amount_cop: 50_000_000,
            max_amount_cop: 900_000_000,
            min_term_months: 60,
            max_term_months: 360,
            evaluation: { eligible: true, blocking_count: 0, warning_count: 1 },
          },
          {
            id: "bp-2",
            code: "LEA",
            name: "Leasing habitacional",
            bank: { id: "b-2", code: "DV", name: "Davivienda", short_name: "" },
            product_type_code: "LEASING",
            product_type_label: "Leasing",
            min_amount_cop: null,
            max_amount_cop: null,
            min_term_months: null,
            max_term_months: null,
            evaluation: { eligible: false, blocking_count: 2, warning_count: 0 },
          },
        ],
        page: 1,
        page_size: 100,
        total: 2,
        next: null,
        previous: null,
      }),
    ),
    http.get(apiUrl("/clients"), () =>
      HttpResponse.json({
        items: [
          {
            id: "cl-9",
            full_name: "Ana Torres",
            document_type: { code: "CC", label: "Cédula" },
            document_number: "52111222",
          },
        ],
        page: 1,
        page_size: 20,
        total: 1,
        next: null,
        previous: null,
      }),
    ),
    http.get(apiUrl("/financial-profiles/fp-1/income-sources"), () =>
      HttpResponse.json({
        items: [
          {
            id: "is-1",
            financial_profile_id: "fp-1",
            source_type: { code: "SALARY", label: "Salario" },
            payer_name: "Constructora Andes",
            monthly_amount_cop: 7_800_000,
            start_date: "2020-02-01",
            is_primary: true,
            notes: "",
            created_at: "2026-11-01T10:00:00Z",
            updated_at: "2026-11-01T10:00:00Z",
          },
        ],
        page: 1,
        page_size: 100,
        total: 1,
        next: null,
        previous: null,
      }),
    ),
    http.put(apiUrl(`${base}/property`), async ({ request }) => {
      await record(request);
      return answer({});
    }),
    http.put(apiUrl(`${base}/financing`), async ({ request }) => {
      await record(request);
      return answer({});
    }),
    http.post(apiUrl(`${base}/participants`), async ({ request }) => {
      await record(request);
      const body = writes.at(-1)!.body as { client_id?: string; document_number?: string };
      if (!body.client_id && body.document_number) {
        return HttpResponse.json(
          {
            code: "DUPLICATE_CLIENT_DOCUMENT",
            message: "Ya existe un cliente con ese documento.",
            details: [
              {
                field: "document_number",
                code: "EXISTING_CLIENT",
                message: "Usa el cliente existente.",
                resource_id: "cl-9",
              },
            ],
            request_id: "r-2",
          },
          { status: 409 },
        );
      }
      return answer({}, 201);
    }),
    http.patch(apiUrl("/application-participants/:id"), async ({ request }) => {
      await record(request);
      return answer({});
    }),
    http.delete(apiUrl("/application-participants/:id"), async ({ request }) => {
      await record(request);
      return options.lock ? answer(null) : new HttpResponse(null, { status: 204 });
    }),
    http.put(apiUrl("/application-participants/:id/financial-profile"), async ({ request }) => {
      await record(request);
      return answer(PROFILE, 201);
    }),
    http.post(apiUrl("/financial-profiles/:id/income-sources"), async ({ request }) => {
      await record(request);
      return answer({}, 201);
    }),
    http.delete(apiUrl("/income-sources/:id"), async ({ request }) => {
      await record(request);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { api, writes };
}

function renderScreen() {
  const user = userEvent.setup();
  render(
    <App>
      <QueryProvider>
        <WorkspaceScreen id={APP_ID} />
      </QueryProvider>
    </App>,
  );
  return user;
}

async function ready() {
  await screen.findByRole("heading", { name: "SOL-000182" });
  await screen.findByText("Inmueble registrado.");
}

const card = (title: string) => screen.getByRole("heading", { name: title }).closest("section")!;

/** El panel lateral o modal con ese título (Ant Design no le da nombre al `dialog`). */
async function dialogNamed(title: string): Promise<HTMLElement> {
  // El último con ese título: el anterior puede seguir en el DOM mientras se cierra.
  const headings = await screen.findAllByText(title, {
    selector: ".ant-modal-title, .ant-drawer-title h2",
  });
  return headings.at(-1)!.closest<HTMLElement>('[role="dialog"]')!;
}

beforeEach(() => {
  window.history.replaceState(null, "", "/solicitudes/app-1");
});

describe("edición del expediente", { timeout: 30_000 }, () => {
  it("edita el inmueble con If-Match y la siguiente escritura usa la versión nueva", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();

    await user.click(within(card("Inmueble")).getByRole("button", { name: "Editar" }));
    const panel = await dialogNamed("Editar inmueble");
    const unit = within(panel).getByLabelText(/Unidad/);
    expect(unit).toHaveValue("Apartamento 1204");
    await user.clear(unit);
    await user.type(unit, "Apartamento 802");
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      method: "PUT",
      path: `${base}/property`,
      ifMatch: '"15"',
      body: {
        property_type_code: "APARTMENT",
        condition_code: "NEW",
        city_code: "68276",
        unit_reference: "Apartamento 802",
        estimated_value_cop: 520_000_000,
        is_owned_by_applicant: null,
        project_id: "pj-1",
      },
    });
    expect(await screen.findByText("Inmueble guardado")).toBeInTheDocument();

    // La respuesta trajo `ETag: "16"`: la financiación sale con esa versión.
    await user.click(within(card("Financiación")).getByRole("button", { name: "Editar" }));
    const financing = await dialogNamed("Editar financiación");
    await user.click(await within(financing).findByRole("radio", { name: /Crédito hipotecario/ }));
    await user.click(within(financing).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({
      path: `${base}/financing`,
      ifMatch: '"16"',
      body: {
        financing_mode_code: "BANK_CREDIT",
        bank_product_id: "bp-1",
        requested_amount_cop: 365_000_000,
        term_months: 240,
        severance_funds_cop: 0,
      },
    });
  });

  it("financiación: los productos traen su evaluación y sin crédito bancario no va producto", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();

    await user.click(within(card("Financiación")).getByRole("button", { name: "Editar" }));
    const panel = await dialogNamed("Editar financiación");
    expect(await within(panel).findByText("Cumple · 1 alerta")).toBeInTheDocument();
    expect(within(panel).getByText("2 reglas no cumplen")).toBeInTheDocument();
    // Crédito bancario sin producto: lo pide antes de enviar.
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));
    expect(await within(panel).findByText("Elige el producto.")).toBeInTheDocument();
    expect(writes).toHaveLength(0);

    await user.click(within(panel).getByRole("combobox", { name: "Modalidad" }));
    await user.click(await screen.findByRole("option", { name: "Recursos propios" }));
    expect(within(panel).queryByRole("radiogroup")).toBeNull();
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]!.body).toMatchObject({
      financing_mode_code: "OWN_FUNDS",
      bank_product_id: null,
      requested_amount_cop: null,
    });
    expect(writes[0]!.body).not.toHaveProperty("external_approved_amount_cop");
  });

  it("después de radicar: el mensaje de bloqueo de la API queda en el panel", async () => {
    useEditApi({ lock: true });
    const user = renderScreen();
    await ready();

    await user.click(within(card("Inmueble")).getByRole("button", { name: "Editar" }));
    const panel = await dialogNamed("Editar inmueble");
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));
    expect(await within(panel).findByText("La solicitud ya no admite cambios")).toBeInTheDocument();
    expect(
      within(panel).getByText("La solicitud ya se radicó: no admite cambios."),
    ).toBeInTheDocument();
  });

  it("agrega un participante existente; si el documento nuevo ya existe, ofrece ese cliente", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();

    await user.click(
      within(card("Participantes")).getByRole("button", { name: "Agregar participante" }),
    );
    const modal = await dialogNamed("Agregar participante");
    await user.click(within(modal).getByRole("combobox", { name: "Cliente" }));
    await user.click(await screen.findByRole("option", { name: /Ana Torres/ }));
    await user.click(within(modal).getByRole("button", { name: "Agregar" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      method: "POST",
      path: `${base}/participants`,
      body: {
        role_code: "CO_APPLICANT",
        client_id: "cl-9",
        contributes_income: true,
        income_share_cop: null,
      },
    });
    expect(await screen.findByText("Participante agregado")).toBeInTheDocument();
  });

  it("cliente nuevo con un documento que ya existe: la API trae su id y se ofrece", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();
    await user.click(
      within(card("Participantes")).getByRole("button", { name: "Agregar participante" }),
    );
    const modal = await dialogNamed("Agregar participante");
    await user.click(within(modal).getByRole("radio", { name: "Cliente nuevo" }));
    await user.click(within(modal).getByRole("combobox", { name: "Papel" }));
    await user.click(await screen.findByRole("option", { name: "Deudor solidario" }));
    await user.click(within(modal).getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Cédula de ciudadanía" }));
    await user.type(within(modal).getByLabelText("Número de documento"), "52111222");
    await user.type(within(modal).getByLabelText("Nombres"), "Ana");
    await user.type(within(modal).getByLabelText("Apellidos"), "Torres");
    await user.click(within(modal).getByRole("button", { name: "Agregar" }));
    expect(
      await within(modal).findByText("Ya existe un cliente con ese documento."),
    ).toBeInTheDocument();
    expect(writes[0]!.body).toMatchObject({
      role_code: "SOLIDARY_DEBTOR",
      document_type_code: "CC",
      document_number: "52111222",
    });

    await user.click(within(modal).getByRole("button", { name: "Agregar ese cliente" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]!.body).toMatchObject({ role_code: "SOLIDARY_DEBTOR", client_id: "cl-9" });
  });

  it("el panel del participante: papel con If-Match, perfil nuevo y quitar con confirmación", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();

    // El titular no cambia de papel ni se quita.
    await user.click(
      within(card("Participantes")).getByRole("button", { name: "Editar a Sofía Herrera" }),
    );
    let panel = await dialogNamed("Sofía Herrera");
    expect(within(panel).queryByRole("combobox", { name: "Papel" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Quitar participante" })).toBeNull();
    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));

    await user.click(
      within(card("Participantes")).getByRole("button", { name: "Editar a Daniel Mejía" }),
    );
    panel = await dialogNamed("Daniel Mejía");
    await user.click(within(panel).getByRole("combobox", { name: "Papel" }));
    await user.click(await screen.findByRole("option", { name: "Deudor solidario" }));
    await user.click(within(panel).getByRole("button", { name: "Guardar participación" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      method: "PATCH",
      path: "/application-participants/pa-2",
      ifMatch: '"15"',
      body: { role_code: "SOLIDARY_DEBTOR", contributes_income: true, income_share_cop: null },
    });

    // Sin perfil financiero: se crea (y los ingresos esperan al perfil).
    expect(within(panel).getByText("Primero guarda el perfil financiero.")).toBeInTheDocument();
    await user.click(within(panel).getByRole("combobox", { name: "Perfil laboral" }));
    await user.click(await screen.findByRole("option", { name: "Independiente" }));
    await user.click(within(panel).getByRole("button", { name: "Crear perfil" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({
      method: "PUT",
      path: "/application-participants/pa-2/financial-profile",
      ifMatch: '"16"',
      body: { employment_profile_code: "INDEPENDENT", employment_start_date: null },
    });

    await user.click(screen.getByRole("button", { name: "Quitar participante" }));
    const confirm = await dialogNamed("Quitar participante");
    await user.click(within(confirm).getByRole("button", { name: "Quitar participante" }));
    await waitFor(() => expect(writes).toHaveLength(3));
    expect(writes[2]).toMatchObject({ method: "DELETE", path: "/application-participants/pa-2" });
    expect(await screen.findByText("Participante quitado")).toBeInTheDocument();
  });

  it("fuentes de ingreso del titular: lista, agregar y quitar", async () => {
    const { writes } = useEditApi();
    const user = renderScreen();
    await ready();

    await user.click(
      within(card("Participantes")).getByRole("button", { name: "Editar a Sofía Herrera" }),
    );
    const panel = await dialogNamed("Sofía Herrera");
    const list = await within(panel).findByRole("list", { name: "Fuentes de ingreso" });
    expect(within(list).getByText("Constructora Andes · desde 1 feb 2020")).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Agregar ingreso" }));
    const modal = await dialogNamed("Agregar ingreso");
    await user.click(within(modal).getByRole("combobox", { name: "Tipo de ingreso" }));
    await user.click(await screen.findByRole("option", { name: "Arriendos" }));
    await user.click(within(modal).getByRole("button", { name: "Agregar" }));
    expect(await within(modal).findByText("Este campo es obligatorio.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Monto mensual"), "1200000");
    await user.click(within(modal).getByRole("button", { name: "Agregar" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      method: "POST",
      path: "/financial-profiles/fp-1/income-sources",
      body: { source_type_code: "RENTAL", monthly_amount_cop: 1_200_000, is_primary: false },
    });

    await user.click(within(list).getByRole("button", { name: "Quitar Salario" }));
    const confirm = await dialogNamed("Quitar ingreso");
    await user.click(within(confirm).getByRole("button", { name: "Quitar ingreso" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({ method: "DELETE", path: "/income-sources/is-1" });
  });
});
