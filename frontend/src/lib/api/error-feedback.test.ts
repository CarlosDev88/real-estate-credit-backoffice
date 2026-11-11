import { describe, expect, it } from "vitest";

import { describeMutationError } from "@/lib/api/error-feedback";
import { ApiError, networkError } from "@/lib/api/errors";

describe("describeMutationError", () => {
  it("error de red: aviso de conexión, sin código", () => {
    expect(describeMutationError(networkError())).toEqual({
      tone: "danger",
      title: "No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo.",
      detail: null,
      requestId: null,
      reload: false,
    });
  });

  it("409 STALE_VERSION: advertencia con Recargar", () => {
    const spec = describeMutationError(new ApiError(409, "STALE_VERSION", "x", [], "req-1"));
    expect(spec).toMatchObject({
      tone: "warning",
      title: "Alguien cambió esta solicitud",
      reload: true,
    });
  });

  it("429: mensaje de la API y el tiempo de Retry-After", () => {
    const spec = describeMutationError(
      new ApiError(429, "RATE_LIMITED", "Demasiados intentos.", [], "req-2", 600),
    );
    expect(spec).toMatchObject({
      tone: "danger",
      title: "Demasiados intentos.",
      detail: "Vuelve a intentarlo en 10 minutos.",
      requestId: "req-2",
    });
  });

  it("error sin campo: message, detalles y request_id", () => {
    const error = new ApiError(
      422,
      "APPLICATION_NOT_READY",
      "No cumple.",
      [{ field: "documents", code: "DOCUMENT_PENDING", message: "Falta un documento." }],
      "req-3",
    );
    expect(describeMutationError(error)).toEqual({
      tone: "danger",
      title: "No cumple.",
      detail: "Falta un documento.",
      requestId: "req-3",
      reload: false,
    });
  });

  it("con detalles filtrados por el formulario muestra solo esos", () => {
    const error = new ApiError(400, "VALIDATION_ERROR", "Datos inválidos.", [
      { field: "email", code: "x", message: "Correo inválido." },
    ]);
    expect(describeMutationError(error, []).detail).toBeNull();
  });

  it("un error que no es de la API: mensaje genérico", () => {
    expect(describeMutationError(new Error("boom")).title).toMatch(/inesperado/);
  });
});
