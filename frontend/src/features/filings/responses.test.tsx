import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ACTIONS, APP_ID, makeDetail, makeSlot } from "@/features/applications/workspace.fixtures";
import { WorkspaceScreen } from "@/features/applications/workspace-screen";
// Con aserción: las acciones de prueba no traen `kind`, que el contrato agrega en el #20.
import type { AvailableAction } from "@/features/applications/workspace-queries";
import { openObservations } from "@/features/filings/filing-banner";
import {
  apiError,
  makeFiling,
  makeResponse,
  useFilingsApi,
  type FilingsApi,
} from "@/features/filings/filings.fixtures";
import { RESPONSE_FORMS, responseForm } from "@/features/filings/response-fields";
import { buildResponseBody, observableSlots } from "@/features/filings/response-modal";
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

const upload = vi.hoisted(() => ({ uploadFile: vi.fn() }));
vi.mock("@/lib/api/upload", () => upload);

// PDF.js no corre en jsdom: se registra la URL que recibe el visor.
const pdf = vi.hoisted(() => ({ calls: [] as string[] }));
vi.mock("@/components/ui/pdf-loader", () => ({
  loadPdf: (url: string) => {
    pdf.calls.push(url);
    return new Promise(() => {});
  },
}));

type User = ReturnType<typeof userEvent.setup>;

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

const FILED = makeDetail({ status: "FILED", status_label: "Radicada" });
const filingTab = () => screen.findByRole("tabpanel", { name: "Radicación" });
const card = async (n: number) =>
  (await screen.findByRole("heading", { name: new RegExp(`#${n}`) })).closest("article")!;

/** Una radicación (#1) con la solicitud radicada; las respuestas, las que se pasen. */
function useFiled(overrides: Parameters<typeof useFilingsApi>[0] = {}): FilingsApi {
  return useFilingsApi({ detail: FILED, filings: [makeFiling(1)], ...overrides });
}

async function openRecord(user: User) {
  const filing = await card(1);
  await user.click(await within(filing).findByRole("button", { name: "Registrar respuesta" }));
  return screen.findByRole("dialog");
}

/**
 * Elige una opción de un `Select` y espera a verla elegida dentro del modal (el menú va
 * en un portal fuera de él). Con la suite cargada, un clic durante la animación del menú
 * a veces no cuenta: se reintenta.
 */
async function choose(user: User, dialog: HTMLElement, label: RegExp | string, option: string) {
  const picked = () =>
    within(dialog)
      .queryAllByTitle(option)
      .some(
        (el) =>
          el.closest(".ant-select") === within(dialog).getByLabelText(label).closest(".ant-select"),
      );
  // Con la suite completa en una máquina cargada, 5 s no siempre alcanzan.
  await waitFor(
    async () => {
      if (picked()) return;
      await user.click(within(dialog).getByLabelText(label));
      const options = (await screen.findAllByTitle(option)).filter((el) =>
        el.classList.contains("ant-select-item-option"),
      );
      await user.click(options.at(-1)!);
      expect(picked()).toBe(true);
    },
    { timeout: 15_000 },
  );
}

const submit = (user: User, dialog: HTMLElement) =>
  user.click(
    within(dialog).getByRole("button", { name: /(Registrar respuesta|Guardar corrección)$/ }),
  );

beforeEach(() => {
  window.history.replaceState(null, "", "/solicitudes/app-1?tab=radicacion");
  nav.replace.mockClear();
  upload.uploadFile.mockReset();
  pdf.calls.length = 0;
});

describe("respuestas: formulario por tipo", { timeout: 30_000 }, () => {
  it("pide solo los campos del tipo elegido", async () => {
    useFiled();
    const user = renderScreen();
    const dialog = await openRecord(user);

    expect(within(dialog).queryByLabelText(/Mensaje al comprador/)).toBeNull();
    await choose(user, dialog, "Tipo de respuesta", "Recibida");
    expect(within(dialog).getByLabelText("Mensaje al comprador (opcional)")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Motivo")).toBeNull();

    await choose(user, dialog, "Tipo de respuesta", "Aprobada");
    expect(within(dialog).getByLabelText("Monto aprobado")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Plazo en meses")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Vigencia (opcional)")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Mensaje al comprador")).toBeInTheDocument();

    await choose(user, dialog, "Tipo de respuesta", "Devuelta con observaciones");
    expect(within(dialog).getByLabelText("Motivo")).toBeInTheDocument();
    expect(within(dialog).getByText("Documentos observados")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Monto aprobado")).toBeNull();

    await choose(user, dialog, "Tipo de respuesta", "Desembolsada");
    expect(within(dialog).getByLabelText("Monto desembolsado")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Motivo")).toBeNull();

    await choose(user, dialog, "Tipo de respuesta", "Otra");
    expect(within(dialog).getByLabelText("Nota interna")).toBeInTheDocument();
    await submit(user, dialog);
    expect(await within(dialog).findByText("Escribe la nota interna.")).toBeInTheDocument();
  });

  const CASES: {
    type: string;
    label: string;
    fill: (user: User, dialog: HTMLElement) => Promise<void>;
    errorField: string;
    errorLabel: RegExp;
    expected: Record<string, unknown>;
  }[] = [
    {
      type: "RECEIVED",
      label: "Recibida",
      fill: async () => {},
      errorField: "received_at",
      errorLabel: /Fecha y hora de la respuesta/,
      expected: {},
    },
    {
      type: "IN_ANALYSIS",
      label: "En análisis",
      fill: async (user, dialog) => {
        await user.type(within(dialog).getByLabelText(/Referencia del banco/), "AN-1");
      },
      errorField: "external_reference",
      errorLabel: /Referencia del banco/,
      expected: { external_reference: "AN-1" },
    },
    {
      type: "APPROVED",
      label: "Aprobada",
      fill: async (user, dialog) => {
        await user.type(within(dialog).getByLabelText("Monto aprobado"), "285000000");
        await user.type(within(dialog).getByLabelText("Plazo en meses"), "240");
        await user.type(within(dialog).getByLabelText("Mensaje al comprador"), "Aprobado.");
      },
      errorField: "approved_amount_cop",
      errorLabel: /Monto aprobado/,
      expected: {
        approved_amount_cop: 285_000_000,
        approved_term_months: 240,
        public_message: "Aprobado.",
      },
    },
    {
      type: "REJECTED",
      label: "Rechazada",
      fill: async (user, dialog) => {
        await choose(user, dialog, "Motivo", "Capacidad de pago insuficiente");
        await user.type(within(dialog).getByLabelText("Mensaje al comprador"), "No aprobado.");
      },
      errorField: "public_message",
      errorLabel: /Mensaje al comprador/,
      expected: { reason_code: "PAYMENT_CAPACITY", public_message: "No aprobado." },
    },
    {
      type: "DISBURSED",
      label: "Desembolsada",
      fill: async (user, dialog) => {
        await user.type(within(dialog).getByLabelText("Monto desembolsado"), "280000000");
      },
      errorField: "disbursed_amount_cop",
      errorLabel: /Monto desembolsado/,
      expected: { disbursed_amount_cop: 280_000_000 },
    },
    {
      type: "OTHER",
      label: "Otra",
      fill: async (user, dialog) => {
        await user.type(within(dialog).getByLabelText("Nota interna"), "Llamó el banco.");
      },
      errorField: "internal_comment",
      errorLabel: /Nota interna/,
      expected: { internal_comment: "Llamó el banco." },
    },
  ];

  it.each(CASES)("$type: error de campo de la API en su campo y después éxito", async (c) => {
    const api = useFiled({
      detail: makeDetail({ status: "LEGALIZATION", status_label: "Legalización" }),
    });
    let fail = true;
    server.use(
      http.post(apiUrl("/filings/:id/responses"), () =>
        fail
          ? apiError(400, "VALIDATION_ERROR", "Revisa los datos.", [
              { field: c.errorField, code: "invalid", message: "Dato inválido para el banco." },
            ])
          : undefined,
      ),
    );
    const user = renderScreen();
    const dialog = await openRecord(user);
    await choose(user, dialog, "Tipo de respuesta", c.label);
    await c.fill(user, dialog);
    await submit(user, dialog);

    expect(await within(dialog).findByText("Dato inválido para el banco.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText(c.errorLabel)).toHaveAttribute("aria-invalid", "true");

    fail = false;
    await submit(user, dialog);
    await waitFor(() => expect(api.bodies.response).toHaveLength(1));
    const body = api.bodies.response[0]!;
    expect(body).toMatchObject({ response_type: c.type, expected_version: 15, ...c.expected });
    expect(Date.parse(body.received_at as string)).not.toBeNaN();
    // Solo van los campos del tipo.
    const allowed = new Set([
      "response_type",
      "received_at",
      "expected_version",
      "external_reference",
      ...RESPONSE_FORMS[c.type]!.fields,
    ]);
    expect(Object.keys(body).filter((k) => !allowed.has(k))).toEqual([]);
    expect(await screen.findByText("Respuesta registrada")).toBeInTheDocument();
  });

  it("RETURNED: devolución con dos observaciones, cada una con motivo y mensaje", async () => {
    const api = useFiled({
      slots: [makeSlot(1, "Certificado laboral"), makeSlot(2, "Extracto bancario 1 de 3")],
    });
    const user = renderScreen();
    const dialog = await openRecord(user);
    await choose(user, dialog, "Tipo de respuesta", "Devuelta con observaciones");
    await choose(user, dialog, "Motivo", "Corrección de documentos");
    await user.type(
      within(dialog).getByLabelText("Mensaje al comprador"),
      "Actualiza dos documentos.",
    );

    await submit(user, dialog);
    expect(
      await within(dialog).findByText("Elige al menos un documento observado."),
    ).toBeInTheDocument();

    // Agrupados por participante, como en Documentos.
    expect(within(dialog).getByText("Sofía Herrera")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox", { name: /Certificado laboral/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Extracto bancario/ }));
    await submit(user, dialog);
    expect(
      await within(dialog).findAllByText("Escribe qué debe corregir el comprador."),
    ).toHaveLength(2);

    await choose(user, dialog, "Motivo de Certificado laboral", "Desactualizado");
    await user.type(
      within(dialog).getByLabelText("Mensaje al comprador sobre Certificado laboral"),
      "Expedido hace menos de 30 días.",
    );
    await choose(user, dialog, "Motivo de Extracto bancario 1 de 3", "Ilegible");
    await user.type(
      within(dialog).getByLabelText("Mensaje al comprador sobre Extracto bancario 1 de 3"),
      "Vuelve a cargarlo.",
    );
    await submit(user, dialog);

    await waitFor(() => expect(api.bodies.response).toHaveLength(1));
    expect(api.bodies.response[0]).toMatchObject({
      response_type: "RETURNED",
      reason_code: "DOCUMENT_CORRECTION",
      public_message: "Actualiza dos documentos.",
      observations: [
        {
          document_slot_id: "s-1",
          reason_code: "OUTDATED",
          message: "Expedido hace menos de 30 días.",
        },
        { document_slot_id: "s-2", reason_code: "ILLEGIBLE", message: "Vuelve a cargarlo." },
      ],
    });
  });

  it("no acepta una respuesta anterior a la radicación", async () => {
    const api = useFiled();
    const user = renderScreen();
    const dialog = await openRecord(user);
    await choose(user, dialog, "Tipo de respuesta", "Recibida");
    const date = within(dialog).getByLabelText("Fecha y hora de la respuesta");
    await user.clear(date);
    await user.type(date, "2026-01-01T10:00");
    await submit(user, dialog);
    expect(
      await within(dialog).findByText("La respuesta no puede ser anterior a la radicación."),
    ).toBeInTheDocument();
    expect(api.bodies.response).toHaveLength(0);
  });

  it("un tipo no admitido en el estado muestra el mensaje de la API", async () => {
    useFiled();
    server.use(
      http.post(apiUrl("/filings/:id/responses"), () =>
        apiError(
          409,
          "INVALID_STATE_TRANSITION",
          "Una respuesta DISBURSED no se registra en FILED.",
        ),
      ),
    );
    const user = renderScreen();
    const dialog = await openRecord(user);
    await choose(user, dialog, "Tipo de respuesta", "Desembolsada");
    await user.type(within(dialog).getByLabelText("Monto desembolsado"), "1000");
    await submit(user, dialog);
    expect(
      await screen.findByText("Una respuesta DISBURSED no se registra en FILED."),
    ).toBeInTheDocument();
  });
});

describe("respuestas: lista, permisos y corrección", { timeout: 30_000 }, () => {
  it("solo se registra en la última radicación", async () => {
    useFilingsApi({ detail: FILED, filings: [makeFiling(2), makeFiling(1)] });
    renderScreen();
    await filingTab();
    const latest = await card(2);
    const older = await card(1);
    expect(
      await within(latest).findByRole("button", { name: "Registrar respuesta" }),
    ).toBeInTheDocument();
    expect(within(older).queryByRole("button", { name: "Registrar respuesta" })).toBeNull();
  });

  it("sin filings.record_response no se registra", async () => {
    useFiled({ permissions: ["applications.read", "filings.read"] });
    renderScreen();
    const filing = await card(1);
    expect(
      await within(filing).findByText("El banco todavía no ha respondido."),
    ).toBeInTheDocument();
    expect(within(filing).queryByRole("button", { name: "Registrar respuesta" })).toBeNull();
  });

  it("el asesor ve nota interna, montos y evidencia; el broker, solo lo público", async () => {
    useFiled({
      responses: {
        "fi-1": [
          makeResponse(1, {
            response_type: "APPROVED",
            response_type_label: "Aprobada",
            public_message: "Tu crédito fue aprobado.",
            internal_comment: "Sujeto a legalización.",
            approved_amount_cop: 285_000_000,
            approved_term_months: 240,
            valid_until: "2026-12-03",
            external_reference: "APR-9",
          }),
        ],
      },
    });
    renderScreen();
    const filing = await card(1);
    expect(await within(filing).findByText("Tu crédito fue aprobado.")).toBeInTheDocument();
    expect(within(filing).getByText("Aprobada")).toHaveAttribute("data-tone", "success");
    expect(within(filing).getByText("Sujeto a legalización.")).toBeInTheDocument();
    expect(within(filing).getByText("240 meses")).toBeInTheDocument();
    expect(within(filing).getByText("APR-9")).toBeInTheDocument();
    expect(within(filing).getByText(/285\.000\.000/)).toBeInTheDocument();
  });

  it("sin los campos restringidos (broker) no muestra nota, montos ni evidencia", async () => {
    useFiled({
      permissions: ["applications.read", "filings.read"],
      responses: {
        "fi-1": [
          {
            id: "re-1",
            filing_id: "fi-1",
            response_type: "IN_ANALYSIS",
            response_type_label: "En análisis",
            received_at: "2026-11-11T10:00:00Z",
            public_message: "El banco está estudiando tu solicitud.",
            created_at: "2026-11-11T10:01:00Z",
          },
        ],
      },
    });
    renderScreen();
    const filing = await card(1);
    expect(
      await within(filing).findByText("El banco está estudiando tu solicitud."),
    ).toBeInTheDocument();
    expect(within(filing).queryByText(/Nota interna/)).toBeNull();
    expect(within(filing).queryByText(/Evidencia/)).toBeNull();
    expect(within(filing).queryByText(/Registró/)).toBeNull();
    expect(within(filing).queryByRole("button", { name: "Adjuntar evidencia" })).toBeNull();
  });

  it("corrige la última respuesta con el mismo tipo y corrects_response_id", async () => {
    const api = useFiled({
      responses: {
        "fi-1": [
          makeResponse(1),
          makeResponse(2, {
            response_type: "OTHER",
            response_type_label: "Otra",
            internal_comment: "Llamó.",
          }),
        ],
      },
    });
    const user = renderScreen();
    const filing = await card(1);
    const buttons = await within(filing).findAllByRole("button", {
      name: "Corregir esta respuesta",
    });
    expect(buttons).toHaveLength(1);
    await user.click(buttons[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("combobox", { name: "Tipo de respuesta" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Nota interna"), "Llamó el banco el martes.");
    await submit(user, dialog);

    await waitFor(() => expect(api.bodies.response).toHaveLength(1));
    expect(api.bodies.response[0]).toMatchObject({
      response_type: "OTHER",
      corrects_response_id: "re-2",
      internal_comment: "Llamó el banco el martes.",
    });
    expect(await screen.findByText("Respuesta corregida")).toBeInTheDocument();
    // Una corrección no abre la evidencia.
    expect(screen.queryByRole("dialog", { name: "Adjuntar evidencia" })).toBeNull();
  });

  it("si la API no admite la corrección, muestra su mensaje", async () => {
    useFiled({ responses: { "fi-1": [makeResponse(1)] } });
    server.use(
      http.post(apiUrl("/filings/:id/responses"), () =>
        apiError(409, "RESPONSE_CORRECTION_NOT_ALLOWED", "Esta respuesta ya no se puede corregir."),
      ),
    );
    const user = renderScreen();
    const filing = await card(1);
    await user.click(
      await within(filing).findByRole("button", { name: "Corregir esta respuesta" }),
    );
    const dialog = await screen.findByRole("dialog");
    await submit(user, dialog);
    expect(await screen.findByText("Esta respuesta ya no se puede corregir.")).toBeInTheDocument();
  });
});

describe("respuestas: evidencia", { timeout: 30_000 }, () => {
  const pdfFile = () => new File(["%PDF"], "carta.pdf", { type: "application/pdf" });
  const fileInput = () => document.querySelector<HTMLInputElement>(".ant-modal input[type=file]")!;

  it("después de registrar, se ofrece adjuntar y se sube con uploadFile", async () => {
    useFiled();
    upload.uploadFile.mockResolvedValue({ data: {}, version: null });
    const user = renderScreen();
    const dialog = await openRecord(user);
    await choose(user, dialog, "Tipo de respuesta", "Recibida");
    await submit(user, dialog);

    const evidence = await screen.findByRole("dialog", { name: "Adjuntar evidencia" });
    expect(within(evidence).getByText("PDF, JPG o PNG · máximo 10 MB")).toBeInTheDocument();
    await user.upload(fileInput(), pdfFile());
    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(1));
    expect(upload.uploadFile.mock.calls[0]![0]).toMatchObject({
      path: "/api/v1/filing-responses/re-100/evidence",
    });
    expect(await screen.findByText("Evidencia adjunta")).toBeInTheDocument();
  });

  it("un tipo de archivo inválido no se envía", async () => {
    useFiled({ responses: { "fi-1": [makeResponse(1)] } });
    const user = userEvent.setup({ applyAccept: false });
    render(
      <App>
        <QueryProvider>
          <WorkspaceScreen id={APP_ID} />
        </QueryProvider>
      </App>,
    );
    const filing = await card(1);
    await user.click(await within(filing).findByRole("button", { name: "Adjuntar evidencia" }));
    await screen.findByRole("dialog", { name: "Adjuntar evidencia" });
    await user.upload(fileInput(), new File(["x"], "nota.txt", { type: "text/plain" }));
    expect(await screen.findByText(/Este tipo de archivo no se acepta/)).toBeInTheDocument();
    expect(upload.uploadFile).not.toHaveBeenCalled();
  });

  it("'Ver evidencia' pide la URL y la abre en el visor; en análisis, no se abre", async () => {
    useFiled({
      responses: {
        "fi-1": [
          makeResponse(1, {
            evidence: {
              filename: "correo.pdf",
              mime_type: "application/pdf",
              size_bytes: 2048,
              scan_status: "PENDING",
              scanned_at: null,
              uploaded_at: "2026-11-11T10:02:00Z",
            },
          }),
          makeResponse(2, {
            evidence: {
              filename: "carta.pdf",
              mime_type: "application/pdf",
              size_bytes: 4096,
              scan_status: "CLEAN",
              scanned_at: "2026-11-11T10:03:00Z",
              uploaded_at: "2026-11-11T10:02:00Z",
            },
          }),
        ],
      },
    });
    const user = renderScreen();
    const filing = await card(1);
    expect(await within(filing).findByText("Se está analizando el archivo.")).toBeInTheDocument();
    const view = within(filing).getAllByRole("button", { name: "Ver evidencia" });
    expect(view).toHaveLength(1);
    await user.click(view[0]!);
    await waitFor(() => expect(pdf.calls).toContain("https://s3.example/evidence?sig=1"));
  });

  it("si la descarga falla, lo dice junto a la evidencia", async () => {
    useFiled({
      responses: {
        "fi-1": [
          makeResponse(1, {
            evidence: {
              filename: "carta.pdf",
              mime_type: "application/pdf",
              size_bytes: 4096,
              scan_status: "CLEAN",
              scanned_at: null,
              uploaded_at: "2026-11-11T10:02:00Z",
            },
          }),
        ],
      },
    });
    server.use(
      http.get(apiUrl("/filing-responses/:id/evidence/download"), () =>
        apiError(409, "FILE_NOT_CLEAN", "El archivo todavía no está disponible."),
      ),
    );
    const user = renderScreen();
    const filing = await card(1);
    await user.click(await within(filing).findByRole("button", { name: "Ver evidencia" }));
    expect(
      await within(filing).findByText("El archivo todavía no está disponible."),
    ).toBeInTheDocument();
  });
});

describe("respuestas: banners", { timeout: 30_000 }, () => {
  const returned = (resolved: boolean) =>
    makeResponse(1, {
      response_type: "RETURNED",
      response_type_label: "Devuelta",
      reason: { code: "DOCUMENT_CORRECTION", label: "Corrección de documentos" },
      public_message: "Actualiza el certificado.",
      observations: [
        {
          id: "ob-1",
          document_slot_id: "s-1",
          reason: { code: "OUTDATED", label: "Desactualizado" },
          message: "Expedido hace menos de 30 días.",
          resolved_at: resolved ? "2026-11-12T10:00:00Z" : null,
          resolved_by_file_id: null,
          created_at: "2026-11-11T10:00:00Z",
        },
      ],
    });

  it("en observación: 'El banco observó N documentos' con enlace a cada uno", async () => {
    useFiled({
      detail: makeDetail({ status: "BANK_OBSERVATION", status_label: "Observada por el banco" }),
      responses: { "fi-1": [returned(false)] },
    });
    const user = renderScreen();
    const panel = await filingTab();
    const banner = (await within(panel).findByText("El banco observó 1 documento")).closest(
      "[role=alert]",
    ) as HTMLElement;
    await user.click(within(banner).getByRole("button", { name: "Certificado laboral" }));
    await waitFor(() =>
      expect(nav.replace).toHaveBeenLastCalledWith("/solicitudes/app-1?tab=documentos&slot=s-1", {
        scroll: false,
      }),
    );
  });

  it("resueltas: recuerda la acción 'lista para radicar de nuevo' del encabezado", async () => {
    useFiled({
      detail: makeDetail({
        status: "BANK_OBSERVATION",
        status_label: "Observada por el banco",
        available_actions: [
          {
            code: "MARK_READY_TO_REFILE",
            label: "Lista para radicar de nuevo",
            target_status: "READY_TO_FILE",
            target_status_label: "Lista para radicar",
            guard_code: "APPLICATION_READY_TO_REFILE",
          },
        ] as AvailableAction[],
      }),
      responses: { "fi-1": [returned(true)] },
    });
    renderScreen();
    const panel = await filingTab();
    expect(
      await within(panel).findByText("Las observaciones del banco están resueltas"),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(
        "Para radicar de nuevo, usa «Lista para radicar de nuevo» en las acciones de la solicitud.",
      ),
    ).toBeInTheDocument();
    expect(within(panel).getByText(/Resuelta el/)).toBeInTheDocument();
  });

  it("aprobada: recuerda 'Iniciar legalización'", async () => {
    useFiled({
      detail: makeDetail({
        status: "APPROVED",
        status_label: "Aprobada",
        available_actions: [
          {
            code: "START_LEGALIZATION",
            label: "Iniciar legalización",
            target_status: "LEGALIZATION",
            target_status_label: "Legalización",
            guard_code: "",
          },
          ACTIONS.withdraw,
        ] as AvailableAction[],
      }),
    });
    renderScreen();
    const panel = await filingTab();
    expect(await within(panel).findByText("El banco aprobó el crédito")).toBeInTheDocument();
    expect(
      within(panel).getByText(
        "Para seguir con la legalización, usa «Iniciar legalización» en las acciones de la solicitud.",
      ),
    ).toBeInTheDocument();
  });
});

describe("respuestas: reglas de pantalla", () => {
  it("cada tipo pide un subconjunto de sus campos; un tipo desconocido, solo los comunes", () => {
    for (const form of Object.values(RESPONSE_FORMS)) {
      expect(form.required.every((f) => form.fields.includes(f))).toBe(true);
    }
    expect(RESPONSE_FORMS.RETURNED!.reasonCatalog).toBe("filing_return_reason");
    expect(RESPONSE_FORMS.REJECTED!.reasonCatalog).toBe("filing_rejection_reason");
    expect(responseForm("NEW_TYPE")).toEqual({
      fields: ["public_message", "internal_comment"],
      required: [],
    });
    expect(responseForm(null).required).toEqual([]);
  });

  it("el cuerpo lleva solo los campos del tipo", () => {
    const values = {
      response_type: "RECEIVED",
      received_at: "2026-11-17T09:00",
      external_reference: "",
      reason_code: "OTHER",
      public_message: " ",
      internal_comment: "Nota",
      approved_amount_cop: 10,
      approved_term_months: 5,
      valid_until: "2026-12-01",
      disbursed_amount_cop: 7,
      observations: [{ document_slot_id: "s-1", reason_code: "X", message: " m " }],
    };
    expect(buildResponseBody(values, 3, null)).toEqual({
      response_type: "RECEIVED",
      received_at: new Date("2026-11-17T09:00").toISOString(),
      internal_comment: "Nota",
      expected_version: 3,
    });
    expect(
      buildResponseBody({ ...values, response_type: "RETURNED" }, 3, makeResponse(1)),
    ).toMatchObject({
      reason_code: "OTHER",
      observations: [{ document_slot_id: "s-1", reason_code: "X", message: "m" }],
      corrects_response_id: "re-1",
    });
  });

  it("solo se observan slots con versión cargada y no exonerados; abiertas = sin resolver", () => {
    const waived = { ...makeSlot(2, "B"), status: "WAIVED" } as ReturnType<typeof makeSlot>;
    const empty = { ...makeSlot(3, "C"), current_file: null } as ReturnType<typeof makeSlot>;
    expect(observableSlots([makeSlot(1, "A"), waived, empty]).map((s) => s.id)).toEqual(["s-1"]);
    const obs = (id: string, resolved: string | null) => ({
      id,
      document_slot_id: "s-1",
      reason: { code: "X", label: "X" },
      message: "",
      resolved_at: resolved,
      resolved_by_file_id: null,
      created_at: "",
    });
    expect(
      openObservations([
        makeResponse(1, { observations: [obs("a", null), obs("b", "2026-01-01")] }),
        makeResponse(2, { observations: undefined }),
      ]).map((o) => o.id),
    ).toEqual(["a"]);
  });
});
