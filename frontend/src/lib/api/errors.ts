import type { components } from "@/lib/api/schema";

export type ErrorDetail = components["schemas"]["ErrorDetail"];
type ErrorBody = components["schemas"]["Error"];

/** Código propio para cuando no hubo respuesta del servidor. */
export const NETWORK_ERROR = "NETWORK_ERROR";

/** Todo error de la API, con el formato de API §5.3. */
export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ErrorDetail[] = [],
    readonly requestId: string | null = null,
    /** Segundos de `Retry-After` (en `429`), si llegó. */
    readonly retryAfter: number | null = null,
  ) {
    super(message);
  }

  get isNetworkError(): boolean {
    return this.code === NETWORK_ERROR;
  }

  /** Detalles que apuntan a un campo (`details[].field`). */
  get fieldDetails(): ErrorDetail[] {
    return this.details.filter((d) => !!d.field);
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

const GENERIC_MESSAGE = "Ocurrió un error inesperado. Inténtalo de nuevo.";

function isErrorBody(body: unknown): body is ErrorBody {
  return (
    typeof body === "object" &&
    body !== null &&
    typeof (body as ErrorBody).code === "string" &&
    typeof (body as ErrorBody).message === "string"
  );
}

/** `Retry-After` en segundos (acepta segundos o fecha HTTP). */
export function parseRetryAfter(value: string | null, now: number = Date.now()): number | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, Math.ceil(seconds));
  const date = Date.parse(value);
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - now) / 1000));
}

/** Convierte una respuesta de error (y su cuerpo ya leído) en `ApiError`. */
export function toApiError(response: Response, body: unknown): ApiError {
  const headerRequestId = response.headers.get("X-Request-ID");
  const retryAfter = parseRetryAfter(response.headers.get("Retry-After"));
  if (isErrorBody(body)) {
    return new ApiError(
      response.status,
      body.code,
      body.message,
      Array.isArray(body.details) ? body.details : [],
      body.request_id ?? headerRequestId,
      retryAfter,
    );
  }
  // Un 5xx sin el formato de la API ni X-Request-ID (que el backend siempre manda)
  // viene del proxy de Next.js: la API no respondió. Es un error de red.
  if (response.status >= 500 && !headerRequestId) return networkError();
  return new ApiError(
    response.status,
    `HTTP_${response.status}`,
    GENERIC_MESSAGE,
    [],
    headerRequestId,
    retryAfter,
  );
}

export function networkError(cause?: unknown): ApiError {
  const error = new ApiError(
    0,
    NETWORK_ERROR,
    "No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo.",
  );
  if (cause !== undefined) Object.defineProperty(error, "cause", { value: cause });
  return error;
}

/** `409` que dejan los formularios en solo lectura. */
export function isReadOnlyError(error: unknown): boolean {
  return (
    isApiError(error) &&
    (error.code === "APPLICATION_NOT_EDITABLE" || error.code === "APPLICATION_CLOSED")
  );
}

/** "Vuelve a intentarlo en N minutos", desde `Retry-After`. */
export function retryAfterMessage(seconds: number | null): string {
  if (seconds === null) return "Vuelve a intentarlo en unos minutos.";
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `Vuelve a intentarlo en ${minutes} ${minutes === 1 ? "minuto" : "minutos"}.`;
}

/**
 * Lleva los `details[].field` a los campos del formulario (por ejemplo, `setError`
 * de React Hook Form). Devuelve los detalles que no correspondían a ningún campo,
 * para mostrarlos en un toast.
 */
export function applyFieldErrors<F extends string>(
  error: ApiError,
  setError: (name: F, error: { type: string; message: string }) => void,
  fields: readonly F[],
): ErrorDetail[] {
  const leftover: ErrorDetail[] = [];
  for (const detail of error.details) {
    const field = fields.find((f) => f === detail.field);
    if (field) setError(field, { type: detail.code, message: detail.message });
    else leftover.push(detail);
  }
  return leftover;
}
