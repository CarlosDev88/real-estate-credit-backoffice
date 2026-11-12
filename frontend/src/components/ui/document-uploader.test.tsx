import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DocumentUploader,
  validateFile,
  type UploadContext,
} from "@/components/ui/document-uploader";
import { ApiError } from "@/lib/api/errors";

const ACCEPT = ["application/pdf", "image/jpeg", "image/png"] as const;
const MB = 1024 * 1024;

const pdf = (size = 1000, name = "extracto.pdf") =>
  new File([new Uint8Array(size)], name, { type: "application/pdf" });

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("sin input de archivo");
  return input;
}

describe("validateFile", () => {
  it("acepta tipo y tamaño permitidos", () => {
    expect(validateFile(pdf(), ACCEPT, 10 * MB)).toBeNull();
  });

  it("rechaza el tipo con los formatos permitidos", () => {
    const doc = new File(["x"], "carta.docx", { type: "application/msword" });
    expect(validateFile(doc, ACCEPT)).toBe(
      "Este tipo de archivo no se acepta. Sube un archivo PDF, JPG o PNG.",
    );
  });

  it("sin tipo informado, mira la extensión", () => {
    expect(validateFile(new File(["x"], "foto.JPEG"), ACCEPT)).toBeNull();
    expect(validateFile(new File(["x"], "foto.heic"), ACCEPT)).not.toBeNull();
  });

  it("rechaza el tamaño con el peso y el máximo", () => {
    expect(validateFile(pdf(12 * MB), ACCEPT, 10 * MB)).toBe(
      "El archivo pesa 12 MB y el máximo es 10 MB.",
    );
  });

  it("sin restricciones de la API no valida (lo hace el backend)", () => {
    expect(validateFile(new File(["x"], "cualquier.bin"), undefined, undefined)).toBeNull();
  });
});

describe("DocumentUploader en web", () => {
  it("muestra el formato y el máximo, y sube el archivo con progreso", async () => {
    let ctx: UploadContext | null = null;
    let finish: () => void = () => {};
    const onUpload = vi.fn(
      (_file: File, context: UploadContext) =>
        new Promise<void>((resolve) => {
          ctx = context;
          finish = resolve;
        }),
    );
    const { container } = render(
      <DocumentUploader onUpload={onUpload} accept={ACCEPT} maxBytes={10 * MB} />,
    );
    expect(screen.getByText("PDF, JPG o PNG · máximo 10 MB")).toBeInTheDocument();
    expect(screen.getByText("Subir documento")).toBeInTheDocument();

    await userEvent.upload(fileInput(container), pdf());
    expect(onUpload).toHaveBeenCalledOnce();
    expect(onUpload.mock.calls[0]?.[0].name).toBe("extracto.pdf");

    act(() => ctx?.onProgress(45));
    expect(screen.getByRole("progressbar", { name: "Subiendo extracto.pdf" })).toHaveAttribute(
      "aria-valuenow",
      "45",
    );
    expect(screen.getByText("Subiendo… 45 %")).toBeInTheDocument();
    act(() => ctx?.onProgress(100));
    expect(screen.getByText("Procesando el archivo…")).toBeInTheDocument();

    await act(async () => finish());
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("Subir documento")).toBeInTheDocument();
  });

  it("no envía un archivo inválido y explica por qué", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup({ applyAccept: false });
    const { container } = render(
      <DocumentUploader onUpload={onUpload} accept={ACCEPT} maxBytes={MB} />,
    );
    await user.upload(fileInput(container), pdf(2 * MB));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "El archivo pesa 2 MB y el máximo es 1 MB.",
    );
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("un error de la API se muestra y se puede reintentar", async () => {
    const onUpload = vi
      .fn<(file: File, context: UploadContext) => Promise<void>>()
      .mockRejectedValueOnce(
        new ApiError(503, "SERVICE_UNAVAILABLE", "El almacenamiento no respondió."),
      )
      .mockResolvedValueOnce(undefined);
    const { container } = render(<DocumentUploader onUpload={onUpload} replace />);
    expect(screen.getByText("Reemplazar documento")).toBeInTheDocument();

    await userEvent.upload(fileInput(container), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("El almacenamiento no respondió.");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onUpload).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("Cancelar aborta la carga y vuelve al inicio sin error", async () => {
    let signal: AbortSignal | null = null;
    const onUpload = vi.fn(
      (_file: File, context: UploadContext) =>
        new Promise<void>((_resolve, reject) => {
          signal = context.signal;
          context.signal.addEventListener("abort", () =>
            reject(new DOMException("Cancelado", "AbortError")),
          );
        }),
    );
    const { container } = render(<DocumentUploader onUpload={onUpload} />);
    await userEvent.upload(fileInput(container), pdf());
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(signal).not.toBeNull();
    expect(signal!.aborted).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Subir documento")).toBeInTheDocument();
  });
});

describe("DocumentUploader en móvil", () => {
  afterEach(() => vi.restoreAllMocks());

  it('ofrece "Tomar foto" y "Elegir archivo"', async () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query === "(max-width: 720px)",
          media: query,
          addEventListener: () => {},
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    );
    const onUpload = vi.fn(() => Promise.resolve());
    render(<DocumentUploader onUpload={onUpload} accept={ACCEPT} />);

    expect(screen.getByRole("button", { name: "Tomar foto" })).toBeInTheDocument();
    const camera = screen.getByLabelText("Tomar foto", { selector: "input" });
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera).toHaveAttribute("accept", "image/*");

    const chooser = screen.getByLabelText("Elegir archivo", { selector: "input" });
    await userEvent.upload(chooser, pdf());
    expect(onUpload).toHaveBeenCalledOnce();
  });

  it('sin imágenes permitidas no muestra "Tomar foto"', () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: true,
          media: query,
          addEventListener: () => {},
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    );
    render(<DocumentUploader onUpload={vi.fn()} accept={["application/pdf"]} />);
    expect(screen.queryByRole("button", { name: "Tomar foto" })).not.toBeInTheDocument();
  });
});
