"use client";

import { darkTheme } from "@design/antd-theme";
import { Button, ConfigProvider, Modal } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { CloseIcon } from "@/components/ui/icons";
import { loadPdf, type PdfDocumentProxy, type PdfRenderTask } from "@/components/ui/pdf-loader";
import { formatPercent } from "@/lib/format";

export interface ViewerFile {
  name: string;
  kind: "pdf" | "image";
  /** URL prefirmada de la descarga (o una URL local de un archivo elegido). */
  url: string;
  /** Tamaño ya formateado ("1,2 MB"), opcional. */
  size?: string;
}

interface DocumentViewerProps {
  open: boolean;
  file: ViewerFile | null;
  onClose: () => void;
  /** Nota al pie (por ejemplo, cuándo vence el enlace de descarga). */
  note?: ReactNode;
}

const BASE_WIDTH = 640;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const STEP = 0.25;

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={16} height={16} aria-hidden="true">
      <path d={d} />
    </svg>
  );
}
const ICONS = {
  prev: "m12.6 4 1.4 1.4L9.4 10l4.6 4.6-1.4 1.4-6-6 6-6Z",
  next: "m7.4 4 6 6-6 6L6 14.6l4.6-4.6L6 5.4 7.4 4Z",
  minus: "M4 9h12v2H4V9Z",
  plus: "M9 4h2v5h5v2h-5v5H9v-5H4V9h5V4Z",
  rotate: "M10 3a7 7 0 1 1-6.6 9.3l1.9-.6A5 5 0 1 0 10 5v3L5.5 4.5 10 1v2Z",
  download: "M9 3h2v8l3-3 1.4 1.4L10 14.8 4.6 9.4 6 8l3 3V3ZM3 15h14v2H3v-2Z",
};

function stageWidth(): number {
  return Math.min(
    BASE_WIDTH,
    (typeof window === "undefined" ? BASE_WIDTH : window.innerWidth) - 32,
  );
}

/** Una página del PDF dibujada en un canvas con el zoom y el giro actuales. */
function PdfPage({
  doc,
  pageNumber,
  zoom,
  rotation,
}: {
  doc: PdfDocumentProxy;
  pageNumber: number;
  zoom: number;
  rotation: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    let task: PdfRenderTask | null = null;
    void (async () => {
      const page = await doc.getPage(pageNumber);
      const canvas = canvasRef.current;
      if (cancelled || !canvas) return;
      const base = page.getViewport({ scale: 1, rotation });
      const cssWidth = stageWidth() * zoom;
      const ratio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: (cssWidth / base.width) * ratio, rotation });
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${(viewport.height / viewport.width) * cssWidth}px`;
      task = page.render({ canvas, viewport });
      // Una tarea cancelada rechaza su promesa: no es un error.
      await task.promise.catch(() => {});
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [doc, pageNumber, zoom, rotation]);

  return (
    <canvas
      ref={canvasRef}
      data-page={pageNumber}
      aria-label={`Página ${pageNumber}`}
      role="img"
      className="rounded-[2px] bg-white shadow-[0_8px_28px_rgba(0,0,0,0.5)]"
    />
  );
}

/**
 * Visor de documentos (mockup `_viewer.html`): PDF con PDF.js e imágenes directas.
 * Zoom, páginas, girar y descargar. Siempre oscuro, con los tokens del tema oscuro.
 * Teclado: Escape cierra, + y − cambian el zoom, flechas y Re Pág/Av Pág cambian de página.
 */
export function DocumentViewer({ open, file, onClose, note }: DocumentViewerProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<PdfDocumentProxy | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [page, setPage] = useState(1);
  const [fileKey, setFileKey] = useState<string | null>(null);

  const currentKey = open && file ? `${file.kind}:${file.url}` : null;
  // Archivo nuevo: vuelve al estado inicial (ajuste de estado durante el render).
  if (currentKey !== fileKey) {
    setFileKey(currentKey);
    setZoom(1);
    setRotation(0);
    setPage(1);
    setDoc(null);
    setStatus(currentKey && file?.kind === "pdf" ? "loading" : "ready");
  }

  useEffect(() => {
    if (!open || !file || file.kind !== "pdf") return;
    let cancelled = false;
    let loaded: PdfDocumentProxy | null = null;
    loadPdf(file.url)
      .then((d) => {
        loaded = d;
        if (cancelled) return void d.destroy();
        setDoc(d);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
      void loaded?.destroy();
    };
  }, [open, file]);

  const pages = file?.kind === "pdf" ? (doc?.numPages ?? 0) : 1;

  const goTo = useCallback(
    (n: number) => {
      const target = Math.max(1, Math.min(pages, n));
      setPage(target);
      stageRef.current
        ?.querySelector(`[data-page="${target}"]`)
        ?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    },
    [pages],
  );

  const changeZoom = (delta: number) =>
    setZoom((z) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z + delta * STEP)));

  // Teclado a nivel de documento mientras está abierto: el foco puede quedar en el
  // contenedor del diálogo (por ejemplo, al deshabilitarse el botón enfocado).
  useEffect(() => {
    if (!open || !file) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "+" || event.key === "=") changeZoom(1);
      else if (event.key === "-") changeZoom(-1);
      else if (event.key === "ArrowRight" || event.key === "PageDown") goTo(page + 1);
      else if (event.key === "ArrowLeft" || event.key === "PageUp") goTo(page - 1);
      else return;
      event.preventDefault();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, file, page, goTo]);

  const onScroll = () => {
    const stage = stageRef.current;
    if (!stage) return;
    const top = stage.scrollTop + 80;
    let current = 1;
    stage.querySelectorAll<HTMLElement>("[data-page]").forEach((el) => {
      if (el.offsetTop <= top) current = Number(el.dataset.page);
    });
    if (current !== page) setPage(current);
  };

  const meta =
    file &&
    [
      file.kind === "image"
        ? "Imagen"
        : `PDF${pages ? ` · ${pages} ${pages === 1 ? "página" : "páginas"}` : ""}`,
      file.size,
    ]
      .filter(Boolean)
      .join(" · ");

  const width = stageWidth() * zoom;

  return (
    <ConfigProvider theme={darkTheme}>
      <Modal
        open={open && !!file}
        onCancel={onClose}
        footer={null}
        closable={false}
        // El título da el nombre accesible del diálogo; el encabezado de Ant Design se oculta.
        title={file?.name}
        width="100vw"
        destroyOnHidden
        classNames={{ wrapper: "um-viewer" }}
        styles={{
          header: { display: "none" },
          container: {
            padding: 0,
            borderRadius: 0,
            height: "100dvh",
            display: "flex",
            flexDirection: "column",
          },
          body: { padding: 0, flex: 1, minHeight: 0, display: "flex", flexDirection: "column" },
        }}
        style={{ top: 0, maxWidth: "100vw", margin: 0, paddingBottom: 0 }}
      >
        {file && (
          <div
            data-theme="dark"
            className="bg-bg-canvas text-text-primary flex min-h-0 flex-1 flex-col"
          >
            <div className="border-border-default flex flex-wrap items-center gap-2 border-b px-3 py-2">
              <Button
                type="text"
                aria-label="Cerrar visor"
                icon={<CloseIcon />}
                onClick={onClose}
              />
              <div className="min-w-0">
                <b className="block max-w-[60vw] truncate text-md font-semibold min-[721px]:max-w-[42vw]">
                  {file.name}
                </b>
                <span className="text-text-secondary text-xs">{meta}</span>
              </div>
              <span className="flex-1" />
              {file.kind === "pdf" && (
                <div
                  role="group"
                  aria-label="Páginas"
                  className="border-border-default flex items-center gap-0.5 border-l px-1 max-[720px]:hidden"
                >
                  <Button
                    type="text"
                    size="small"
                    aria-label="Página anterior"
                    icon={<Icon d={ICONS.prev} />}
                    disabled={page <= 1}
                    onClick={() => goTo(page - 1)}
                  />
                  <output className="min-w-14 text-center text-sm tabular-nums">
                    {pages ? `${page} / ${pages}` : "–"}
                  </output>
                  <Button
                    type="text"
                    size="small"
                    aria-label="Página siguiente"
                    icon={<Icon d={ICONS.next} />}
                    disabled={page >= pages}
                    onClick={() => goTo(page + 1)}
                  />
                </div>
              )}
              <div
                role="group"
                aria-label="Zoom"
                className="border-border-default flex items-center gap-0.5 border-l px-1"
              >
                <Button
                  type="text"
                  size="small"
                  aria-label="Alejar"
                  icon={<Icon d={ICONS.minus} />}
                  disabled={zoom <= MIN_ZOOM}
                  onClick={() => changeZoom(-1)}
                />
                <Button
                  type="text"
                  size="small"
                  title="Ajustar al ancho"
                  aria-label={`Zoom ${formatPercent(zoom * 100)}. Ajustar al ancho`}
                  onClick={() => setZoom(1)}
                >
                  <span className="tabular-nums">{formatPercent(zoom * 100)}</span>
                </Button>
                <Button
                  type="text"
                  size="small"
                  aria-label="Acercar"
                  icon={<Icon d={ICONS.plus} />}
                  disabled={zoom >= MAX_ZOOM}
                  onClick={() => changeZoom(1)}
                />
              </div>
              <div className="border-border-default flex items-center gap-0.5 border-l px-1">
                <Button
                  type="text"
                  size="small"
                  aria-label="Girar"
                  icon={<Icon d={ICONS.rotate} />}
                  onClick={() => setRotation((r) => (r + 90) % 360)}
                />
                <Button
                  type="text"
                  size="small"
                  aria-label="Descargar"
                  icon={<Icon d={ICONS.download} />}
                  href={file.url}
                  download={file.name}
                />
              </div>
            </div>

            <div
              ref={stageRef}
              onScroll={onScroll}
              // Enfocable para desplazarse con el teclado (axe: scrollable-region-focusable).
              tabIndex={0}
              role="region"
              aria-label={`Contenido de ${file.name}`}
              className="grid flex-1 content-start justify-items-center gap-6 overflow-auto px-4 py-8 max-[720px]:px-2 max-[720px]:py-4"
            >
              {status === "loading" && (
                <p role="status" className="text-text-secondary m-0">
                  Cargando el documento…
                </p>
              )}
              {status === "error" && (
                <div
                  role="alert"
                  className="text-text-secondary grid justify-items-center gap-3 text-center"
                >
                  <p className="m-0">No pudimos mostrar el documento. Puedes descargarlo.</p>
                  <Button href={file.url} download={file.name}>
                    Descargar
                  </Button>
                </div>
              )}
              {status === "ready" &&
                file.kind === "pdf" &&
                doc &&
                Array.from({ length: doc.numPages }, (_, i) => (
                  <PdfPage
                    key={i + 1}
                    doc={doc}
                    pageNumber={i + 1}
                    zoom={zoom}
                    rotation={rotation}
                  />
                ))}
              {status === "ready" && file.kind === "image" && (
                // eslint-disable-next-line @next/next/no-img-element -- URL prefirmada o local; no pasa por el optimizador de imágenes
                <img
                  src={file.url}
                  alt={`Vista de ${file.name}`}
                  className="h-auto max-w-none shadow-[0_8px_28px_rgba(0,0,0,0.5)] transition-transform motion-reduce:transition-none"
                  style={{
                    width,
                    transform: `rotate(${rotation}deg)`,
                    transformOrigin: "center top",
                  }}
                />
              )}
            </div>
            {note && (
              <div className="text-text-secondary px-3 pb-2 text-center text-xs">{note}</div>
            )}
          </div>
        )}
      </Modal>
    </ConfigProvider>
  );
}
