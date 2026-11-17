import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ALL_PERMISSIONS, APP_ID, makeDetail } from "@/features/applications/workspace.fixtures";
import { WorkspaceScreen } from "@/features/applications/workspace-screen";
import { isResponseOverdue } from "@/features/filings/filing-card";
import { apiError, makeFiling, makeJob, useFilingsApi } from "@/features/filings/filings.fixtures";
import {
  defaultPastInput,
  fromLocalInput,
  isFutureInput,
  toLocalInput,
} from "@/features/filings/local-datetime";
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

const download = vi.hoisted(() => ({ startDownload: vi.fn() }));
vi.mock("@/features/filings/download", () => download);

const base = `/applications/${APP_ID}`;

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

const filingTab = () => screen.findByRole("tabpanel", { name: "Radicación" });

/** Pide el paquete y espera a que esté listo. */
async function preparePackage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Preparar paquete" }));
  await screen.findByText("SOL-000182_expediente.zip");
}

beforeEach(() => {
  window.history.replaceState(null, "", "/solicitudes/app-1?tab=radicacion");
  nav.replace.mockClear();
  download.startDownload.mockClear();
});

describe("radicación: pestaña", { timeout: 20_000 }, () => {
  it("sin filings.read no hay pestaña y ?tab=radicacion muestra el resumen", async () => {
    const api = useFilingsApi({ permissions: ALL_PERMISSIONS });
    renderScreen();
    await screen.findByRole("heading", { name: "SOL-000182" });

    expect(screen.queryByRole("tab", { name: /Radicación/ })).not.toBeInTheDocument();
    expect(await screen.findByRole("tabpanel", { name: "Resumen" })).toBeInTheDocument();
    expect(api.calls.filings).toBe(0);
  });

  it("con filings.read se ve entre Documentos e Historial, con el número de radicaciones", async () => {
    useFilingsApi({ filings: [makeFiling(2), makeFiling(1)] });
    renderScreen();
    await filingTab();

    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs.indexOf("Radicación 2")).toBeGreaterThan(-1);
    expect(tabs.findIndex((t) => t?.startsWith("Documentos"))).toBe(
      tabs.indexOf("Radicación 2") - 1,
    );
    expect(tabs.at(-1)).toBe("Historial");
  });

  it("sin radicaciones explica cuándo se registra", async () => {
    useFilingsApi({ detail: makeDetail() });
    renderScreen();
    const panel = await filingTab();

    expect(await within(panel).findByText("Todavía no hay radicaciones")).toBeInTheDocument();
    expect(
      within(panel).getByText("La radicación se registra después de entregar el paquete al banco."),
    ).toBeInTheDocument();
    // Fuera de "lista para radicar" no se entrega el paquete.
    expect(within(panel).queryByText("Entregar al banco")).not.toBeInTheDocument();
  });

  it("si la lista falla, se puede reintentar", async () => {
    useFilingsApi();
    server.use(
      http.get(apiUrl(`${base}/filings`), () => apiError(500, "INTERNAL_ERROR", "Falló.")),
    );
    renderScreen();
    const panel = await filingTab();
    expect(
      await within(panel).findByText("No pudimos cargar las radicaciones", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("radicación: paquete", { timeout: 20_000 }, () => {
  it("pide el paquete, consulta mientras se arma y descarga el ZIP con una URL nueva", async () => {
    const api = useFilingsApi({
      requested: makeJob({ status: "PENDING", completed_at: null, output: null }),
      polled: [makeJob()],
    });
    const user = renderScreen();
    const panel = await filingTab();

    // "Registrar radicación" espera al paquete.
    expect(within(panel).getByRole("button", { name: "Registrar radicación" })).toBeDisabled();
    await user.click(within(panel).getByRole("button", { name: "Preparar paquete" }));
    expect(await within(panel).findByText(/Preparando el paquete/)).toBeInTheDocument();

    expect(
      await within(panel).findByText("SOL-000182_expediente.zip", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(api.calls.packageGet).toBeGreaterThan(0);
    expect(within(panel).getByText(/1 documento · 2,4 MB/)).toBeInTheDocument();

    const zip = within(panel).getByRole("button", { name: "Descargar ZIP" });
    expect(zip).toHaveClass("ant-btn-primary");
    await user.click(zip);
    await waitFor(() =>
      expect(download.startDownload).toHaveBeenCalledWith("https://s3.example/zip?sig=1"),
    );
    // Después de descargar, la principal es registrar.
    await waitFor(() =>
      expect(within(panel).getByRole("button", { name: "Registrar radicación" })).toHaveClass(
        "ant-btn-primary",
      ),
    );
    await user.click(within(panel).getByRole("button", { name: "Descargar ZIP" }));
    await waitFor(() => expect(download.startDownload).toHaveBeenCalledTimes(2));
  });

  it("muestra el error de la API con sus detalles", async () => {
    useFilingsApi();
    server.use(
      http.post(apiUrl(`${base}/document-package-jobs`), () =>
        apiError(422, "APPLICATION_NOT_READY", "La solicitud no está lista.", [
          { code: "DOCUMENT_PENDING", message: "Falta el certificado laboral." },
        ]),
      ),
    );
    const user = renderScreen();
    const panel = await filingTab();
    await user.click(within(panel).getByRole("button", { name: "Preparar paquete" }));

    expect(await within(panel).findByText("No se pudo preparar el paquete")).toBeInTheDocument();
    expect(within(panel).getByText("La solicitud no está lista.")).toBeInTheDocument();
    expect(within(panel).getByText("Falta el certificado laboral.")).toBeInTheDocument();
  });

  it("un paquete fallido se puede volver a pedir", async () => {
    useFilingsApi({ requested: makeJob({ status: "FAILED", error_code: "STORAGE_UNAVAILABLE" }) });
    const user = renderScreen();
    const panel = await filingTab();
    await user.click(within(panel).getByRole("button", { name: "Preparar paquete" }));

    expect(await within(panel).findByText("No se pudo armar el paquete")).toBeInTheDocument();
    expect(within(panel).getByText(/STORAGE_UNAVAILABLE/)).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Preparar otro paquete" })).toBeEnabled();
  });

  it("si el paquete venció al descargar, lo dice y vuelve a leer el trabajo", async () => {
    const api = useFilingsApi({ polled: [makeJob({ status: "EXPIRED" })] });
    server.use(
      http.get(apiUrl("/document-package-jobs/:jobId/download"), () =>
        apiError(409, "PACKAGE_EXPIRED", "El paquete venció."),
      ),
    );
    const user = renderScreen();
    const panel = await filingTab();
    await preparePackage(user);
    await user.click(within(panel).getByRole("button", { name: "Descargar ZIP" }));

    expect(await within(panel).findByText("El paquete venció.")).toBeInTheDocument();
    await waitFor(() => expect(api.calls.packageGet).toBeGreaterThan(0));
    expect(await within(panel).findByText("El paquete venció")).toBeInTheDocument();
    expect(download.startDownload).not.toHaveBeenCalled();
  });

  it("sin filings.create no hay radicación ni acción principal", async () => {
    useFilingsApi({
      permissions: ["applications.read", "filings.read", "filings.prepare"],
    });
    const user = renderScreen();
    const panel = await filingTab();
    const prepare = await within(panel).findByRole("button", { name: "Preparar paquete" });
    expect(prepare).not.toHaveClass("ant-btn-primary");
    expect(within(panel).queryByRole("button", { name: "Registrar radicación" })).toBeNull();
    await user.click(prepare);
    expect(await within(panel).findByRole("button", { name: "Descargar ZIP" })).not.toHaveClass(
      "ant-btn-primary",
    );
  });
});

describe("radicación: registrar", { timeout: 20_000 }, () => {
  async function openModal(user: ReturnType<typeof userEvent.setup>) {
    await preparePackage(user);
    const panel = await filingTab();
    await user.click(within(panel).getByRole("button", { name: "Registrar radicación" }));
    return screen.findByRole("dialog");
  }

  async function chooseChannel(user: ReturnType<typeof userEvent.setup>, dialog: HTMLElement) {
    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("Correo electrónico"));
  }

  it("envía canal, referencia, fecha, paquete, producto y expected_version", async () => {
    const api = useFilingsApi();
    const user = renderScreen();
    const dialog = await openModal(user);

    expect(within(dialog).getByText("Banco de Bogotá · Leasing")).toBeInTheDocument();
    expect(within(dialog).getByText("SOL-000182_expediente.zip")).toBeInTheDocument();
    // La fecha de entrega viene con la hora actual.
    expect(within(dialog).getByLabelText("Fecha y hora de entrega")).toHaveValue(
      defaultPastInput(),
    );

    await user.click(within(dialog).getByRole("button", { name: "Registrar radicación" }));
    expect(await within(dialog).findByText("Elige el canal.")).toBeInTheDocument();

    await chooseChannel(user, dialog);
    await user.type(within(dialog).getByLabelText(/Referencia del banco/), " RAD-77 ");
    await user.type(within(dialog).getByLabelText(/Comentario/), "Entregada en el portal.");
    const before = api.calls.detail;
    await user.click(within(dialog).getByRole("button", { name: /Registrar radicación$/ }));

    await waitFor(() => expect(api.bodies.filing).toHaveLength(1));
    const body = api.bodies.filing[0] as Record<string, unknown>;
    expect(body).toMatchObject({
      bank_product_id: "p-1",
      package_job_id: "job-9",
      channel_code: "EMAIL",
      external_reference: "RAD-77",
      comment: "Entregada en el portal.",
      expected_version: 15,
    });
    expect(Date.parse(body.filed_at as string)).not.toBeNaN();

    expect(await screen.findByText("Radicación registrada")).toBeInTheDocument();
    // Se refresca el expediente: estado, etapas, completitud, radicaciones e historial.
    await waitFor(() => expect(api.calls.detail).toBeGreaterThan(before));
    expect(await screen.findByRole("heading", { name: /#1/ })).toBeInTheDocument();
  });

  it("no acepta una fecha futura", async () => {
    const api = useFilingsApi();
    const user = renderScreen();
    const dialog = await openModal(user);
    await chooseChannel(user, dialog);
    const date = within(dialog).getByLabelText("Fecha y hora de entrega");
    await user.clear(date);
    await user.type(date, "2099-01-01T10:00");
    await user.click(within(dialog).getByRole("button", { name: /Registrar radicación$/ }));

    expect(
      await within(dialog).findByText("La fecha de entrega no puede ser futura."),
    ).toBeInTheDocument();
    expect(api.bodies.filing).toHaveLength(0);
  });

  it("una precondición que falla muestra el mensaje de la API y el modal sigue abierto", async () => {
    useFilingsApi();
    server.use(
      http.post(apiUrl(`${base}/filings`), () =>
        apiError(409, "PACKAGE_OUTDATED", "El expediente cambió después de armar el paquete."),
      ),
    );
    const user = renderScreen();
    const dialog = await openModal(user);
    await chooseChannel(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: /Registrar radicación$/ }));

    expect(
      await screen.findByText("El expediente cambió después de armar el paquete."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("un error de campo va a su campo", async () => {
    useFilingsApi();
    server.use(
      http.post(apiUrl(`${base}/filings`), () =>
        apiError(400, "VALIDATION_ERROR", "Revisa los datos.", [
          { field: "external_reference", code: "invalid", message: "Referencia inválida." },
        ]),
      ),
    );
    const user = renderScreen();
    const dialog = await openModal(user);
    await chooseChannel(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: /Registrar radicación$/ }));

    expect(await within(dialog).findByText("Referencia inválida.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Referencia del banco/)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("409 STALE_VERSION muestra el aviso global con 'Recargar'", async () => {
    const api = useFilingsApi();
    server.use(
      http.post(apiUrl(`${base}/filings`), () => apiError(409, "STALE_VERSION", "Versión vieja.")),
    );
    const user = renderScreen();
    const dialog = await openModal(user);
    await chooseChannel(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: /Registrar radicación$/ }));

    expect(await screen.findByText("Alguien cambió esta solicitud")).toBeInTheDocument();
    const before = api.calls.detail;
    await user.click(screen.getByRole("button", { name: "Recargar" }));
    await waitFor(() => expect(api.calls.detail).toBeGreaterThan(before));
  });
});

describe("radicación: lista", { timeout: 20_000 }, () => {
  it("muestra número, banco y producto, canal, referencia, quién, cuándo, estado y respuestas", async () => {
    useFilingsApi({
      detail: makeDetail({ status: "CREDIT_ANALYSIS", status_label: "Análisis de crédito" }),
      filings: [
        makeFiling(2, {
          status: "IN_ANALYSIS",
          status_label: "En análisis",
          responses_count: 2,
          comment: "Entregada por correo.",
        }),
        makeFiling(1, {
          status: "RETURNED",
          status_label: "Devuelta",
          external_reference: null,
          target_response_at: "2026-01-01T10:00:00Z",
        }),
      ],
    });
    renderScreen();
    const panel = await filingTab();

    const second = (await within(panel).findByRole("heading", { name: /#2/ })).closest("article")!;
    expect(within(second).getByText("Banco de Bogotá · Leasing")).toBeInTheDocument();
    expect(within(second).getByText("En análisis")).toHaveAttribute("data-tone", "info");
    expect(within(second).getByText("Portal del banco")).toBeInTheDocument();
    expect(within(second).getByText("RAD-002")).toBeInTheDocument();
    expect(within(second).getByText("por Paula Rincón")).toBeInTheDocument();
    expect(within(second).getByText("2")).toBeInTheDocument();
    expect(within(second).getByText("Entregada por correo.")).toBeInTheDocument();
    expect(within(second).queryByText("Vencida")).toBeNull();

    const first = within(panel).getByRole("heading", { name: /#1/ }).closest("article")!;
    expect(within(first).getByText("Devuelta")).toHaveAttribute("data-tone", "warning");
    expect(within(first).getByText("Vencida")).toBeInTheDocument();
    expect(within(panel).queryByText("Entregar al banco")).not.toBeInTheDocument();
  });

  it("corrige la referencia y el comentario; vacío los borra", async () => {
    const api = useFilingsApi({ filings: [makeFiling(1, { comment: "Nota vieja." })] });
    const user = renderScreen();
    const panel = await filingTab();
    await user.click(
      await within(panel).findByRole("button", { name: /Corregir referencia o comentario/ }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Referencia del banco/)).toHaveValue("RAD-001");

    await user.clear(within(dialog).getByLabelText(/Referencia del banco/));
    await user.type(within(dialog).getByLabelText(/Referencia del banco/), "RAD-NUEVA");
    await user.clear(within(dialog).getByLabelText(/Comentario/));
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    await waitFor(() =>
      expect(api.bodies.patch).toEqual([{ external_reference: "RAD-NUEVA", comment: null }]),
    );
    expect(await screen.findByText("Radicación corregida")).toBeInTheDocument();
    expect(await within(panel).findByText("RAD-NUEVA")).toBeInTheDocument();
  });

  it("la corrección muestra el error de la API en su campo", async () => {
    useFilingsApi({ filings: [makeFiling(1)] });
    server.use(
      http.patch(apiUrl("/filings/:id"), () =>
        apiError(400, "VALIDATION_ERROR", "Revisa los datos.", [
          { field: "external_reference", code: "max_length", message: "Demasiado larga." },
        ]),
      ),
    );
    const user = renderScreen();
    const panel = await filingTab();
    await user.click(
      await within(panel).findByRole("button", { name: /Corregir referencia o comentario/ }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByText("Demasiado larga.")).toBeInTheDocument();
  });

  it("sin filings.update no se corrige", async () => {
    useFilingsApi({
      filings: [makeFiling(1)],
      permissions: ["applications.read", "filings.read"],
    });
    renderScreen();
    const panel = await filingTab();
    await within(panel).findByRole("heading", { name: /#1/ });
    expect(within(panel).queryByRole("button", { name: /Corregir/ })).toBeNull();
  });

  it("los documentos entregados se despliegan para el asesor asignado", async () => {
    useFilingsApi({ filings: [makeFiling(1)] });
    const user = renderScreen();
    const panel = await filingTab();
    const toggle = await within(panel).findByRole("button", { name: "Ver documentos entregados" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(await within(panel).findByText("Certificado laboral")).toBeInTheDocument();
    expect(within(panel).getByText(/Versión 2 · certificado\.pdf · 178/)).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Ocultar documentos entregados" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("otro asesor no ve los documentos entregados", async () => {
    useFilingsApi({
      filings: [makeFiling(1)],
      detail: makeDetail({ assigned_advisor: { id: "u-2", name: "Otro" } }),
    });
    renderScreen();
    const panel = await filingTab();
    await within(panel).findByRole("heading", { name: /#1/ });
    expect(within(panel).queryByRole("button", { name: /documentos entregados/ })).toBeNull();
  });
});

describe("radicación: reglas de pantalla", () => {
  it("la respuesta vence solo si pasó la fecha y no hay respuestas", () => {
    const now = Date.parse("2026-11-17T12:00:00Z");
    const late = makeFiling(1, { target_response_at: "2026-11-16T12:00:00Z" });
    expect(isResponseOverdue(late, now)).toBe(true);
    expect(isResponseOverdue({ ...late, responses_count: 1 }, now)).toBe(false);
    expect(isResponseOverdue({ ...late, target_response_at: null }, now)).toBe(false);
    expect(isResponseOverdue(makeFiling(1), now)).toBe(false);
  });

  it("convierte la fecha local del campo y detecta las futuras", () => {
    const date = new Date(2026, 10, 17, 9, 5);
    expect(toLocalInput(date)).toBe("2026-11-17T09:05");
    expect(fromLocalInput("2026-11-17T09:05")).toBe(date.toISOString());
    expect(fromLocalInput("")).toBeNull();
    expect(fromLocalInput("no")).toBeNull();
    expect(isFutureInput("2026-11-17T09:05", date.getTime())).toBe(false);
    expect(isFutureInput("2026-11-17T09:10", date.getTime())).toBe(true);
    // Por defecto, un minuto antes: nunca queda a segundos del presente.
    expect(defaultPastInput(date.getTime() + 1000)).toBe("2026-11-17T09:04");
  });
});
