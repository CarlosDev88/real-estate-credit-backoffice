import type { ApiResult } from "@/lib/api/client";
import { networkError, toApiError } from "@/lib/api/errors";
import { canRefreshPath, isBuyerPath, REFRESH_CODES } from "@/lib/api/fetch";
import {
  CSRF_COOKIE,
  notifyAuthFailure,
  notifyBuyerSessionExpired,
  notifyConsentRequired,
  readCookie,
  refreshSession,
} from "@/lib/api/session";
import { versionOf } from "@/lib/api/version";

export interface UploadOptions {
  /** Ruta de la API, por ejemplo `/api/v1/buyer/document-slots/<id>/uploads`. */
  path: string;
  file: File;
  /** Nombre del campo del archivo (por defecto `file`). */
  fieldName?: string;
  /** Otros campos del formulario (por ejemplo `document_date`). */
  fields?: Record<string, string>;
  /** Porcentaje enviado, de 0 a 100. */
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

function parseHeaders(raw: string): Headers {
  const headers = new Headers();
  for (const line of raw.trim().split(/[\r\n]+/)) {
    const index = line.indexOf(":");
    if (index > 0) headers.append(line.slice(0, index).trim(), line.slice(index + 1).trim());
  }
  return headers;
}

function abortError(): DOMException {
  return new DOMException("La carga se canceló.", "AbortError");
}

function send(options: UploadOptions): Promise<Response> {
  const { path, file, fieldName = "file", fields, onProgress, signal } = options;
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());

    const body = new FormData();
    for (const [key, value] of Object.entries(fields ?? {})) body.append(key, value);
    body.append(fieldName, file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", new URL(path, window.location.origin).toString());
    xhr.setRequestHeader("X-Request-ID", crypto.randomUUID());
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) xhr.setRequestHeader("X-CSRFToken", csrf);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      const status = xhr.status;
      const noBody = status === 204 || status === 205 || status === 304;
      resolve(
        new Response(noBody ? null : xhr.responseText, {
          status,
          headers: parseHeaders(xhr.getAllResponseHeaders()),
        }),
      );
    };
    xhr.onerror = () => reject(networkError());
    xhr.onabort = () => reject(abortError());
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });

    xhr.send(body);
  });
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/**
 * Sube un archivo con `multipart/form-data` informando el progreso (fetch no lo da).
 * Mismas reglas que `apiFetch`: `X-Request-ID` y `X-CSRFToken`; en rutas internas, un
 * `401` renueva la sesión y reintenta una vez; en el portal, emite sus eventos.
 * Devuelve `{ data, version }` o lanza `ApiError` (o `AbortError` si se cancela).
 */
export async function uploadFile<T = unknown>(options: UploadOptions): Promise<ApiResult<T>> {
  const startedAt = Date.now();
  let response = await send(options);
  let body = await readBody(response);
  const code =
    typeof body === "object" && body !== null && "code" in body ? String(body.code) : null;

  if (isBuyerPath(options.path)) {
    if (response.status === 401 && code === "SESSION_EXPIRED") notifyBuyerSessionExpired();
    if (response.status === 403 && code === "CONSENT_REQUIRED") notifyConsentRequired();
  } else if (
    response.status === 401 &&
    code &&
    REFRESH_CODES.has(code) &&
    canRefreshPath(options.path)
  ) {
    if (await refreshSession(startedAt)) {
      options.onProgress?.(0);
      response = await send(options);
      body = await readBody(response);
      if (response.status === 401) notifyAuthFailure();
    } else {
      notifyAuthFailure();
    }
  }

  if (!response.ok) throw toApiError(response, body);
  return { data: body as T, version: versionOf(response), response };
}
