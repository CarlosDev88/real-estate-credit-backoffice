// Sesión interna: refresh serializado entre pestañas y manejadores de fallo.
import { currentPath, redirectTo } from "@/lib/api/navigation";

export const CSRF_COOKIE = "app_csrf";
export const REFRESH_LOCK = "um-auth-refresh";
/** En localStorage solo va la hora del último refresh; nunca tokens ni datos de la sesión. */
export const LAST_REFRESH_KEY = "um-auth-last-refresh";
const REFRESH_PATH = "/api/v1/auth/refresh";

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length));
  }
  return null;
}

export function readLastRefresh(): number | null {
  try {
    const value = Number(window.localStorage.getItem(LAST_REFRESH_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeLastRefresh(at: number): void {
  try {
    window.localStorage.setItem(LAST_REFRESH_KEY, String(at));
  } catch {
    // Sin almacenamiento: las otras pestañas no se enteran y refrescarán por su cuenta.
  }
}

// ---------- `next` y login ----------

/** Solo rutas internas: empieza con una `/` y no es `//host` ni `/\host`. */
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return null;
  }
  try {
    const url = new URL(next, "http://internal.invalid");
    if (url.origin !== "http://internal.invalid") return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

export function loginUrl(next: string | null | undefined): string {
  const safe = safeNextPath(next);
  return safe && !safe.startsWith("/login") ? `/login?next=${encodeURIComponent(safe)}` : "/login";
}

// ---------- manejadores inyectables ----------

type Handler = () => void;

const defaultAuthFailure: Handler = () => {
  redirectTo(loginUrl(currentPath()));
};

const handlers: {
  authFailure: Handler;
  buyerSessionExpired: Handler;
  consentRequired: Handler;
} = {
  authFailure: defaultAuthFailure,
  buyerSessionExpired: () => {},
  consentRequired: () => {},
};

/** El refresh falló: por defecto lleva a `/login?next=<ruta actual>`. */
export function setAuthFailureHandler(handler: Handler | null): void {
  handlers.authFailure = handler ?? defaultAuthFailure;
}

/** `401 SESSION_EXPIRED` del portal del comprador. La pantalla la decide F2. */
export function setBuyerSessionExpiredHandler(handler: Handler | null): void {
  handlers.buyerSessionExpired = handler ?? (() => {});
}

/** `403 CONSENT_REQUIRED` del portal del comprador. La pantalla la decide F2. */
export function setConsentRequiredHandler(handler: Handler | null): void {
  handlers.consentRequired = handler ?? (() => {});
}

export function notifyAuthFailure(): void {
  handlers.authFailure();
}
export function notifyBuyerSessionExpired(): void {
  handlers.buyerSessionExpired();
}
export function notifyConsentRequired(): void {
  handlers.consentRequired();
}

// ---------- refresh ----------

async function postRefresh(): Promise<boolean> {
  const headers = new Headers({ "X-Request-ID": crypto.randomUUID() });
  const csrf = readCookie(CSRF_COOKIE);
  if (csrf) headers.set("X-CSRFToken", csrf);
  try {
    const response = await fetch(new URL(REFRESH_PATH, window.location.origin), {
      method: "POST",
      headers,
      credentials: "same-origin",
    });
    return response.ok;
  } catch {
    return false;
  }
}

let inflight: Promise<boolean> | null = null;

/**
 * Renueva la sesión una sola vez aunque haya varios `401` a la vez.
 * - En la pestaña, los `401` simultáneos comparten la misma promesa.
 * - Entre pestañas, `navigator.locks` serializa; con el candado tomado, si otra
 *   pestaña refrescó después de que salió la petición, no se vuelve a refrescar.
 * Devuelve `true` si la petición puede reintentarse.
 */
export function refreshSession(requestStartedAt: number): Promise<boolean> {
  if (inflight) return inflight;

  const run = async (): Promise<boolean> => {
    const last = readLastRefresh();
    if (last !== null && last >= requestStartedAt) return true;
    const ok = await postRefresh();
    if (ok) writeLastRefresh(Date.now());
    return ok;
  };

  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  const exec = async (): Promise<boolean> =>
    locks ? await locks.request(REFRESH_LOCK, run) : await run();
  const pending = exec().finally(() => {
    inflight = null;
  });
  inflight = pending;
  return pending;
}
