import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  applyFieldErrors,
  isReadOnlyError,
  networkError,
  parseRetryAfter,
  retryAfterMessage,
  toApiError,
} from "@/lib/api/errors";

describe("toApiError", () => {
  it("toma code, message, details y request_id del cuerpo (API §5.3)", () => {
    const response = new Response(null, { status: 422 });
    const error = toApiError(response, {
      code: "APPLICATION_NOT_READY",
      message: "No cumple.",
      details: [{ field: "documents", code: "DOCUMENT_PENDING", message: "Falta uno." }],
      request_id: "req-1",
    });
    expect(error).toMatchObject({
      status: 422,
      code: "APPLICATION_NOT_READY",
      message: "No cumple.",
      requestId: "req-1",
    });
    expect(error.fieldDetails).toHaveLength(1);
  });

  it("con un cuerpo que no es de la API usa un mensaje genérico y el X-Request-ID", () => {
    const response = new Response(null, { status: 502, headers: { "X-Request-ID": "hdr-1" } });
    const error = toApiError(response, "<html>Bad gateway</html>");
    expect(error).toMatchObject({ status: 502, code: "HTTP_502", requestId: "hdr-1", details: [] });
    expect(error.message).toMatch(/inesperado/);
  });

  it("un 5xx del proxy (sin formato de la API ni X-Request-ID) es un error de red", () => {
    const error = toApiError(new Response(null, { status: 500 }), "Internal Server Error");
    expect(error.isNetworkError).toBe(true);
    expect(error.message).toMatch(/No hay conexión con el servidor/);
  });

  it("lee Retry-After del 429", () => {
    const response = new Response(null, { status: 429, headers: { "Retry-After": "120" } });
    const error = toApiError(response, {
      code: "RATE_LIMITED",
      message: "Límite.",
      details: [],
      request_id: null,
    });
    expect(error.retryAfter).toBe(120);
  });
});

describe("parseRetryAfter", () => {
  it("acepta segundos y fechas HTTP", () => {
    expect(parseRetryAfter("90")).toBe(90);
    const now = Date.parse("2026-11-11T10:00:00Z");
    expect(parseRetryAfter("Wed, 11 Nov 2026 10:02:00 GMT", now)).toBe(120);
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("no-es-fecha")).toBeNull();
  });
});

describe("retryAfterMessage", () => {
  it("redondea a minutos hacia arriba", () => {
    expect(retryAfterMessage(30)).toBe("Vuelve a intentarlo en 1 minuto.");
    expect(retryAfterMessage(61)).toBe("Vuelve a intentarlo en 2 minutos.");
    expect(retryAfterMessage(900)).toBe("Vuelve a intentarlo en 15 minutos.");
    expect(retryAfterMessage(null)).toBe("Vuelve a intentarlo en unos minutos.");
  });
});

describe("applyFieldErrors", () => {
  it("lleva los detalles a los campos y devuelve los que no tienen campo en el formulario", () => {
    const error = new ApiError(400, "VALIDATION_ERROR", "Datos inválidos.", [
      { field: "email", code: "invalid", message: "Correo inválido." },
      { field: "documents", code: "DOCUMENT_PENDING", message: "Falta un documento." },
      { field: null, code: "x", message: "General." },
    ]);
    const setError = vi.fn();
    const leftover = applyFieldErrors(error, setError, ["email", "password"] as const);

    expect(setError).toHaveBeenCalledOnce();
    expect(setError).toHaveBeenCalledWith("email", {
      type: "invalid",
      message: "Correo inválido.",
    });
    expect(leftover.map((d) => d.message)).toEqual(["Falta un documento.", "General."]);
  });
});

describe("isReadOnlyError y networkError", () => {
  it("reconoce los 409 de solo lectura", () => {
    expect(isReadOnlyError(new ApiError(409, "APPLICATION_NOT_EDITABLE", "x"))).toBe(true);
    expect(isReadOnlyError(new ApiError(409, "APPLICATION_CLOSED", "x"))).toBe(true);
    expect(isReadOnlyError(new ApiError(409, "STALE_VERSION", "x"))).toBe(false);
    expect(isReadOnlyError(new Error("x"))).toBe(false);
  });

  it("el error de red no tiene status ni request_id", () => {
    const error = networkError(new TypeError("Failed to fetch"));
    expect(error).toMatchObject({ status: 0, requestId: null, isNetworkError: true });
    expect(error.cause).toBeInstanceOf(TypeError);
  });
});
