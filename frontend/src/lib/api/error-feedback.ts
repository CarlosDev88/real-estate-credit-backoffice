import { isApiError, retryAfterMessage, type ErrorDetail } from "@/lib/api/errors";

/** Qué aviso mostrar para un error de escritura. Sin React, para poder probarlo. */
export interface ErrorToastSpec {
  tone: "danger" | "warning";
  title: string;
  detail: string | null;
  /** `request_id` para rastrear el error en los logs del backend. */
  requestId: string | null;
  /** `409 STALE_VERSION`: botón "Recargar" y el aviso se queda. */
  reload: boolean;
}

const UNEXPECTED = "Ocurrió un error inesperado. Inténtalo de nuevo.";

function joinDetails(details: ErrorDetail[]): string | null {
  const messages = details.map((d) => d.message).filter(Boolean);
  return messages.length ? messages.join(" ") : null;
}

/**
 * Reglas de la spec (Cliente API, parte 3):
 * - error de red: "No hay conexión con el servidor…";
 * - `409 STALE_VERSION`: "Alguien cambió esta solicitud" con "Recargar";
 * - `429`: el mensaje de la API y "Vuelve a intentarlo en N minutos";
 * - cualquier otro: el `message` de la API, sus detalles y "Código: <request_id>".
 *
 * `details` permite pasar solo los detalles que el formulario no pudo ubicar.
 */
export function describeMutationError(error: unknown, details?: ErrorDetail[]): ErrorToastSpec {
  if (!isApiError(error)) {
    return { tone: "danger", title: UNEXPECTED, detail: null, requestId: null, reload: false };
  }
  if (error.isNetworkError) {
    return { tone: "danger", title: error.message, detail: null, requestId: null, reload: false };
  }
  if (error.code === "STALE_VERSION") {
    return {
      tone: "warning",
      title: "Alguien cambió esta solicitud",
      detail: "Recarga para ver los datos actuales. No se guardó nada.",
      requestId: error.requestId,
      reload: true,
    };
  }
  if (error.status === 429) {
    return {
      tone: "danger",
      title: error.message,
      detail: retryAfterMessage(error.retryAfter),
      requestId: error.requestId,
      reload: false,
    };
  }
  return {
    tone: "danger",
    title: error.message,
    detail: joinDetails(details ?? error.details),
    requestId: error.requestId,
    reload: false,
  };
}
