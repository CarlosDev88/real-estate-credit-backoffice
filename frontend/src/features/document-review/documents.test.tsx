import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ALL_PERMISSIONS,
  APP_ID,
  useWorkspaceApi,
} from "@/features/applications/workspace.fixtures";
import { WorkspaceScreen } from "@/features/applications/workspace-screen";
import { useDocumentsApi } from "@/features/document-review/documents.fixtures";
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

// PDF.js no corre en jsdom: se registra la URL que recibe el visor.
const pdf = vi.hoisted(() => ({ calls: [] as string[] }));
vi.mock("@/components/ui/pdf-loader", () => ({
  loadPdf: (url: string) => {
    pdf.calls.push(url);
    return new Promise(() => {});
  },
}));

const DOCS = "/solicitudes/app-1?tab=documentos";
const REVIEWER = [...ALL_PERMISSIONS, "documents.review", "documents.waive", "documents.download"];

async function renderDocuments(search = DOCS) {
  window.history.replaceState(null, "", search);
  const user = userEvent.setup();
  render(
    <App>
      <QueryProvider>
        <WorkspaceScreen id={APP_ID} />
      </QueryProvider>
    </App>,
  );
  await screen.findByRole("heading", { name: /Sofía Herrera/, level: 3 });
  return user;
}

const row = (label: string) => screen.getByText(label, { selector: "div" }).closest("li")!;
const query = () => new URLSearchParams(window.location.search);

/** Panel de revisión: su nombre accesible es el título (participante y documento). */
const getDrawer = (label: string) =>
  screen.getByRole("heading", { name: label, level: 2 }).closest<HTMLElement>("[role=dialog]")!;
const findDrawer = async (label: string) => {
  await screen.findByRole("heading", { name: label, level: 2 });
  return getDrawer(label);
};

beforeEach(() => {
  pdf.calls.length = 0;
  nav.push.mockClear();
});

describe("pestaña Documentos", { timeout: 20_000 }, () => {
  it("agrupa por participante y deja al final los de la solicitud, sin los retirados", async () => {
    useWorkspaceApi();
    useDocumentsApi();
    await renderDocuments();

    const groups = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    await waitFor(() => expect(groups[0]).toContain("Sofía Herrera"));
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "SHSofía Herrera· Empleada",
      "DMDaniel Mejía",
      "Solicitud· Inmueble y trámite",
    ]);
    expect(screen.queryByText("Documento retirado")).toBeNull();

    // Estado con la etiqueta del catálogo y su tono.
    expect(within(row("Documento de identidad")).getByText("Aprobado")).toHaveAttribute(
      "data-tone",
      "success",
    );
    expect(within(row("Certificado de tradición")).getByText("Exonerado")).toBeInTheDocument();
    expect(row("Certificado de tradición")).toHaveTextContent("Exonerado: No aplica al inmueble");
    expect(row("Extracto bancario 1 de 3")).toHaveTextContent("Sin archivo");

    // Archivo vigente: nombre, tamaño y regla de vigencia.
    await waitFor(() =>
      expect(row("Certificado laboral")).toHaveTextContent(
        "laboral.pdf · 412 KB · vigencia de 30 días · vence 2 dic 2026",
      ),
    );
    // Rechazado: el mensaje que ve el comprador.
    await waitFor(() =>
      expect(row("Desprendible de nómina 2 de 3")).toHaveTextContent(
        "Mensaje al comprador: La foto está borrosa.",
      ),
    );
  });

  it("acciones por estado y permiso; análisis pendiente o fallido en línea", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi();
    await renderDocuments();

    const names = (label: string) =>
      within(row(label))
        .queryAllByRole("button")
        .map((b) => b.textContent?.split(" ")[0]);
    expect(names("Certificado laboral")).toEqual(["Ver", "Revisar"]);
    expect(names("Documento de identidad")).toEqual(["Ver", "Revisar"]);
    expect(names("Extracto bancario 1 de 3")).toEqual(["Exonerar"]);
    expect(names("Certificado de tradición")).toEqual(["Reabrir"]);

    expect(row("Cédula del co-solicitante")).toHaveTextContent("Analizando el archivo…");
    expect(names("Cédula del co-solicitante")).toEqual([]);
    expect(row("Soporte de ingresos")).toHaveTextContent(
      "El archivo no pasó el análisis de seguridad",
    );
  });

  it("sin permisos de revisión, exoneración ni descarga no hay acciones", async () => {
    useWorkspaceApi({ permissions: ALL_PERMISSIONS });
    useDocumentsApi();
    await renderDocuments();
    expect(within(row("Certificado laboral")).queryAllByRole("button")).toHaveLength(0);
    expect(within(row("Extracto bancario 1 de 3")).queryAllByRole("button")).toHaveLength(0);
  });
});

describe("revisión de documentos", { timeout: 20_000 }, () => {
  it("aprueba con la fecha del documento y pasa al siguiente por revisar", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments();

    await user.click(within(row("Certificado laboral")).getByRole("button", { name: /Revisar/ }));
    expect(query().get("slot")).toBe("laboral");
    const drawer = await findDrawer("Certificado laboral");
    expect(within(drawer).getByText("Sofía Herrera")).toBeInTheDocument();
    await within(drawer).findByText("412 KB");
    expect(drawer).toHaveTextContent("por el comprador");
    expect(within(drawer).getByText("Sin amenazas")).toHaveAttribute("data-tone", "success");
    expect(within(drawer).getByLabelText("Fecha del documento")).toHaveValue("2026-11-02");

    await user.click(within(drawer).getByRole("button", { name: "Aprobar documento" }));
    await waitFor(() => expect(api.reviews).toHaveLength(1));
    expect(api.reviews[0]).toEqual({
      slotId: "laboral",
      body: { decision: "APPROVED", document_file_id: "f-laboral", document_date: "2026-11-02" },
    });
    expect(await screen.findByText("Certificado laboral: aprobado")).toBeInTheDocument();
    // El siguiente cargado con análisis limpio, en el orden de la pantalla.
    await waitFor(() => expect(query().get("slot")).toBe("promesa"));
    expect(await findDrawer("Promesa de compraventa")).toBeInTheDocument();
  });

  it("rechazar exige motivo y mensaje; la nota interna es opcional", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=promesa");
    const drawer = await findDrawer("Promesa de compraventa");
    await within(drawer).findByText("412 KB");

    // El input del radio de Ant Design no recibe el puntero: se hace clic en su etiqueta.
    await user.click(within(drawer).getByRole("radio", { name: "Rechazar" }).closest("label")!);
    expect(within(drawer).getByText(/el comprador no la ve/)).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Rechazar documento" }));
    expect(await within(drawer).findByText("Elige el motivo.")).toBeInTheDocument();
    expect(
      within(drawer).getByText("Explícale al comprador qué debe corregir."),
    ).toBeInTheDocument();
    expect(api.reviews).toHaveLength(0);

    await user.click(within(drawer).getByRole("combobox"));
    await user.click(await screen.findByTitle("Ilegible"));
    await user.type(within(drawer).getByLabelText("Mensaje para el comprador"), "Súbela nítida.");
    await user.type(within(drawer).getByLabelText(/Nota interna/), "Se ve cortada.");
    await user.click(within(drawer).getByRole("button", { name: /Rechazar documento/ }));

    await waitFor(() =>
      expect(api.reviews[0]?.body).toEqual({
        decision: "REJECTED",
        document_file_id: "f-promesa",
        reason_code: "ILLEGIBLE",
        buyer_comment: "Súbela nítida.",
        internal_comment: "Se ve cortada.",
      }),
    );
    expect(await screen.findByText("Promesa de compraventa: rechazado")).toBeInTheDocument();
  });

  it("un error de la API con campo va al campo del panel", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi({
      reviewError: {
        status: 400,
        body: {
          code: "VALIDATION_ERROR",
          message: "Revisa los datos.",
          details: [{ field: "document_date", code: "future", message: "No puede ser futura." }],
          request_id: "r",
        },
      },
    });
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=laboral");
    const drawer = await findDrawer("Certificado laboral");
    await within(drawer).findByText("412 KB");
    await user.click(within(drawer).getByRole("button", { name: "Aprobar documento" }));
    expect(await within(drawer).findByText("No puede ser futura.")).toBeInTheDocument();
  });

  it("'Siguiente' pasa al próximo por revisar sin decidir", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=laboral");
    const drawer = await findDrawer("Certificado laboral");
    await user.click(within(drawer).getByRole("button", { name: "Siguiente" }));
    expect(query().get("slot")).toBe("promesa");
    expect(api.reviews).toHaveLength(0);
  });

  it("exonera con motivo obligatorio", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments();
    await user.click(
      within(row("Extracto bancario 1 de 3")).getByRole("button", { name: /Exonerar/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: /Exonerar · Extracto bancario/ });
    await user.click(within(dialog).getByRole("button", { name: "Exonerar" }));
    expect(await within(dialog).findByText("Elige el motivo.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox"));
    await user.click(await screen.findByTitle("No aplica al inmueble"));
    await user.click(within(dialog).getByRole("button", { name: /Exonerar$/ }));
    await waitFor(() =>
      expect(api.reviews[0]).toEqual({
        slotId: "extracto",
        body: { decision: "WAIVED", reason_code: "NOT_APPLICABLE" },
      }),
    );
    expect(await screen.findByText("Extracto bancario 1 de 3: exonerado")).toBeInTheDocument();
  });

  it("reabre un exonerado con nota interna obligatoria", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments();
    await user.click(
      within(row("Certificado de tradición")).getByRole("button", { name: /Reabrir/ }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /Reabrir · Certificado de tradición/,
    });
    await user.click(within(dialog).getByRole("button", { name: "Reabrir" }));
    expect(await within(dialog).findByText("Explica por qué se reabre.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Nota interna"), "Sí aplica: inmueble usado.");
    await user.click(within(dialog).getByRole("button", { name: /Reabrir$/ }));
    await waitFor(() =>
      expect(api.reviews[0]).toEqual({
        slotId: "tradicion",
        body: { decision: "REOPENED", internal_comment: "Sí aplica: inmueble usado." },
      }),
    );
  });

  it("el visor pide una URL nueva cada vez que se abre", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments();
    const view = () =>
      user.click(within(row("Documento de identidad")).getByRole("button", { name: /Ver/ }));

    await view();
    expect(await screen.findByRole("img", { name: "Vista de cedula.pdf" })).toHaveAttribute(
      "src",
      "http://localhost:3000/api/v1/storage/objects/f-cedula-1",
    );
    await user.click(screen.getByRole("button", { name: "Cerrar visor" }));
    await view();
    await waitFor(() => expect(api.downloads).toEqual(["f-cedula", "f-cedula"]));
    expect(await screen.findByRole("img", { name: "Vista de cedula.pdf" })).toHaveAttribute(
      "src",
      "http://localhost:3000/api/v1/storage/objects/f-cedula-2",
    );
  });

  it("'Abrir en el visor' del panel carga el PDF con la URL pedida", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi();
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=laboral");
    const drawer = await findDrawer("Certificado laboral");
    await within(drawer).findByText("412 KB");
    await user.click(within(drawer).getByRole("button", { name: "Abrir en el visor" }));
    await waitFor(() =>
      expect(pdf.calls).toEqual(["http://localhost:3000/api/v1/storage/objects/f-laboral-1"]),
    );
  });

  it("503 en la descarga: mensaje en línea en la fila", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi({ download: { status: 503 } });
    const user = await renderDocuments();
    await user.click(within(row("Documento de identidad")).getByRole("button", { name: /Ver/ }));
    expect(
      await within(row("Documento de identidad")).findByText(
        "El almacenamiento no está disponible.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Vista de/ })).toBeNull();
  });

  it("409 en la descarga: mensaje en línea en el panel", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi({
      download: { status: 409, code: "FILE_NOT_CLEAN", message: "El archivo no está disponible." },
    });
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=laboral");
    const drawer = await findDrawer("Certificado laboral");
    await within(drawer).findByText("412 KB");
    await user.click(within(drawer).getByRole("button", { name: "Abrir en el visor" }));
    expect(await within(drawer).findByText("El archivo no está disponible.")).toBeInTheDocument();
  });

  it("versiones anteriores en una lista plegable, con 'Ver'", async () => {
    useWorkspaceApi({ permissions: REVIEWER });
    const api = useDocumentsApi();
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=laboral");
    const drawer = await findDrawer("Certificado laboral");
    await user.click(within(drawer).getByRole("button", { name: "Versiones anteriores" }));
    expect(await within(drawer).findByText("Versión 1")).toBeInTheDocument();
    expect(drawer).toHaveTextContent("Mensaje al comprador: Estaba vencido.");
    await user.click(within(drawer).getByRole("button", { name: "Ver versión 1" }));
    await waitFor(() => expect(api.downloads).toEqual(["old-laboral"]));
  });

  it("teclado: el panel atrapa el foco y Escape lo cierra", async () => {
    // El bloqueo de foco de Ant Design solo considera elementos visibles (`offsetParent`),
    // que jsdom no calcula: se simula que todo está a la vista.
    vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockReturnValue(document.body);
    useWorkspaceApi({ permissions: REVIEWER });
    useDocumentsApi();
    const user = await renderDocuments("/solicitudes/app-1?tab=documentos&slot=promesa");
    const drawer = await findDrawer("Promesa de compraventa");
    await within(drawer).findByText("412 KB");
    const root = drawer.closest(".ant-drawer")!;
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { level: 2, name: "Promesa de compraventa" }),
      ),
    );

    // Con Tab, el foco nunca cae en un control fuera del panel. Al pasar el último, jsdom lo
    // deja un momento en `body` (fin del documento) y el bloqueo lo devuelve al panel.
    let inside = 0;
    for (let i = 0; i < 20; i += 1) {
      await user.tab();
      const active = document.activeElement;
      if (active !== document.body) {
        expect(root.contains(active)).toBe(true);
        inside += 1;
      }
    }
    expect(inside).toBeGreaterThan(15);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(query().has("slot")).toBe(false));
    expect(query().get("tab")).toBe("documentos");
  });
});
