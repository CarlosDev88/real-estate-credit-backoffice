"use client";

import { Button, Upload } from "antd";
import { useRef, useState } from "react";

import { isApiError } from "@/lib/api/errors";
import { formatBytes, formatPercent } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

export interface UploadContext {
  onProgress: (percent: number) => void;
  signal: AbortSignal;
}

interface DocumentUploaderProps {
  /** Envía el archivo (por ejemplo con `uploadFile`); el componente solo pinta el estado. */
  onUpload: (file: File, context: UploadContext) => Promise<void>;
  /** Tipos MIME permitidos (`allowed_mime_types` de la API). Sin ellos, valida solo la API. */
  accept?: readonly string[];
  /** Tamaño máximo en bytes (`max_size_bytes`). Sin él, valida solo la API. */
  maxBytes?: number;
  /** Reemplazo de un documento rechazado (cambia los textos). */
  replace?: boolean;
  disabled?: boolean;
  className?: string;
}

type State =
  | { kind: "idle" }
  | { kind: "uploading"; name: string; percent: number }
  | { kind: "error"; message: string; retry: File | null };

/** Nombre corto de un tipo MIME para los textos ("application/pdf" → "PDF"). */
function typeLabel(mime: string): string {
  const sub = mime.split("/")[1] ?? mime;
  return (sub === "jpeg" ? "jpg" : sub).toUpperCase();
}

function listLabels(labels: string[]): string {
  return labels.length <= 1
    ? (labels[0] ?? "")
    : `${labels.slice(0, -1).join(", ")} o ${labels[labels.length - 1]}`;
}

const EXTENSIONS: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
};

function matchesType(file: File, accept: readonly string[]): boolean {
  if (file.type) return accept.includes(file.type);
  // Algunos navegadores no informan el tipo: se mira la extensión.
  const name = file.name.toLowerCase();
  return accept.some((mime) => (EXTENSIONS[mime] ?? []).some((ext) => name.endsWith(ext)));
}

/** Valida tipo y tamaño antes de enviar. Devuelve el mensaje de error o `null`. */
export function validateFile(
  file: File,
  accept?: readonly string[],
  maxBytes?: number,
): string | null {
  if (accept && accept.length > 0 && !matchesType(file, accept)) {
    return `Este tipo de archivo no se acepta. Sube un archivo ${listLabels(accept.map(typeLabel))}.`;
  }
  if (maxBytes !== undefined && file.size > maxBytes) {
    return `El archivo pesa ${formatBytes(file.size)} y el máximo es ${formatBytes(maxBytes)}.`;
  }
  return null;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Carga de documentos (mockups `portal-documentos.html` y `solicitud.html`):
 * `Upload.Dragger` en web; "Tomar foto" y "Elegir archivo" en móvil. Valida tipo y
 * tamaño antes de enviar y muestra el progreso, con opción de cancelar.
 */
export function DocumentUploader({
  onUpload,
  accept,
  maxBytes,
  replace = false,
  disabled = false,
  className = "",
}: DocumentUploaderProps) {
  const isMobile = useMediaQuery("(max-width: 720px)");
  const [state, setState] = useState<State>({ kind: "idle" });
  const controller = useRef<AbortController | null>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const acceptAttr = accept?.join(",");
  const allowsPhotos = !accept || accept.some((m) => m.startsWith("image/"));
  const hint = [
    accept?.length ? listLabels(accept.map(typeLabel)) : null,
    maxBytes !== undefined ? `máximo ${formatBytes(maxBytes)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const start = async (file: File) => {
    const invalid = validateFile(file, accept, maxBytes);
    if (invalid) return setState({ kind: "error", message: invalid, retry: null });

    const abort = new AbortController();
    controller.current = abort;
    setState({ kind: "uploading", name: file.name, percent: 0 });
    try {
      await onUpload(file, {
        signal: abort.signal,
        onProgress: (percent) => setState((s) => (s.kind === "uploading" ? { ...s, percent } : s)),
      });
      setState({ kind: "idle" });
    } catch (error) {
      if (isAbort(error)) return setState({ kind: "idle" });
      const message = isApiError(error)
        ? error.message
        : "No pudimos subir el documento. Inténtalo de nuevo.";
      setState({ kind: "error", message, retry: file });
    } finally {
      controller.current = null;
    }
  };

  const pick = (input: HTMLInputElement | null) => {
    const file = input?.files?.[0];
    if (input) input.value = "";
    if (file) void start(file);
  };

  if (state.kind === "uploading") {
    const done = state.percent >= 100;
    return (
      <div
        className={`border-border-default grid gap-2 rounded-lg border p-4 ${className}`}
        aria-live="polite"
      >
        <b className="truncate">{state.name}</b>
        <div
          role="progressbar"
          aria-label={`Subiendo ${state.name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={state.percent}
          className="bg-bg-muted h-2 overflow-hidden rounded"
        >
          <div
            className="bg-brand-primary h-full transition-[width] duration-200 motion-reduce:transition-none"
            style={{ width: `${state.percent}%` }}
          />
        </div>
        <div className="flex items-center gap-2">
          <p className="text-text-secondary m-0 flex-1 text-sm tabular-nums">
            {done ? "Procesando el archivo…" : `Subiendo… ${formatPercent(state.percent)}`}
          </p>
          <Button size="small" onClick={() => controller.current?.abort()}>
            Cancelar
          </Button>
        </div>
      </div>
    );
  }

  const action = replace ? "Reemplazar documento" : "Subir documento";

  return (
    <div className={`grid gap-3 ${className}`}>
      {state.kind === "error" && (
        <div
          role="alert"
          className="border-tone-danger-border bg-tone-danger-bg text-text-primary flex flex-wrap items-center gap-3 rounded-md border px-4 py-3 text-sm"
        >
          <span className="flex-1">{state.message}</span>
          {state.retry && (
            <Button size="small" onClick={() => state.retry && void start(state.retry)}>
              Reintentar
            </Button>
          )}
        </div>
      )}

      {isMobile ? (
        <div className="grid gap-2">
          {allowsPhotos && (
            <Button
              type="primary"
              size="large"
              block
              disabled={disabled}
              onClick={() => cameraInput.current?.click()}
            >
              Tomar foto
            </Button>
          )}
          <Button size="large" block disabled={disabled} onClick={() => fileInput.current?.click()}>
            Elegir archivo
          </Button>
          {hint && <p className="text-text-tertiary m-0 text-center text-xs">{hint}</p>}
          <input
            ref={cameraInput}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            aria-label="Tomar foto"
            onChange={(e) => pick(e.currentTarget)}
          />
          <input
            ref={fileInput}
            type="file"
            accept={acceptAttr}
            hidden
            aria-label="Elegir archivo"
            onChange={(e) => pick(e.currentTarget)}
          />
        </div>
      ) : (
        <Upload.Dragger
          accept={acceptAttr}
          multiple={false}
          showUploadList={false}
          disabled={disabled}
          beforeUpload={(file) => {
            void start(file);
            return Upload.LIST_IGNORE;
          }}
        >
          <div className="grid justify-items-center gap-1 py-2">
            <b className="text-lg font-semibold">{action}</b>
            <span className="text-text-secondary text-sm">
              Arrastra el archivo aquí o haz clic para elegirlo
            </span>
            {hint && <span className="text-text-tertiary text-xs">{hint}</span>}
          </div>
        </Upload.Dragger>
      )}
    </div>
  );
}
