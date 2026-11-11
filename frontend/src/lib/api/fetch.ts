import { networkError } from "@/lib/api/errors";
import {
  CSRF_COOKIE,
  notifyAuthFailure,
  notifyBuyerSessionExpired,
  notifyConsentRequired,
  readCookie,
  refreshSession,
} from "@/lib/api/session";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const REFRESH_CODES = new Set(["NOT_AUTHENTICATED", "SESSION_EXPIRED"]);

// Rutas que nunca disparan el refresh: las de la sesión interna y las del comprador.
const NO_REFRESH = [
  /^\/api\/v1\/auth\/(login|refresh|logout)$/,
  /^\/api\/v1\/buyer\//,
  /^\/api\/v1\/buyer-access\//,
];

function isBuyerPath(path: string): boolean {
  return path.startsWith("/api/v1/buyer/");
}

function withHeaders(request: Request): Request {
  const headers = new Headers(request.headers);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (UNSAFE_METHODS.has(request.method.toUpperCase())) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  return new Request(request, { headers });
}

async function send(request: Request): Promise<Response> {
  try {
    return await fetch(request);
  } catch (cause) {
    // Sin respuesta del servidor (red caída, CORS, DNS…).
    throw networkError(cause);
  }
}

async function errorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.clone().json();
    return typeof body === "object" && body !== null && "code" in body
      ? String((body as { code: unknown }).code)
      : null;
  } catch {
    return null;
  }
}

/**
 * `fetch` del cliente API. Agrega `X-Request-ID` y, en escrituras, `X-CSRFToken`.
 * Ante un `401` del backoffice, renueva la sesión una vez y reintenta; si no se
 * puede, avisa al manejador de fallo. En el portal, emite los eventos de sesión
 * vencida y de consentimiento pendiente.
 */
export async function apiFetch(input: Request): Promise<Response> {
  const startedAt = Date.now();
  const path = new URL(input.url).pathname;
  const canRefresh = !NO_REFRESH.some((re) => re.test(path));
  // Copia para el reintento: el cuerpo de una petición se consume una sola vez.
  const retryCopy = canRefresh ? input.clone() : null;

  const response = await send(withHeaders(input));

  if (isBuyerPath(path)) {
    if (response.status === 401 && (await errorCode(response)) === "SESSION_EXPIRED") {
      notifyBuyerSessionExpired();
    } else if (response.status === 403 && (await errorCode(response)) === "CONSENT_REQUIRED") {
      notifyConsentRequired();
    }
    return response;
  }

  if (response.status !== 401 || !retryCopy) return response;
  const code = await errorCode(response);
  if (!code || !REFRESH_CODES.has(code)) return response;

  if (!(await refreshSession(startedAt))) {
    notifyAuthFailure();
    return response;
  }

  const retried = await send(withHeaders(retryCopy));
  if (retried.status === 401) notifyAuthFailure();
  return retried;
}
