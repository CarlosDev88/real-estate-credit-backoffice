import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  firstName,
  formatTerm,
  inSentence,
  whatsappUrl,
  workloadText,
} from "@/features/buyer-portal/home-format";
import { PortalHome } from "@/features/buyer-portal/home-screen";
import { PortalGuard } from "@/features/buyer-portal/portal-guard";
import {
  APP_ID,
  CO_ID,
  PRIMARY_ID,
  apiError,
  detailFixture,
  sessionFixture,
  slotFixture,
  slotsPage,
} from "@/features/buyer-portal/portal.fixtures";
import type { BuyerApplicationDetail, BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";
import { ThemeProvider } from "@/providers/theme-provider";

// Con `--coverage` y la suite completa, el primer render del portal pasa del segundo por
// defecto de Testing Library: las esperas de este archivo llegan a 5 s y cada prueba a 20 s.
configure({ asyncUtilTimeout: 5_000 });

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), pathname: "/portal" }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => router.pathname,
}));

const SLOTS: BuyerDocumentSlot[] = [
  slotFixture({
    id: "s-rej",
    label: "Desprendible de nómina 2 de 3",
    status: "REJECTED",
    public_status: "TO_FIX",
    public_status_label: "Corrígelo",
    current_file: { id: "f-1" } as BuyerDocumentSlot["current_file"],
    rejection: {
      reason: { code: "BLURRY", label: "Ilegible" },
      buyer_comment: "La foto está borrosa.",
      rejected_at: "2026-11-16T10:00:00Z",
    },
  }),
  slotFixture({ id: "s-2", label: "Extracto bancario 2 de 3" }),
  slotFixture({
    id: "s-3",
    label: "Extracto bancario 1 de 3",
    participant: {
      id: CO_ID,
      role: "CO_APPLICANT",
      role_label: "Segundo solicitante",
      full_name: "Daniel Mejía",
    },
  }),
  slotFixture({ id: "s-4", label: "Certificado laboral" }),
  slotFixture({
    id: "s-rev",
    label: "Cédula",
    status: "UPLOADED",
    public_status: "IN_REVIEW",
    public_status_label: "En revisión",
    needs_action: false,
  }),
];

interface Setup {
  detail?: BuyerApplicationDetail;
  slots?: BuyerDocumentSlot[];
  session?: ReturnType<typeof sessionFixture>;
}

function useHomeApi({ detail = detailFixture(), slots = SLOTS, session }: Setup = {}) {
  const state = { detail, session: session ?? sessionFixture(), withdrawals: [] as unknown[] };
  server.use(
    http.get(apiUrl("/buyer/session"), () => HttpResponse.json(state.session)),
    http.get(apiUrl(`/buyer/applications/${APP_ID}`), () =>
      HttpResponse.json(state.detail, { headers: { ETag: '"9"' } }),
    ),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/document-slots`), () => slotsPage(slots)),
    http.get(apiUrl("/buyer/participants/:id/financial-profile"), ({ params }) =>
      params.id === PRIMARY_ID
        ? HttpResponse.json({ monthly_income_cop: 5_000_000 })
        : params.id === CO_ID
          ? HttpResponse.json({ monthly_income_cop: 2_800_000 })
          : apiError(404, "RESOURCE_NOT_FOUND"),
    ),
    http.get(apiUrl("/buyer/metadata/catalogs/application_withdrawal_reason"), () =>
      HttpResponse.json({
        catalog: "application_withdrawal_reason",
        name: "Motivos",
        version: 1,
        items: [
          {
            id: "r-1",
            code: "OTHER_BANK",
            label: "Me aprobaron en otro banco",
            description: "",
            order: 1,
            active: true,
            parent_id: null,
            parent_code: null,
            metadata: {},
          },
        ],
      }),
    ),
    http.post(apiUrl(`/buyer/applications/${APP_ID}/withdrawals`), async ({ request }) => {
      state.withdrawals.push(await request.json());
      state.detail = { ...state.detail, is_closed: true, is_editable: false };
      state.session = {
        ...state.session,
        application: {
          ...state.session.application,
          is_closed: true,
          is_editable: false,
          public_status_label: "Desistida",
        },
      };
      return HttpResponse.json({}, { headers: { ETag: '"10"' } });
    }),
  );
  return state;
}

function renderHome() {
  return renderWithProviders(
    <ThemeProvider initialMode="light" hasCookie>
      <PortalGuard>
        <PortalHome />
      </PortalGuard>
    </ThemeProvider>,
  );
}

const sectionByTitle = (name: string) =>
  screen.getByRole("heading", { name, level: 2 }).closest("section")!;

beforeEach(() => {
  router.replace.mockReset();
  router.push.mockReset();
  router.pathname = "/portal";
});

describe("inicio del portal con datos completos", { timeout: 20_000 }, () => {
  it("saludo, estado, progreso, etapas y respuesta del banco", async () => {
    useHomeApi();
    renderHome();

    expect(await screen.findByRole("heading", { name: "Hola, Sofía" })).toBeInTheDocument();
    expect(screen.getByText(/Tu crédito de vivienda con Banco de Bogotá ·/)).toHaveTextContent(
      "Tu crédito de vivienda con Banco de Bogotá · SOL-000182",
    );

    const status = sectionByTitle("Estamos revisando tus documentos");
    expect(status).toHaveTextContent("Sube los documentos que te faltan.");
    expect(status).toHaveTextContent("Documentos listos10 de 16");
    expect(within(status).getByRole("img", { name: "10 de 16 documentos listos" })).toBeVisible();
    expect(status).toHaveTextContent("4 te tocan a ti · 1 lo está revisando tu asesor");

    const stages = within(status).getAllByRole("listitem");
    expect(stages.map((li) => li.textContent)).toEqual([
      "Tus datosCompletos",
      "DocumentosEn curso",
      "Respuesta del bancoPendiente",
    ]);
    expect(stages[1]).toHaveAttribute("aria-current", "step");
    expect(status).toHaveTextContent(/Tu acceso vence en/);

    const bank = sectionByTitle("Observación del banco");
    expect(bank).toHaveTextContent("Respuesta del banco · 16 nov 2026");
    expect(bank).toHaveTextContent("El banco pide un extracto más reciente.");
  });

  it("lo que necesitamos de ti: hasta 3, con titular, rechazo y su botón", async () => {
    useHomeApi();
    const user = userEvent.setup();
    renderHome();

    const todo = await screen.findByRole("region", { name: /Lo que necesitamos de ti/ });
    expect(todo).toHaveTextContent("Lo que necesitamos de ti4");
    const items = within(todo).getAllByRole("article");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Desprendible de nómina 2 de 3");
    expect(items[0]).toHaveTextContent("Corrígelo · Sofía Herrera · Titular");
    expect(items[0]).toHaveTextContent("Ilegible: La foto está borrosa.");
    expect(within(items[0]!).getByRole("button")).toHaveTextContent("Reemplazar documento");
    expect(items[2]).toHaveTextContent("Daniel Mejía · Segundo solicitante");
    expect(within(items[1]!).getByRole("button")).toHaveTextContent("Subir documento");
    expect(screen.queryByText("Certificado laboral")).not.toBeInTheDocument();

    // "Subir documento" abre la hoja de carga en el mismo inicio.
    await user.click(within(items[1]!).getByRole("button", { name: "Subir documento" }));
    expect(
      await screen.findByRole("dialog", { name: "Extracto bancario 2 de 3" }),
    ).toHaveTextContent("PDF, JPG o PNG, de hasta 10 MB.");
    expect(router.push).not.toHaveBeenCalled();
    expect(within(todo).getByRole("link", { name: "Ver todos mis documentos" })).toHaveAttribute(
      "href",
      "/portal/documentos",
    );
  });

  it("tu solicitud: lo que falta y una fila por sección con su enlace", async () => {
    useHomeApi();
    renderHome();

    const nav = await screen.findByRole("navigation", { name: "Secciones de tu solicitud" });
    expect(screen.getByText("Faltan 3 documentos.")).toBeInTheDocument();
    expect(screen.queryByText("Datos completos.")).not.toBeInTheDocument();

    const rows = within(nav).getAllByRole("link");
    await waitFor(() => expect(rows[1]).toHaveTextContent("$ 7.800.000 al mes"));
    expect(rows.map((a) => a.getAttribute("href"))).toEqual([
      "/portal/datos",
      "/portal/ingresos",
      `/portal/ingresos#participante-${CO_ID}`,
      "/portal/inmueble",
      "/portal/financiacion",
      "/portal/documentos",
    ]);
    expect(rows[0]).toHaveTextContent("Tus datos personalesSofía Herrera");
    expect(rows[2]).toHaveTextContent("Segundo solicitanteDaniel Mejía");
    expect(rows[3]).toHaveTextContent("Torres del Parque · Apto 1204");
    expect(rows[4]).toHaveTextContent("Banco de Bogotá · $ 365.000.000 a 20 años");
    expect(rows[5]).toHaveTextContent("10 de 16 listos4 pendientes");
  });

  it("tu asesor con WhatsApp (indicativo 57) y correo", async () => {
    useHomeApi();
    renderHome();
    const advisor = (await screen.findByText("Paula Rincón")).closest("section")!;
    expect(advisor).toHaveTextContent("Tu asesor de crédito");
    expect(within(advisor).getByRole("link", { name: /WhatsApp/ })).toHaveAttribute(
      "href",
      "https://wa.me/573001234567",
    );
    expect(within(advisor).getByRole("link", { name: /Correo/ })).toHaveAttribute(
      "href",
      "mailto:paula@example.com",
    );
  });
});

describe("inicio del portal con datos vacíos o nulos", { timeout: 20_000 }, () => {
  const empty = detailFixture({
    financing: null,
    property: null,
    advisor: null,
    latest_bank_update: null,
    stages: [],
    next_action: "",
    participants: [detailFixture().participants[0]!],
    progress: {
      ...detailFixture().progress,
      documents_required_total: 0,
      documents_completed_total: 0,
      items: [],
    },
  });

  it("sin banco, etapas, respuesta, asesor ni pendientes", async () => {
    useHomeApi({ detail: empty, slots: [] });
    // Sin perfil financiero (404): el handler más reciente gana.
    server.use(
      http.get(apiUrl("/buyer/participants/:id/financial-profile"), () =>
        apiError(404, "RESOURCE_NOT_FOUND"),
      ),
    );
    renderHome();

    expect(await screen.findByText(/^Tu crédito de vivienda/)).toHaveTextContent(
      "Tu crédito de vivienda · SOL-000182",
    );
    const status = sectionByTitle("Estamos revisando tus documentos");
    expect(within(status).queryByRole("list", { name: "Etapas" })).not.toBeInTheDocument();
    expect(status).not.toHaveTextContent("Documentos listos");
    expect(screen.queryByText(/Respuesta del banco/)).not.toBeInTheDocument();
    expect(screen.queryByText("Tu asesor de crédito")).not.toBeInTheDocument();
    expect(
      screen.getByText("Por ahora no necesitamos ningún documento de ti."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Lo que falta")).not.toBeInTheDocument();

    const rows = within(
      screen.getByRole("navigation", { name: "Secciones de tu solicitud" }),
    ).getAllByRole("link");
    expect(rows).toHaveLength(5);
    await waitFor(() => expect(rows[1]).toHaveTextContent("Ingresos y gastosSin datos todavía"));
    expect(rows[2]).toHaveTextContent("El inmuebleSin datos todavía");
    expect(rows[3]).toHaveTextContent("FinanciaciónSin datos todavía");
    expect(rows[4]).toHaveTextContent("0 de 0 listos");
  });

  it("financiación sin banco: solo monto y plazo", async () => {
    const base = detailFixture();
    useHomeApi({
      detail: detailFixture({
        financing: { ...base.financing!, bank_product: null, term_months: 18 },
      }),
    });
    renderHome();
    const nav = await screen.findByRole("navigation", { name: "Secciones de tu solicitud" });
    expect(within(nav).getAllByRole("link")[4]).toHaveTextContent(
      "Financiación$ 365.000.000 a 18 meses",
    );
    expect(screen.getByText(/^Tu crédito de vivienda/)).not.toHaveTextContent("con");
  });

  it("asesor sin teléfono: solo correo", async () => {
    useHomeApi({
      detail: detailFixture({
        advisor: { full_name: "Paula Rincón", email: "paula@example.com", phone: null },
      }),
    });
    renderHome();
    const advisor = (await screen.findByText("Paula Rincón")).closest("section")!;
    expect(within(advisor).queryByRole("link", { name: /WhatsApp/ })).not.toBeInTheDocument();
    expect(within(advisor).getByRole("link", { name: /Correo/ })).toBeInTheDocument();
  });

  it("si el detalle falla, error en línea con Reintentar", async () => {
    useHomeApi();
    server.use(
      http.get(apiUrl(`/buyer/applications/${APP_ID}`), () => apiError(500, "BOOM", "Falló.")),
    );
    renderHome();
    expect(
      await screen.findByRole(
        "heading",
        { name: "No pudimos cargar tu solicitud" },
        // La consulta del detalle reintenta un 5xx una vez.
        { timeout: 8_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("desistimiento", { timeout: 20_000 }, () => {
  it("pide motivo y confirmación, envía expected_version y queda en solo lectura", async () => {
    const state = useHomeApi();
    const user = userEvent.setup();
    renderHome();

    await user.click(
      await screen.findByRole("button", { name: "Ya no quiero continuar con la solicitud" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cerrar mi solicitud" }));
    expect(await within(dialog).findByText("Elige el motivo.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Confirma que entiendes que tu solicitud se cerrará."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("combobox")).toHaveAttribute("aria-invalid", "true");

    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("Me aprobaron en otro banco"));
    await user.type(within(dialog).getByRole("textbox"), "  Ya tengo crédito. ");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Cerrar mi solicitud" }));

    await waitFor(() =>
      expect(state.withdrawals).toEqual([
        { reason_code: "OTHER_BANK", expected_version: 9, comment: "Ya tengo crédito." },
      ]),
    );
    expect(await screen.findByText("Tu solicitud está cerrada")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Ya no quiero continuar con la solicitud" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("un error de la API con campo va al motivo", async () => {
    useHomeApi();
    server.use(
      http.post(apiUrl(`/buyer/applications/${APP_ID}/withdrawals`), () =>
        HttpResponse.json(
          {
            code: "VALIDATION_ERROR",
            message: "Datos inválidos.",
            details: [{ field: "reason_code", code: "invalid", message: "Motivo no válido." }],
            request_id: "r",
          },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderHome();
    await user.click(
      await screen.findByRole("button", { name: "Ya no quiero continuar con la solicitud" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("Me aprobaron en otro banco"));
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Cerrar mi solicitud" }));
    expect(await within(dialog).findByText("Motivo no válido.")).toBeInTheDocument();
  });

  it("con la solicitud cerrada no se ofrece", async () => {
    const base = sessionFixture();
    useHomeApi({
      detail: detailFixture({ is_closed: true, is_editable: false }),
      session: { ...base, application: { ...base.application, is_closed: true } },
    });
    renderHome();
    await screen.findByRole("heading", { name: "Hola, Sofía" });
    expect(
      screen.queryByRole("button", { name: "Ya no quiero continuar con la solicitud" }),
    ).not.toBeInTheDocument();
  });
});

describe("formato del inicio", { timeout: 20_000 }, () => {
  it("plazo, WhatsApp, carga de trabajo y frases", () => {
    expect(formatTerm(240)).toBe("20 años");
    expect(formatTerm(12)).toBe("1 año");
    expect(formatTerm(18)).toBe("18 meses");
    expect(formatTerm(1)).toBe("1 mes");
    expect(formatTerm(null)).toBeNull();
    expect(whatsappUrl("300 123 4567")).toBe("https://wa.me/573001234567");
    expect(whatsappUrl("+57 300 123 4567")).toBe("https://wa.me/573001234567");
    expect(whatsappUrl("6015550000")).toBe("https://wa.me/6015550000");
    expect(whatsappUrl("")).toBeNull();
    expect(whatsappUrl(null)).toBeNull();
    expect(workloadText(0, 0)).toBeNull();
    expect(workloadText(1, 0)).toBe("1 te toca a ti");
    expect(workloadText(0, 2)).toBe("2 los está revisando tu asesor");
    expect(inSentence("Vivienda nueva")).toBe("vivienda nueva");
    expect(firstName("Sofía")).toBe("Sofía");
  });
});
