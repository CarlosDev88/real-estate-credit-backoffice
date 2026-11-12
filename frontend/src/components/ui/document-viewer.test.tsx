import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentViewer } from "@/components/ui/document-viewer";
import type { PdfDocumentProxy } from "@/components/ui/pdf-loader";

// Función común en lugar de vi.fn: el espía de Vitest, al registrar una promesa
// rechazada, deja otra sin manejar y la reporta como error de la prueba.
const pdf = vi.hoisted(() => ({
  calls: [] as string[],
  impl: (() => new Promise(() => {})) as (url: string) => Promise<unknown>,
}));
vi.mock("@/components/ui/pdf-loader", () => ({
  loadPdf: (url: string) => {
    pdf.calls.push(url);
    return pdf.impl(url);
  },
}));

/** Como en PDF.js, `cancel` usa `this`: llamarla desligada de la tarea falla. */
class FakeRenderTask {
  promise = Promise.resolve();
  private internal = { cancelled: false };
  cancel() {
    this.internal.cancelled = true;
  }
}

function fakeDoc(numPages: number): PdfDocumentProxy & { renders: unknown[] } {
  const renders: unknown[] = [];
  return {
    numPages,
    renders,
    destroy: vi.fn(() => Promise.resolve()),
    getPage: vi.fn(() =>
      Promise.resolve({
        getViewport: ({ scale, rotation = 0 }: { scale: number; rotation?: number }) =>
          rotation % 180 === 0
            ? { width: 600 * scale, height: 800 * scale }
            : { width: 800 * scale, height: 600 * scale },
        render: (params: unknown) => {
          renders.push(params);
          return new FakeRenderTask();
        },
      }),
    ),
  };
}

const PDF = {
  name: "certificado-laboral.pdf",
  kind: "pdf" as const,
  url: "/api/v1/storage/objects/t1",
  size: "320 KB",
};

describe("DocumentViewer", () => {
  beforeEach(() => {
    pdf.calls = [];
  });

  it("dibuja cada página del PDF y muestra sus datos", async () => {
    const doc = fakeDoc(3);
    pdf.impl = () => Promise.resolve(doc);
    render(<DocumentViewer open file={PDF} onClose={vi.fn()} note="Enlace firmado" />);

    expect(screen.getByText("Cargando el documento…")).toHaveAttribute("role", "status");
    await waitFor(() => expect(screen.getAllByRole("img", { name: /^Página/ })).toHaveLength(3));
    expect(pdf.calls).toEqual([PDF.url]);
    expect(screen.getByRole("dialog")).toHaveAccessibleName(PDF.name);
    expect(screen.getByText("PDF · 3 páginas · 320 KB")).toBeInTheDocument();
    expect(screen.getByText("Enlace firmado")).toBeInTheDocument();
    await waitFor(() => expect(doc.renders).toHaveLength(3));
  });

  it("páginas, zoom, giro y descarga", async () => {
    pdf.impl = () => Promise.resolve(fakeDoc(2));
    const user = userEvent.setup();
    render(<DocumentViewer open file={PDF} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole("img", { name: /^Página/ })).toHaveLength(2));

    const prev = screen.getByRole("button", { name: "Página anterior" });
    const next = screen.getByRole("button", { name: "Página siguiente" });
    expect(prev).toBeDisabled();
    await user.click(next);
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
    expect(next).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Acercar" }));
    expect(screen.getByRole("button", { name: /Ajustar al ancho/ })).toHaveTextContent(/125\s%/);
    await user.click(screen.getByRole("button", { name: /Ajustar al ancho/ }));
    expect(screen.getByRole("button", { name: /Ajustar al ancho/ })).toHaveTextContent(/100\s%/);

    const download = screen.getByRole("link", { name: "Descargar" });
    expect(download).toHaveAttribute("href", PDF.url);
    expect(download).toHaveAttribute("download", PDF.name);
    await user.click(screen.getByRole("button", { name: "Girar" }));
  });

  it("teclado: flechas cambian de página y + / − el zoom", async () => {
    pdf.impl = () => Promise.resolve(fakeDoc(3));
    const user = userEvent.setup();
    render(<DocumentViewer open file={PDF} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole("img", { name: /^Página/ })).toHaveLength(3));

    await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}");
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    await user.keyboard("+");
    expect(screen.getByRole("button", { name: /Ajustar al ancho/ })).toHaveTextContent(/125\s%/);
    await user.keyboard("-");
    expect(screen.getByRole("button", { name: /Ajustar al ancho/ })).toHaveTextContent(/100\s%/);
  });

  it("si el PDF no carga, ofrece descargarlo", async () => {
    pdf.impl = () => Promise.reject(new Error("CORS"));
    render(<DocumentViewer open file={PDF} onClose={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos mostrar el documento. Puedes descargarlo.",
    );
  });

  it("muestra las imágenes directo, sin PDF.js", () => {
    render(
      <DocumentViewer
        open
        file={{ name: "cedula.jpg", kind: "image", url: "blob:local" }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("img", { name: "Vista de cedula.jpg" })).toHaveAttribute(
      "src",
      "blob:local",
    );
    expect(screen.getByText("Imagen")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Páginas" })).not.toBeInTheDocument();
    expect(pdf.calls).toEqual([]);
  });

  it("se cierra con el botón y con Escape", async () => {
    pdf.impl = () => Promise.resolve(fakeDoc(1));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<DocumentViewer open file={PDF} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Cerrar visor" }));
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
