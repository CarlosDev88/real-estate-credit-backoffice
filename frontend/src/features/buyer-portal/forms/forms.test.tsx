import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse, type JsonBodyType } from "msw";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FinancingScreen } from "@/features/buyer-portal/forms/financing-screen";
import { toFormPath } from "@/features/buyer-portal/forms/form-kit";
import { IncomeScreen } from "@/features/buyer-portal/forms/income-screen";
import { ProfileScreen } from "@/features/buyer-portal/forms/profile-screen";
import { PropertyScreen } from "@/features/buyer-portal/forms/property-screen";
import { PortalGuard } from "@/features/buyer-portal/portal-guard";
import {
  APP_ID,
  CO_ID,
  PRIMARY_ID,
  apiError,
  detailFixture,
  sessionFixture,
} from "@/features/buyer-portal/portal.fixtures";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";
import { ThemeProvider } from "@/providers/theme-provider";

// Con `--coverage` y la suite completa, el primer render pasa del segundo por defecto.
configure({ asyncUtilTimeout: 5_000 });

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), pathname: "/portal/datos" }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => router.pathname,
}));

// ---------- datos de prueba ----------

const item = (code: string, label: string, parent_code: string | null = null) => ({
  id: `id-${code}`,
  code,
  label,
  description: "",
  order: 1,
  active: true,
  parent_id: null,
  parent_code,
  metadata: {},
});

const CATALOGS: Record<string, ReturnType<typeof item>[]> = {
  address_type: [item("HOME", "Residencia"), item("WORK", "Trabajo")],
  department: [item("11", "Bogotá D.C."), item("05", "Antioquia")],
  municipality: [item("11001", "Bogotá", "11"), item("05001", "Medellín", "05")],
  employment_profile: [item("EMPLOYEE", "Empleado"), item("INDEPENDENT", "Independiente")],
  contract_type: [item("INDEFINITE", "Indefinido")],
  funds_origin: [item("SALARY", "Salario")],
  income_source_type: [item("SALARY", "Salario"), item("RENT", "Arriendos")],
  property_type: [item("APT", "Apartamento")],
  property_condition: [item("NEW", "Nuevo"), item("USED", "Usado")],
  financing_mode: [item("BANK", "Crédito bancario")],
  currency_mode: [item("COP", "Pesos")],
  amortization_mode: [item("FIXED", "Cuota fija")],
};

const PROFILE = {
  first_names: "Sofía",
  last_names: "Herrera",
  full_name: "Sofía Herrera",
  document_type: { code: "CC", label: "Cédula" },
  document_number: "****5678",
  birth_date: "1990-05-01",
  email: "sofia@example.com",
  phone: "+573001234567",
  addresses: [
    {
      id: "addr-1",
      address_type: { code: "HOME", label: "Residencia" },
      city: { code: "11001", label: "Bogotá" },
      line1: "Calle 1 # 2-3",
      line2: "",
      postal_code: "",
      is_primary: true,
    },
  ],
  updated_at: "2026-11-10T10:00:00Z",
};

const FIN_PROFILE = {
  id: "fp-1",
  participant_id: PRIMARY_ID,
  employment_profile: { code: "EMPLOYEE", label: "Empleado" },
  contract_type: null,
  employer_name: "Acme",
  job_title: "Analista",
  employment_start_date: null,
  monthly_income_cop: 5_000_000,
  income_sources_total_cop: 5_000_000,
  monthly_expenses_cop: 1_000_000,
  assets_cop: 0,
  liabilities_cop: 0,
  funds_origin: null,
  data_confirmed_at: null as string | null,
  updated_at: "2026-11-10T10:00:00Z",
};

const SOURCE = {
  id: "src-1",
  financial_profile_id: "fp-1",
  source_type: { code: "SALARY", label: "Salario" },
  payer_name: "Acme",
  monthly_amount_cop: 5_000_000,
  start_date: "2024-01-01",
  is_primary: true,
  updated_at: "2026-11-10T10:00:00Z",
};

const PRODUCTS = [
  {
    id: "bp-1",
    name: "Hipotecario",
    bank: { id: "b-1", name: "Banco de Bogotá" },
    min_amount_cop: 50_000_000,
    max_amount_cop: 800_000_000,
    min_term_months: 60,
    max_term_months: 360,
    eligible: true,
  },
  {
    id: "bp-2",
    name: "Leasing",
    bank: { id: "b-2", name: "Bancolombia" },
    min_amount_cop: null,
    max_amount_cop: null,
    min_term_months: null,
    max_term_months: 240,
    eligible: false,
  },
];

const page = (items: unknown[]) =>
  HttpResponse.json({
    items,
    page: 1,
    page_size: 100,
    total: items.length,
    next: null,
    previous: null,
  } as JsonBodyType);

interface Call {
  method: string;
  path: string;
  ifMatch: string | null;
  body: unknown;
}

/** API del portal con versión 9 en cada `ETag`; registra las escrituras. */
function useFormsApi({ readOnly = false } = {}) {
  const calls: Call[] = [];
  const state = { profile: structuredClone(PROFILE), finProfile: { ...FIN_PROFILE } };
  const base = sessionFixture();
  const session = readOnly
    ? { ...base, application: { ...base.application, is_editable: false } }
    : base;
  const etag = { headers: { ETag: '"9"' } };
  const record = async (request: Request, path: string) => {
    const text = await request.text();
    calls.push({
      method: request.method,
      path,
      ifMatch: request.headers.get("If-Match"),
      body: text ? JSON.parse(text) : null,
    });
  };
  const catalogRequests: string[] = [];

  server.use(
    http.get(apiUrl("/buyer/session"), () => HttpResponse.json(session)),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/document-slots`), () => page([])),
    http.get(apiUrl("/buyer/metadata/catalogs/:code"), ({ params, request }) => {
      const parent = new URL(request.url).searchParams.get("parent_code");
      catalogRequests.push(`${String(params.code)}${parent ? `?${parent}` : ""}`);
      const items = (CATALOGS[String(params.code)] ?? []).filter(
        (i) => !parent || i.parent_code === parent,
      );
      return HttpResponse.json({ catalog: params.code, name: "", version: 1, items });
    }),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/profile`), () =>
      HttpResponse.json(state.profile, etag),
    ),
    http.patch(apiUrl(`/buyer/applications/${APP_ID}/profile`), async ({ request }) => {
      await record(request, "profile");
      return HttpResponse.json(state.profile, { headers: { ETag: '"10"' } });
    }),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/participants`), () =>
      page([
        {
          id: PRIMARY_ID,
          role: "PRIMARY",
          role_label: "Titular",
          full_name: "Sofía Herrera",
          contributes_income: true,
          financial_profile_id: "fp-1",
          data_confirmed_at: null,
        },
        {
          id: CO_ID,
          role: "CO_APPLICANT",
          role_label: "Segundo solicitante",
          full_name: "Daniel Mejía",
          contributes_income: true,
          financial_profile_id: null,
          data_confirmed_at: null,
        },
        {
          id: "p-3",
          role: "SOLIDARY_DEBTOR",
          role_label: "Deudor solidario",
          full_name: "Sin Ingresos",
          contributes_income: false,
          financial_profile_id: null,
          data_confirmed_at: null,
        },
      ]),
    ),
    http.get(apiUrl("/buyer/participants/:id/financial-profile"), ({ params }) =>
      params.id === PRIMARY_ID
        ? HttpResponse.json(state.finProfile, etag)
        : apiError(404, "RESOURCE_NOT_FOUND"),
    ),
    http.put(apiUrl("/buyer/participants/:id/financial-profile"), async ({ request, params }) => {
      await record(request, `financial-profile/${String(params.id)}`);
      return HttpResponse.json(state.finProfile, { headers: { ETag: '"10"' } });
    }),
    http.post(
      apiUrl("/buyer/participants/:id/financial-profile/confirmation"),
      async ({ request }) => {
        await record(request, "confirmation");
        state.finProfile = { ...state.finProfile, data_confirmed_at: "2026-11-17T15:00:00Z" };
        return HttpResponse.json(state.finProfile, { headers: { ETag: '"10"' } });
      },
    ),
    http.get(apiUrl("/buyer/financial-profiles/fp-1/income-sources"), () =>
      HttpResponse.json(
        { items: [SOURCE], page: 1, page_size: 100, total: 1, next: null, previous: null },
        etag,
      ),
    ),
    http.post(apiUrl("/buyer/financial-profiles/fp-1/income-sources"), async ({ request }) => {
      await record(request, "income-sources");
      return HttpResponse.json(SOURCE, { status: 201, headers: { ETag: '"10"' } });
    }),
    http.patch(apiUrl("/buyer/income-sources/:id"), async ({ request }) => {
      await record(request, "income-source");
      return HttpResponse.json(SOURCE, { headers: { ETag: '"10"' } });
    }),
    http.delete(apiUrl("/buyer/income-sources/:id"), async ({ request }) => {
      await record(request, "income-source-delete");
      return new HttpResponse(null, { status: 204, headers: { ETag: '"10"' } });
    }),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/property`), () =>
      HttpResponse.json(detailFixture().property, etag),
    ),
    http.put(apiUrl(`/buyer/applications/${APP_ID}/property`), async ({ request }) => {
      await record(request, "property");
      return HttpResponse.json(detailFixture().property, { headers: { ETag: '"10"' } });
    }),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/financing`), () =>
      HttpResponse.json(detailFixture().financing, etag),
    ),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/eligible-bank-products`), () =>
      HttpResponse.json(
        { items: PRODUCTS, page: 1, page_size: 100, total: 2, next: null, previous: null },
        etag,
      ),
    ),
    http.put(apiUrl(`/buyer/applications/${APP_ID}/financing`), async ({ request }) => {
      await record(request, "financing");
      return HttpResponse.json(detailFixture().financing, { headers: { ETag: '"10"' } });
    }),
  );
  return { calls, catalogRequests, state };
}

function renderScreen(ui: ReactElement, path: string) {
  router.pathname = path;
  return renderWithProviders(
    <ThemeProvider initialMode="light" hasCookie>
      <PortalGuard>{ui}</PortalGuard>
    </ThemeProvider>,
  );
}

const stale = () => apiError(409, "STALE_VERSION", "La solicitud cambió.");
const fieldError = (field: string, message: string) =>
  HttpResponse.json(
    {
      code: "VALIDATION_ERROR",
      message: "Datos inválidos.",
      details: [{ field, code: "invalid", message }],
      request_id: "r",
    },
    { status: 400 },
  );

async function choose(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByTitle(option));
}

beforeEach(() => {
  router.replace.mockReset();
  router.push.mockReset();
});

// ---------- datos personales ----------

describe("/portal/datos", { timeout: 20_000 }, () => {
  it("carga, muestra lo que no se edita y guarda con If-Match y la lista completa", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<ProfileScreen />, "/portal/datos");

    expect(await screen.findByLabelText("Correo")).toHaveValue("sofia@example.com");
    expect(screen.getByText("Cédula ****5678")).toBeInTheDocument();
    expect(screen.queryByLabelText("Nombres")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute(
      "href",
      "/portal",
    );
    // La ciudad existente muestra su departamento (buscado en el catálogo de municipios).
    await waitFor(() => expect(screen.getByText("Bogotá D.C.")).toBeInTheDocument());

    await user.clear(screen.getByLabelText("Teléfono"));
    await user.type(screen.getByLabelText("Teléfono"), "3109998888");
    await user.click(screen.getByRole("button", { name: "Agregar dirección" }));
    const second = screen.getByRole("group", { name: "Dirección 2" });
    await user.click(within(second).getByRole("combobox", { name: "Tipo" }));
    await user.click(await screen.findByTitle("Trabajo"));
    await user.click(within(second).getByRole("combobox", { name: "Departamento" }));
    await user.click((await screen.findAllByTitle("Antioquia")).at(-1)!);
    await user.click(within(second).getByRole("combobox", { name: "Ciudad" }));
    await user.click(await screen.findByTitle("Medellín"));
    await user.type(within(second).getByLabelText("Dirección"), "Carrera 7 # 8-9");
    // Solo una principal.
    await user.click(within(second).getByRole("checkbox", { name: "Dirección principal" }));
    expect(
      within(screen.getByRole("group", { name: "Dirección 1" })).getByRole("checkbox"),
    ).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect(api.catalogRequests).toContain("municipality?05");
    expect(api.calls[0]).toEqual({
      method: "PATCH",
      path: "profile",
      ifMatch: '"9"',
      body: {
        email: "sofia@example.com",
        phone: "3109998888",
        birth_date: "1990-05-01",
        addresses: [
          {
            id: "addr-1",
            address_type_code: "HOME",
            city_code: "11001",
            line1: "Calle 1 # 2-3",
            line2: "",
            postal_code: "",
            is_primary: false,
          },
          {
            address_type_code: "WORK",
            city_code: "05001",
            line1: "Carrera 7 # 8-9",
            line2: "",
            postal_code: "",
            is_primary: true,
          },
        ],
      },
    });
    expect(await screen.findByText("Guardamos tus datos")).toBeInTheDocument();
  });

  it("quita una dirección y valida el formato en el cliente", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<ProfileScreen />, "/portal/datos");

    await user.clear(await screen.findByLabelText("Correo"));
    await user.type(screen.getByLabelText("Correo"), "no-es-correo");
    await user.click(screen.getByRole("button", { name: "Quitar la dirección 1" }));
    expect(screen.getByText("Todavía no tienes direcciones.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));

    expect(await screen.findByText("Escribe un correo válido.")).toBeInTheDocument();
    expect(screen.getByLabelText("Correo")).toHaveAttribute("aria-invalid", "true");
    expect(api.calls).toHaveLength(0);
  });

  it("un error de la API con campo va al campo (también en una dirección)", async () => {
    useFormsApi();
    server.use(
      http.patch(apiUrl(`/buyer/applications/${APP_ID}/profile`), () =>
        fieldError("addresses[0].line1", "Dirección no válida."),
      ),
    );
    const user = userEvent.setup();
    renderScreen(<ProfileScreen />, "/portal/datos");
    await screen.findByLabelText("Correo");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    const error = await screen.findByText("Dirección no válida.");
    expect(
      within(screen.getByRole("group", { name: "Dirección 1" })).getByLabelText("Dirección"),
    ).toHaveAccessibleDescription("Dirección no válida.");
    expect(error).toBeInTheDocument();
  });

  it("409 STALE_VERSION: aviso con Recargar", async () => {
    useFormsApi();
    server.use(http.patch(apiUrl(`/buyer/applications/${APP_ID}/profile`), stale));
    const user = userEvent.setup();
    renderScreen(<ProfileScreen />, "/portal/datos");
    await screen.findByLabelText("Correo");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("solo lectura: campos deshabilitados y sin Guardar", async () => {
    useFormsApi({ readOnly: true });
    renderScreen(<ProfileScreen />, "/portal/datos");
    expect(await screen.findByLabelText("Correo")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Guardar$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Agregar dirección" })).not.toBeInTheDocument();
    expect(screen.getByText("Tu solicitud ya no admite cambios")).toBeInTheDocument();
  });

  it("un 409 de solo lectura vuelve a pedir la sesión y bloquea el formulario", async () => {
    let sessionCalls = 0;
    useFormsApi();
    const base = sessionFixture();
    server.use(
      http.get(apiUrl("/buyer/session"), () => {
        sessionCalls += 1;
        return HttpResponse.json(
          sessionCalls > 1
            ? { ...base, application: { ...base.application, is_editable: false } }
            : base,
        );
      }),
      http.patch(apiUrl(`/buyer/applications/${APP_ID}/profile`), () =>
        apiError(409, "APPLICATION_NOT_EDITABLE", "La solicitud ya no admite cambios."),
      ),
    );
    const user = userEvent.setup();
    renderScreen(<ProfileScreen />, "/portal/datos");
    await screen.findByLabelText("Correo");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("La solicitud ya no admite cambios.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Correo")).toBeDisabled());
  });
});

// ---------- ingresos ----------

describe("/portal/ingresos", { timeout: 20_000 }, () => {
  it("una sección por participante con ingresos; guarda el perfil con If-Match", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<IncomeScreen />, "/portal/ingresos");

    const primary = await screen.findByRole("region", { name: /Sofía Herrera/ });
    const co = screen.getByRole("region", { name: /Daniel Mejía/ });
    expect(primary).toHaveTextContent("Sofía Herrera · Titular");
    expect(
      await within(co).findByText(
        "Guarda el perfil financiero para agregar tus fuentes de ingreso.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Sin Ingresos")).not.toBeInTheDocument();

    const income = await within(primary).findByLabelText("Ingreso mensual");
    expect(income).toHaveValue("5.000.000");
    await user.clear(income);
    await user.type(income, "6500000");
    await user.click(within(primary).getByRole("button", { name: /Guardar perfil financiero$/ }));

    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect(api.calls[0]).toMatchObject({
      method: "PUT",
      path: `financial-profile/${PRIMARY_ID}`,
      ifMatch: '"9"',
      body: {
        employment_profile_code: "EMPLOYEE",
        contract_type_code: null,
        employer_name: "Acme",
        monthly_income_cop: 6_500_000,
      },
    });
  });

  it("el perfil nuevo exige el perfil laboral y un error de la API va al campo", async () => {
    const api = useFormsApi();
    server.use(
      http.put(apiUrl(`/buyer/participants/${CO_ID}/financial-profile`), () =>
        fieldError("monthly_income_cop", "Ingreso fuera de rango."),
      ),
    );
    const user = userEvent.setup();
    renderScreen(<IncomeScreen />, "/portal/ingresos");
    const co = await screen.findByRole("region", { name: /Daniel Mejía/ });
    const save = await within(co).findByRole("button", { name: /Guardar perfil financiero$/ });
    await user.click(save);
    expect(await within(co).findByText("Este campo es obligatorio.")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);

    await user.click(within(co).getByRole("combobox", { name: "Perfil laboral" }));
    await user.click((await screen.findAllByTitle("Independiente")).at(-1)!);
    await user.click(save);
    expect(await within(co).findByText("Ingreso fuera de rango.")).toBeInTheDocument();
  });

  it("fuentes de ingreso: agregar, editar y eliminar con confirmación", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<IncomeScreen />, "/portal/ingresos");
    const primary = await screen.findByRole("region", { name: /Sofía Herrera/ });
    expect(await within(primary).findByText("Salario")).toBeInTheDocument();
    expect(primary).toHaveTextContent("Acme · Desde 1 ene 2024");
    expect(primary).toHaveTextContent("Principal");

    // Agregar (sin If-Match).
    await user.click(within(primary).getByRole("button", { name: "Agregar ingreso" }));
    let dialog = await screen.findByRole("dialog", { name: "Agregar ingreso" });
    await user.click(within(dialog).getByRole("button", { name: /Guardar$/ }));
    expect(await within(dialog).findAllByText("Este campo es obligatorio.")).toHaveLength(2);
    await user.click(within(dialog).getByRole("combobox", { name: "Tipo de ingreso" }));
    await user.click(await screen.findByTitle("Arriendos"));
    await user.type(within(dialog).getByLabelText("Monto mensual"), "800000");
    await user.click(within(dialog).getByRole("button", { name: /Guardar$/ }));
    await waitFor(() =>
      expect(api.calls.at(-1)).toEqual({
        method: "POST",
        path: "income-sources",
        ifMatch: null,
        body: {
          source_type_code: "RENT",
          payer_name: "",
          monthly_amount_cop: 800_000,
          start_date: null,
          is_primary: false,
        },
      }),
    );

    // Editar (con If-Match).
    await user.click(within(primary).getByRole("button", { name: "Editar Salario" }));
    dialog = await screen.findByRole("dialog", { name: "Editar ingreso" });
    expect(within(dialog).getByLabelText(/^Pagador/)).toHaveValue("Acme");
    await user.clear(within(dialog).getByLabelText(/^Pagador/));
    await user.type(within(dialog).getByLabelText(/^Pagador/), "Acme S.A.S.");
    await user.click(within(dialog).getByRole("button", { name: /Guardar$/ }));
    await waitFor(() =>
      expect(api.calls.at(-1)).toMatchObject({
        method: "PATCH",
        path: "income-source",
        ifMatch: '"10"',
        body: { payer_name: "Acme S.A.S." },
      }),
    );

    // Eliminar, después de confirmar.
    const before = api.calls.length;
    await user.click(within(primary).getByRole("button", { name: "Eliminar Salario" }));
    await screen.findAllByText("¿Eliminar este ingreso?");
    const confirm = screen.getAllByRole("dialog").at(-1)!;
    expect(confirm).toHaveTextContent("¿Eliminar este ingreso?");
    expect(api.calls).toHaveLength(before);
    await user.click(within(confirm).getByRole("button", { name: "Eliminar" }));
    await waitFor(() =>
      expect(api.calls.at(-1)).toMatchObject({ method: "DELETE", path: "income-source-delete" }),
    );
  });

  it("confirmar mis datos con If-Match y después 'Confirmados el'", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<IncomeScreen />, "/portal/ingresos");
    const primary = await screen.findByRole("region", { name: /Sofía Herrera/ });
    await user.click(await within(primary).findByRole("button", { name: "Confirmar mis datos" }));
    await waitFor(() =>
      expect(api.calls.at(-1)).toMatchObject({ path: "confirmation", ifMatch: '"9"' }),
    );
    expect(await within(primary).findByText(/Confirmados el 17 nov 2026/)).toBeInTheDocument();
    expect(
      within(primary).queryByRole("button", { name: "Confirmar mis datos" }),
    ).not.toBeInTheDocument();
  });

  it("409 STALE_VERSION al guardar el perfil", async () => {
    useFormsApi();
    server.use(http.put(apiUrl("/buyer/participants/:id/financial-profile"), stale));
    const user = userEvent.setup();
    renderScreen(<IncomeScreen />, "/portal/ingresos");
    const primary = await screen.findByRole("region", { name: /Sofía Herrera/ });
    await user.click(
      await within(primary).findByRole("button", { name: /Guardar perfil financiero$/ }),
    );
    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
  });

  it("solo lectura: sin guardar, agregar, editar ni confirmar", async () => {
    useFormsApi({ readOnly: true });
    renderScreen(<IncomeScreen />, "/portal/ingresos");
    const primary = await screen.findByRole("region", { name: /Sofía Herrera/ });
    expect(await within(primary).findByLabelText("Ingreso mensual")).toBeDisabled();
    expect(
      within(primary).queryByRole("button", { name: /Guardar|Agregar|Editar|Confirmar/ }),
    ).toBeNull();
  });
});

// ---------- inmueble ----------

describe("/portal/inmueble", { timeout: 20_000 }, () => {
  it("proyecto en solo lectura; guarda con If-Match y '¿Ya es tuyo?' en tres valores", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<PropertyScreen />, "/portal/inmueble");
    expect(await screen.findByText("Torres del Parque")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Unidad/)).toHaveValue("Apto 1204");
    expect(screen.getByRole("radio", { name: "No" })).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "Sin respuesta" }));
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect(api.calls[0]).toEqual({
      method: "PUT",
      path: "property",
      ifMatch: '"9"',
      body: {
        property_type_code: "APT",
        condition_code: "NEW",
        city_code: "11001",
        address: "Calle 1 # 2-3",
        unit_reference: "Apto 1204",
        estimated_value_cop: 500_000_000,
        is_owned_by_applicant: null,
      },
    });
  });

  it("departamento → municipio: cambiar el departamento limpia y filtra el municipio", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<PropertyScreen />, "/portal/inmueble");
    await screen.findByText("Torres del Parque");
    await waitFor(() => expect(screen.getByText("Bogotá D.C.")).toBeInTheDocument());
    expect(screen.getByRole("combobox", { name: "Ciudad" })).toBeEnabled();

    await choose(user, "Departamento", "Antioquia");
    expect(screen.queryByTitle("Bogotá")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Ciudad" }));
    expect(await screen.findByTitle("Medellín")).toBeInTheDocument();
    expect(api.catalogRequests).toContain("municipality?05");

    // Sin municipio, el campo es obligatorio en el cliente.
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("Este campo es obligatorio.")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it("mientras cargan los municipios, la ciudad se ve con su nombre y no con el código", async () => {
    useFormsApi();
    server.use(
      http.get(apiUrl("/buyer/metadata/catalogs/municipality"), async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    );
    renderScreen(<PropertyScreen />, "/portal/inmueble");
    const city = await screen.findByRole("combobox", { name: "Ciudad" });
    expect(city).toBeEnabled();
    expect(city.closest(".ant-select")).toHaveTextContent("Bogotá");
    expect(screen.queryByText("11001")).not.toBeInTheDocument();
  });

  it("sin inmueble registrado: formulario vacío; error de la API en el campo", async () => {
    useFormsApi();
    server.use(
      http.get(apiUrl(`/buyer/applications/${APP_ID}/property`), () =>
        apiError(404, "RESOURCE_NOT_FOUND"),
      ),
      http.get(apiUrl(`/buyer/applications/${APP_ID}`), () =>
        HttpResponse.json(detailFixture({ property: null }), { headers: { ETag: '"9"' } }),
      ),
      http.put(apiUrl(`/buyer/applications/${APP_ID}/property`), ({ request }) => {
        // Sin inmueble no llegó ETag: la versión sale del detalle.
        expect(request.headers.get("If-Match")).toBe('"9"');
        return fieldError("estimated_value_cop", "El valor es muy bajo para la finalidad.");
      }),
    );
    const user = userEvent.setup();
    renderScreen(<PropertyScreen />, "/portal/inmueble");
    expect(await screen.findByLabelText(/^Unidad/)).toHaveValue("");
    expect(screen.queryByText("Proyecto")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Sin respuesta" })).toBeChecked();

    await choose(user, "Tipo de inmueble", "Apartamento");
    await choose(user, "Condición", "Usado");
    await choose(user, "Departamento", "Bogotá D.C.");
    await choose(user, "Ciudad", "Bogotá");
    await user.type(screen.getByLabelText("Valor estimado"), "1000");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("El valor es muy bajo para la finalidad.")).toBeInTheDocument();
  });

  it("409 STALE_VERSION y solo lectura", async () => {
    useFormsApi();
    server.use(http.put(apiUrl(`/buyer/applications/${APP_ID}/property`), stale));
    const user = userEvent.setup();
    const view = renderScreen(<PropertyScreen />, "/portal/inmueble");
    await screen.findByText("Torres del Parque");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    view.unmount();

    useFormsApi({ readOnly: true });
    renderScreen(<PropertyScreen />, "/portal/inmueble");
    expect(await screen.findByLabelText(/^Unidad/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Guardar$/ })).not.toBeInTheDocument();
  });
});

// ---------- financiación ----------

describe("/portal/financiacion", { timeout: 20_000 }, () => {
  it("productos como tarjetas; uno no elegible no se puede elegir", async () => {
    useFormsApi();
    renderScreen(<FinancingScreen />, "/portal/financiacion");
    const available = await screen.findByRole("radio", { name: /Hipotecario/ });
    const blocked = screen.getByRole("radio", { name: /Leasing/ });
    expect(available).toBeChecked();
    expect(blocked).toBeDisabled();
    expect(available.closest("label")).toHaveTextContent(
      "Banco de BogotáHipotecarioDe $ 50.000.000 a $ 800.000.000 · De 60 meses a 360 mesesDisponible",
    );
    expect(blocked.closest("label")).toHaveTextContent("Hasta 240 mesesNo disponible para tu caso");
  });

  it("guarda con If-Match; las cesantías piden su monto solo si se marcan", async () => {
    const api = useFormsApi();
    const user = userEvent.setup();
    renderScreen(<FinancingScreen />, "/portal/financiacion");
    expect(await screen.findByLabelText("Plazo en meses")).toHaveValue("240");
    expect(screen.queryByLabelText("Monto de cesantías")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "¿Usarás tus cesantías?" }));
    await user.type(screen.getByLabelText("Monto de cesantías"), "12000000");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect(api.calls[0]).toEqual({
      method: "PUT",
      path: "financing",
      ifMatch: '"9"',
      body: {
        financing_mode_code: "BANK",
        bank_product_id: "bp-1",
        requested_amount_cop: 365_000_000,
        term_months: 240,
        currency_mode_code: null,
        amortization_mode_code: null,
        own_resources_cop: 135_000_000,
        uses_severance_funds: true,
        severance_funds_cop: 12_000_000,
        external_approved_amount_cop: null,
      },
    });
  });

  it("error de la API en el campo, 409 STALE_VERSION y solo lectura", async () => {
    useFormsApi();
    let attempt = 0;
    server.use(
      http.put(apiUrl(`/buyer/applications/${APP_ID}/financing`), () => {
        attempt += 1;
        return attempt === 1
          ? fieldError("term_months", "El plazo supera el del producto.")
          : stale();
      }),
    );
    const user = userEvent.setup();
    const view = renderScreen(<FinancingScreen />, "/portal/financiacion");
    await screen.findByLabelText("Plazo en meses");
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("El plazo supera el del producto.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Guardar$/ }));
    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    view.unmount();

    useFormsApi({ readOnly: true });
    renderScreen(<FinancingScreen />, "/portal/financiacion");
    expect(await screen.findByLabelText("Plazo en meses")).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Hipotecario/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Guardar$/ })).not.toBeInTheDocument();
  });
});

describe("utilidades de formularios", () => {
  it("toFormPath convierte los índices de la API", () => {
    expect(toFormPath("addresses[2].city_code")).toBe("addresses.2.city_code");
    expect(toFormPath("email")).toBe("email");
  });
});
