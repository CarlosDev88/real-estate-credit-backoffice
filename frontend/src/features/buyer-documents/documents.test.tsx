import { act, configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfigProvider } from "antd";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BuyerDocumentsScreen, slotName } from "@/features/buyer-documents/documents-screen";
import {
  listLabels,
  requirementsText,
  sortSlots,
  statusTabs,
  summaryText,
  typeLabel,
  viewerKind,
} from "@/features/buyer-documents/slot-format";
import { PortalGuard } from "@/features/buyer-portal/portal-guard";
import {
  APP_ID,
  CO_ID,
  apiError,
  detailFixture,
  sessionFixture,
  slotFixture,
  slotsPage,
} from "@/features/buyer-portal/portal.fixtures";
import type { BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";
import { ThemeProvider } from "@/providers/theme-provider";

configure({ asyncUtilTimeout: 5_000 });

const router = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  pathname: "/portal/documentos",
}));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => router.pathname,
}));

// PDF.js no corre en jsdom.
vi.mock("@/components/ui/pdf-loader", () => ({ loadPdf: () => new Promise(() => {}) }));

// ---------- XMLHttpRequest controlable (la carga usa XHR para el progreso) ----------

class FakeXHR {
  static instances: FakeXHR[] = [];
  url = "";
  status = 0;
  responseText = "";
  body: FormData | null = null;
  headers: Record<string, string> = {};
  responseHeaders = "";
  upload: { onprogress: ((e: ProgressEventInit) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  aborted = false;

  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  getAllResponseHeaders() {
    return this.responseHeaders;
  }
  send(body: FormData) {
    this.body = body;
    FakeXHR.instances.push(this);
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }
  respond(status: number, body?: unknown, headers = "Content-Type: application/json") {
    this.status = status;
    this.responseText = body === undefined ? "" : JSON.stringify(body);
    this.responseHeaders = headers;
    this.onload?.();
  }
}

const lastXhr = () => FakeXHR.instances.at(-1)!;

// ---------- datos ----------

const IMAGE = "image/jpeg";
const PENDING = slotFixture({ id: "s-pend", label: "Extracto bancario 1 de 3" });
const REJECTED = slotFixture({
  id: "s-rej",
  label: "Desprendible de nómina 2 de 3",
  status: "REJECTED",
  public_status: "TO_FIX",
  public_status_label: "Corrígelo",
  validity_days: 30,
  current_file: {
    id: "f-rej",
    version_number: 2,
    status: "REJECTED",
    status_label: "Rechazado",
    client_filename: "nomina-agosto.jpg",
    document_date: null,
    expires_at: null,
    mime_type: IMAGE,
    size_bytes: 300_000,
    rejection: null,
    created_at: "2026-11-15T10:00:00Z",
  },
  rejection: {
    reason: { code: "BLURRY", label: "Ilegible" },
    buyer_comment: "La foto está borrosa.",
    rejected_at: "2026-11-16T10:00:00Z",
  },
});
const IN_REVIEW = slotFixture({
  id: "s-rev",
  label: "Cédula",
  status: "UPLOADED",
  public_status: "IN_REVIEW",
  public_status_label: "En revisión",
  needs_action: false,
  can_upload: false,
  participant: {
    id: CO_ID,
    role: "CO_APPLICANT",
    role_label: "Co-solicitante",
    full_name: "Daniel Mejía",
  },
  current_file: {
    id: "f-ced",
    version_number: 1,
    status: "IN_REVIEW",
    status_label: "En revisión",
    client_filename: "cedula.jpg",
    document_date: null,
    expires_at: null,
    mime_type: IMAGE,
    size_bytes: 120_000,
    rejection: null,
    created_at: "2026-11-14T10:00:00Z",
  },
});
const APP_DOC = slotFixture({
  id: "s-app",
  label: "Promesa de compraventa",
  participant: null,
  status: "APPROVED",
  public_status: "DONE",
  public_status_label: "Listo",
  needs_action: false,
  can_upload: false,
});

// Orden de la API: primero el de la solicitud, luego los de cada participante.
const SLOTS: BuyerDocumentSlot[] = [APP_DOC, IN_REVIEW, PENDING, REJECTED];

function useDocsApi(slots: BuyerDocumentSlot[] = SLOTS) {
  const state = { slotRequests: 0, downloads: [] as string[] };
  server.use(
    http.get(apiUrl("/buyer/session"), () => HttpResponse.json(sessionFixture())),
    http.get(apiUrl(`/buyer/applications/${APP_ID}/document-slots`), () => {
      state.slotRequests += 1;
      return slotsPage(slots);
    }),
    http.get(apiUrl(`/buyer/applications/${APP_ID}`), () =>
      HttpResponse.json(detailFixture(), { headers: { ETag: '"9"' } }),
    ),
    http.get(apiUrl("/buyer/document-slots/s-rej/versions"), () =>
      HttpResponse.json({
        items: [
          {
            id: "f-rej",
            version_number: 2,
            status: "REJECTED",
            client_filename: "nomina-agosto.jpg",
            document_date: null,
            expires_at: null,
            mime_type: IMAGE,
            size_bytes: 300_000,
            rejection: {
              reason: { code: "BLURRY", label: "Ilegible" },
              buyer_comment: "La foto está borrosa.",
              rejected_at: "2026-11-16T10:00:00Z",
            },
            created_at: "2026-11-15T10:00:00Z",
            is_current: true,
          },
          {
            id: "f-old",
            version_number: 1,
            status: "REJECTED",
            client_filename: "nomina-vieja.jpg",
            document_date: null,
            expires_at: null,
            mime_type: IMAGE,
            size_bytes: 200_000,
            rejection: null,
            created_at: "2026-11-10T10:00:00Z",
            is_current: false,
          },
        ],
        page: 1,
        page_size: 100,
        total: 2,
        next: null,
        previous: null,
      }),
    ),
    http.get(apiUrl("/buyer/document-files/:id/download"), ({ params }) => {
      state.downloads.push(String(params.id));
      return HttpResponse.json({
        url: `https://storage.test/${String(params.id)}`,
        expires_at: "2026-11-17T16:05:00Z",
      });
    }),
  );
  return state;
}

/** Sin animaciones: en jsdom no terminan, y el foco y el cierre de la hoja dependen de ellas. */
function renderDocs() {
  return renderWithProviders(
    <ThemeProvider initialMode="light" hasCookie>
      <ConfigProvider theme={{ token: { motion: false } }}>
        <PortalGuard>
          <BuyerDocumentsScreen />
        </PortalGuard>
      </ConfigProvider>
    </ThemeProvider>,
  );
}

const card = (label: string) =>
  screen.getByRole("heading", { name: label, level: 3 }).closest("article")!;

async function openSheet(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(
    await screen.findByRole("button", { name: `Reemplazar ${label} · Sofía Herrera` }),
  );
  return screen.findByRole("dialog", { name: label });
}

function fileInput(dialog: HTMLElement): HTMLInputElement {
  const input = dialog.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("sin input de archivo");
  return input;
}

const jpg = (size = 1000, name = "nomina-nueva.jpg") =>
  new File([new Uint8Array(size)], name, { type: IMAGE });

beforeEach(() => {
  FakeXHR.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});

describe("/portal/documentos", { timeout: 20_000 }, () => {
  it("encabezado, resumen y barra con la métrica del inicio", async () => {
    useDocsApi();
    renderDocs();
    expect(await screen.findByRole("heading", { name: "Tus documentos" })).toBeInTheDocument();
    expect(
      await screen.findByText("Te faltan 2 documentos. Tu asesor revisa los demás."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "10 de 16 documentos listos" })).toBeVisible();
  });

  it("pestañas dinámicas: una por estado presente, en el orden de la lista y con su número", async () => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const tablist = await screen.findByRole("tablist", { name: "Filtrar documentos por estado" });
    const tabs = within(tablist).getAllByRole("tab");
    // Primero los que necesitan acción (Te falta, Corrígelo), después el orden de la API.
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Todos 4",
      "Te falta 1",
      "Corrígelo 1",
      "Listo 1",
      "En revisión 1",
    ]);

    await user.click(within(tablist).getByRole("tab", { name: /^Corrígelo/ }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(card("Desprendible de nómina 2 de 3")).toBeInTheDocument();
  });

  it("agrupa por participante; cada documento con estado, archivo, rechazo y acciones", async () => {
    useDocsApi();
    renderDocs();
    const groups = await screen.findAllByRole("heading", { level: 2 });
    expect(groups.map((h) => h.textContent)).toEqual([
      "Sofía Herrera · Titular",
      "Documentos de la solicitud",
      "Daniel Mejía · Co-solicitante",
    ]);

    const rejected = card("Desprendible de nómina 2 de 3");
    expect(rejected).toHaveTextContent("Últimos 3 meses.");
    expect(within(rejected).getByText("Corrígelo")).toHaveAttribute("data-tone", "danger");
    expect(rejected).toHaveTextContent("nomina-agosto.jpg · subido el 15 nov 2026");
    expect(rejected).toHaveTextContent("IlegibleLa foto está borrosa.");
    expect(within(rejected).getByRole("button", { name: /^Reemplazar/ })).toBeInTheDocument();
    expect(
      within(rejected).getByRole("button", { name: "Ver nomina-agosto.jpg" }),
    ).toBeInTheDocument();

    expect(
      within(card("Extracto bancario 1 de 3")).getByRole("button", { name: /^Subir/ }),
    ).toBeInTheDocument();

    // Sin `can_upload`, sin botón de carga.
    const review = card("Cédula");
    expect(within(review).queryByRole("button", { name: /Subir|Reemplazar/ })).toBeNull();
    expect(within(review).getByRole("button", { name: "Ver cedula.jpg" })).toBeInTheDocument();
  });

  it("visor: pide la URL de descarga y abre la imagen", async () => {
    const api = useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    await user.click(await screen.findByRole("button", { name: "Ver cedula.jpg" }));
    expect(await screen.findByRole("img", { name: "Vista de cedula.jpg" })).toHaveAttribute(
      "src",
      "https://storage.test/f-ced",
    );
    expect(api.downloads).toEqual(["f-ced"]);
  });

  it("visor: un 409 de la descarga se muestra junto al documento", async () => {
    useDocsApi();
    server.use(
      http.get(apiUrl("/buyer/document-files/:id/download"), () =>
        apiError(409, "FILE_NOT_CLEAN", "El archivo todavía se está analizando."),
      ),
    );
    const user = userEvent.setup();
    renderDocs();
    await user.click(await screen.findByRole("button", { name: "Ver cedula.jpg" }));
    expect(
      await within(card("Cédula")).findByText("El archivo todavía se está analizando."),
    ).toBeInTheDocument();
  });

  it("versiones: cada una con su motivo, la vigente marcada y 'Ver'", async () => {
    const api = useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const rejected = await waitFor(() => card("Desprendible de nómina 2 de 3"));
    const toggle = within(rejected).getByRole("button", { name: "Versiones" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const items = await within(rejected).findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Versión 2 · Vigente");
    expect(items[0]).toHaveTextContent("Motivo del rechazo: Ilegible: La foto está borrosa.");
    expect(items[1]).toHaveTextContent("Versión 1nomina-vieja.jpg · 10 nov 2026");

    await user.click(within(items[1]!).getByRole("button", { name: "Ver nomina-vieja.jpg" }));
    expect(await screen.findByRole("img", { name: "Vista de nomina-vieja.jpg" })).toHaveAttribute(
      "src",
      "https://storage.test/f-old",
    );
    expect(api.downloads).toEqual(["f-old"]);
  });

  it("sin documentos pedidos: un mensaje en lugar de la lista", async () => {
    useDocsApi([]);
    renderDocs();
    expect(
      await screen.findByText("Tu asesor todavía no te ha pedido documentos."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No te falta ningún documento. Tu asesor revisa los demás."),
    ).toBeInTheDocument();
  });
});

describe("hoja de carga", { timeout: 20_000 }, () => {
  it("título, titular, tipos y tamaño legibles, ayuda y fecha del documento", async () => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");
    expect(dialog).toHaveTextContent("Sofía Herrera · Titular");
    expect(dialog).toHaveTextContent("PDF, JPG o PNG, de hasta 10 MB.");
    expect(dialog).toHaveTextContent("Últimos 3 meses.");
    // `validity_days`: fecha opcional.
    expect(within(dialog).getByLabelText(/Fecha del documento/)).toHaveAttribute("type", "date");
  });

  it("validación local de tipo y tamaño, sin enviar", async () => {
    useDocsApi();
    const user = userEvent.setup({ applyAccept: false });
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");

    await user.upload(
      fileInput(dialog),
      new File(["x"], "carta.docx", { type: "application/msword" }),
    );
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este tipo de archivo no se acepta. Sube un archivo PDF, JPG o PNG.",
    );
    await user.upload(fileInput(dialog), jpg(11 * 1024 * 1024));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "El archivo pesa 11 MB y el máximo es 10 MB.",
    );
    expect(FakeXHR.instances).toHaveLength(0);
  });

  it("carga con progreso y fecha; al terminar: toast, recarga y se cierra", async () => {
    const api = useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");
    await user.type(within(dialog).getByLabelText(/Fecha del documento/), "2026-11-01");
    const requestsBefore = api.slotRequests;
    await user.upload(fileInput(dialog), jpg());

    const xhr = lastXhr();
    expect(xhr.url).toBe("http://localhost:3000/api/v1/buyer/document-slots/s-rej/uploads");
    expect(xhr.body?.get("document_date")).toBe("2026-11-01");
    expect((xhr.body?.get("file") as File).name).toBe("nomina-nueva.jpg");
    act(() => xhr.progress(50, 100));
    expect(
      within(dialog).getByRole("progressbar", { name: "Subiendo nomina-nueva.jpg" }),
    ).toHaveAttribute("aria-valuenow", "50");

    act(() => xhr.respond(201, REJECTED));
    expect(await screen.findByText("Documento subido")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(api.slotRequests).toBeGreaterThan(requestsBefore));
  });

  it("cancelar una carga en curso vuelve a dejar elegir el archivo", async () => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");
    await user.upload(fileInput(dialog), jpg());
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(lastXhr().aborted).toBe(true);
    expect(await within(dialog).findByText("Reemplazar documento")).toBeInTheDocument();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    [422, "UNSUPPORTED_FILE_TYPE", "El contenido del archivo no es un PDF ni una imagen."],
    [422, "FILE_TOO_LARGE", "El archivo supera el tamaño máximo."],
    [413, "PAYLOAD_TOO_LARGE", "La carga es demasiado grande."],
    [409, "DOCUMENT_LOCKED", "Este documento ya no admite cambios."],
    [409, "DOCUMENT_NOT_REJECTED", "Solo puedes reemplazar documentos rechazados."],
    [503, "SERVICE_UNAVAILABLE", "El almacenamiento no está disponible."],
  ])("error de la API %i %s: su mensaje en la hoja", async (status, code, message) => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");
    await user.upload(fileInput(dialog), jpg());
    act(() =>
      lastXhr().respond(
        status,
        { code, message, details: [], request_id: "r" },
        "Content-Type: application/json\r\nX-Request-ID: r",
      ),
    );
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
  });

  it("un 413 del servidor web, sin el formato de la API, tiene su propio mensaje", async () => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const dialog = await openSheet(user, "Desprendible de nómina 2 de 3");
    await user.upload(fileInput(dialog), jpg());
    act(() => lastXhr().respond(413, undefined, "Content-Type: text/html\r\nX-Request-ID: r"));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "El archivo es demasiado grande para subirlo.",
    );
  });

  it("teclado: el foco entra a la hoja, Escape la cierra y vuelve al botón", async () => {
    useDocsApi();
    const user = userEvent.setup();
    renderDocs();
    const opener = await screen.findByRole("button", {
      name: "Reemplazar Desprendible de nómina 2 de 3 · Sofía Herrera",
    });
    opener.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Desprendible de nómina 2 de 3" });
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
  });
});

describe("formato de documentos", () => {
  it("tipos, requisitos, visor, orden, pestañas y resumen", () => {
    expect(typeLabel("image/jpeg")).toBe("JPG");
    expect(listLabels(["PDF"])).toBe("PDF");
    expect(
      requirementsText({
        allowed_mime_types: ["application/pdf"],
        max_size_bytes: 5 * 1024 * 1024,
      }),
    ).toBe("PDF, de hasta 5 MB.");
    expect(requirementsText({ allowed_mime_types: [], max_size_bytes: 1024 * 1024 })).toBe(
      "De hasta 1 MB.",
    );
    expect(viewerKind("image/png")).toBe("image");
    expect(viewerKind("application/pdf")).toBe("pdf");
    expect(sortSlots(SLOTS).map((s) => s.id)).toEqual(["s-pend", "s-rej", "s-app", "s-rev"]);
    expect(statusTabs(sortSlots(SLOTS)).map((t) => t.key)).toEqual([
      "TO_UPLOAD",
      "TO_FIX",
      "DONE",
      "IN_REVIEW",
    ]);
    expect(summaryText(1)).toBe("Te falta 1 documento. Tu asesor revisa los demás.");
    // Dos participantes pueden tener la misma etiqueta: el nombre accesible lleva el titular.
    expect(slotName(PENDING)).toBe("Extracto bancario 1 de 3 · Sofía Herrera");
    expect(slotName(APP_DOC)).toBe("Promesa de compraventa");
  });
});
