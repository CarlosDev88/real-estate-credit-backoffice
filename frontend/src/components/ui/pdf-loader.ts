// Carga de PDF.js aparte del visor: solo en el cliente y fácil de sustituir en pruebas.

export interface PdfRenderTask {
  promise: Promise<void>;
  cancel: () => void;
}

export interface PdfPageProxy {
  getViewport: (params: { scale: number; rotation?: number }) => { width: number; height: number };
  render: (params: {
    canvas: HTMLCanvasElement;
    viewport: { width: number; height: number };
  }) => PdfRenderTask;
}

export interface PdfDocumentProxy {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageProxy>;
  /** Libera el documento y su conexión con el worker. */
  destroy: () => Promise<void>;
}

let worker: Worker | null = null;

/** Abre el PDF de la URL (prefirmada o local). El worker se crea una sola vez. */
export async function loadPdf(url: string): Promise<PdfDocumentProxy> {
  const pdfjs = await import("pdfjs-dist");
  if (!worker) {
    worker = new Worker(new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url), {
      type: "module",
    });
    pdfjs.GlobalWorkerOptions.workerPort = worker;
  }
  const task = pdfjs.getDocument({ url, disableWorkerRendering: true });
  const doc = await task.promise;
  // En PDF.js 6 el documento se cierra desde la tarea de carga.
  return {
    numPages: doc.numPages,
    getPage: (n) => doc.getPage(n) as unknown as Promise<PdfPageProxy>,
    destroy: () => task.destroy(),
  };
}
