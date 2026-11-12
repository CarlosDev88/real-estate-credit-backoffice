import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, NETWORK_ERROR } from "@/lib/api/errors";
import { apiFetch } from "@/lib/api/fetch";
import type * as Navigation from "@/lib/api/navigation";
import { redirectTo } from "@/lib/api/navigation";
import {
  LAST_REFRESH_KEY,
  REFRESH_LOCK,
  setAuthFailureHandler,
  setBuyerSessionExpiredHandler,
  setConsentRequiredHandler,
} from "@/lib/api/session";
import { apiUrl, server } from "@/test/msw-server";

vi.mock("@/lib/api/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof Navigation>()),
  redirectTo: vi.fn(),
}));

const unauthorized = (code = "NOT_AUTHENTICATED") =>
  HttpResponse.json(
    { code, message: "No autenticado.", details: [], request_id: "r-1" },
    { status: 401 },
  );

/** Cuenta los refresh y responde según `ok`. */
function refreshHandler(ok = true) {
  const calls = { count: 0 };
  server.use(
    http.post(apiUrl("/auth/refresh"), () => {
      calls.count += 1;
      return ok
        ? HttpResponse.json({ session_expires_at: "2026-11-11T23:00:00Z" })
        : unauthorized("SESSION_EXPIRED");
    }),
  );
  return calls;
}

/** `/auth/me` responde 401 hasta que hubo un refresh exitoso. */
function meHandler(refresh: { count: number }) {
  const calls = { count: 0 };
  server.use(
    http.get(apiUrl("/auth/me"), () => {
      calls.count += 1;
      return refresh.count > 0 ? HttpResponse.json({ id: "u-1" }) : unauthorized();
    }),
  );
  return calls;
}

const get = (path: string) => apiFetch(new Request(apiUrl(path)));

beforeEach(() => {
  vi.mocked(redirectTo).mockReset();
  setAuthFailureHandler(null);
  setBuyerSessionExpiredHandler(null);
  setConsentRequiredHandler(null);
});

describe("cabeceras", () => {
  it("agrega X-Request-ID y, solo en escrituras, X-CSRFToken desde la cookie app_csrf", async () => {
    document.cookie = "app_csrf=csrf-123; Path=/";
    const seen: Record<string, { id: string | null; csrf: string | null }> = {};
    server.use(
      http.all(apiUrl("/echo"), ({ request }) => {
        seen[request.method] = {
          id: request.headers.get("X-Request-ID"),
          csrf: request.headers.get("X-CSRFToken"),
        };
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await get("/echo");
    await apiFetch(new Request(apiUrl("/echo"), { method: "POST" }));

    expect(seen.GET?.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(seen.GET?.csrf).toBeNull();
    expect(seen.POST?.csrf).toBe("csrf-123");
  });

  it("convierte la falta de respuesta del servidor en ApiError de red", async () => {
    server.use(http.get(apiUrl("/down"), () => HttpResponse.error()));
    const error = await get("/down").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe(NETWORK_ERROR);
    expect((error as ApiError).isNetworkError).toBe(true);
  });
});

describe("refresh de la sesión interna", () => {
  it("ante un 401 refresca una vez, reintenta y guarda solo la hora del refresh", async () => {
    const refresh = refreshHandler();
    const me = meHandler(refresh);

    const response = await get("/auth/me");

    expect(response.status).toBe(200);
    expect(refresh.count).toBe(1);
    expect(me.count).toBe(2);
    expect(Object.keys(window.localStorage)).toEqual([LAST_REFRESH_KEY]);
    expect(Number(window.localStorage.getItem(LAST_REFRESH_KEY))).toBeGreaterThan(0);
  });

  it("refresca con SESSION_EXPIRED igual que con NOT_AUTHENTICATED", async () => {
    const refresh = refreshHandler();
    server.use(
      http.get(apiUrl("/applications"), () =>
        refresh.count > 0 ? HttpResponse.json({ items: [] }) : unauthorized("SESSION_EXPIRED"),
      ),
    );
    expect((await get("/applications")).status).toBe(200);
    expect(refresh.count).toBe(1);
  });

  it("dos 401 a la vez en la misma pestaña hacen un solo refresh", async () => {
    const refresh = refreshHandler();
    // Las dos primeras peticiones salen con la sesión vencida: el servidor retiene
    // sus 401 hasta que llegan ambas, para que de verdad coincidan.
    let meCalls = 0;
    let releaseFirst: () => void = () => {};
    const bothArrived = new Promise<void>((resolve) => (releaseFirst = resolve));
    server.use(
      http.get(apiUrl("/auth/me"), async () => {
        meCalls += 1;
        if (meCalls === 1) {
          await bothArrived;
          return unauthorized();
        }
        if (meCalls === 2) {
          releaseFirst();
          return unauthorized();
        }
        return HttpResponse.json({ id: "u-1" });
      }),
    );

    const [a, b] = await Promise.all([get("/auth/me"), get("/auth/me")]);

    expect([a.status, b.status]).toEqual([200, 200]);
    expect(refresh.count).toBe(1);
    expect(meCalls).toBe(4);
  });

  it("con un refresh reciente de otra pestaña no vuelve a refrescar: solo reintenta", async () => {
    const refresh = refreshHandler();
    let meCalls = 0;
    server.use(
      http.get(apiUrl("/auth/me"), () => {
        meCalls += 1;
        if (meCalls === 1) {
          // Mientras esta petición viajaba, otra pestaña refrescó la sesión.
          window.localStorage.setItem(LAST_REFRESH_KEY, String(Date.now()));
          return unauthorized();
        }
        return HttpResponse.json({ id: "u-1" });
      }),
    );

    expect((await get("/auth/me")).status).toBe(200);
    expect(refresh.count).toBe(0);
    expect(meCalls).toBe(2);
  });

  it("un refresh fallido lleva a /login con el next interno de la ruta actual", async () => {
    window.history.replaceState(null, "", "/solicitudes?page=2");
    refreshHandler(false);
    server.use(http.get(apiUrl("/auth/me"), () => unauthorized()));

    const response = await get("/auth/me");

    expect(response.status).toBe(401);
    expect(redirectTo).toHaveBeenCalledWith("/login?next=%2Fsolicitudes%3Fpage%3D2");
  });

  it("en el login, un refresh fallido no vuelve a redirigir (sin bucle)", async () => {
    window.history.replaceState(null, "", "/login?next=%2Fsolicitudes");
    refreshHandler(false);
    server.use(http.get(apiUrl("/auth/me"), () => unauthorized()));

    expect((await get("/auth/me")).status).toBe(401);
    expect(redirectTo).not.toHaveBeenCalled();
  });

  it("usa el manejador de fallo inyectado en lugar de la redirección por defecto", async () => {
    const onFailure = vi.fn();
    setAuthFailureHandler(onFailure);
    refreshHandler(false);
    server.use(http.get(apiUrl("/auth/me"), () => unauthorized()));

    await get("/auth/me");

    expect(onFailure).toHaveBeenCalledOnce();
    expect(redirectTo).not.toHaveBeenCalled();
  });

  it("si el reintento vuelve a dar 401, avisa el fallo", async () => {
    const onFailure = vi.fn();
    setAuthFailureHandler(onFailure);
    refreshHandler(true);
    server.use(http.get(apiUrl("/auth/me"), () => unauthorized()));

    expect((await get("/auth/me")).status).toBe(401);
    expect(onFailure).toHaveBeenCalledOnce();
  });

  it("reintenta una escritura con el mismo cuerpo y X-CSRFToken", async () => {
    document.cookie = "app_csrf=csrf-xyz; Path=/";
    const refresh = refreshHandler();
    const bodies: unknown[] = [];
    server.use(
      http.patch(apiUrl("/applications/a-1"), async ({ request }) => {
        bodies.push({ body: await request.json(), csrf: request.headers.get("X-CSRFToken") });
        return refresh.count > 0 ? HttpResponse.json({ ok: true }) : unauthorized();
      }),
    );

    const response = await apiFetch(
      new Request(apiUrl("/applications/a-1"), {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "If-Match": '"7"' },
        body: JSON.stringify({ notes: "hola" }),
      }),
    );

    expect(response.status).toBe(200);
    expect(bodies).toEqual([
      { body: { notes: "hola" }, csrf: "csrf-xyz" },
      { body: { notes: "hola" }, csrf: "csrf-xyz" },
    ]);
  });

  it("no refresca con un 401 de otro código", async () => {
    const refresh = refreshHandler();
    server.use(http.get(apiUrl("/x"), () => unauthorized("MAGIC_LINK_INVALID")));
    expect((await get("/x")).status).toBe(401);
    expect(refresh.count).toBe(0);
  });

  it.each(["/auth/login", "/auth/refresh", "/auth/logout"])(
    "%s nunca dispara el refresh",
    async (path) => {
      let refreshes = 0;
      server.use(
        http.post(apiUrl(path), () => {
          if (path === "/auth/refresh") refreshes += 1;
          return unauthorized("SESSION_EXPIRED");
        }),
        http.post(apiUrl("/auth/refresh"), () => {
          refreshes += 1;
          return unauthorized("SESSION_EXPIRED");
        }),
      );
      const response = await apiFetch(new Request(apiUrl(path), { method: "POST" }));
      expect(response.status).toBe(401);
      expect(refreshes).toBe(path === "/auth/refresh" ? 1 : 0);
      expect(redirectTo).not.toHaveBeenCalled();
    },
  );

  it("serializa entre pestañas con navigator.locks", async () => {
    const request = vi.fn((_name: string, cb: () => Promise<boolean>) => cb());
    Object.defineProperty(navigator, "locks", { value: { request }, configurable: true });
    try {
      const refresh = refreshHandler();
      meHandler(refresh);
      expect((await get("/auth/me")).status).toBe(200);
      expect(request).toHaveBeenCalledWith(REFRESH_LOCK, expect.any(Function));
    } finally {
      Reflect.deleteProperty(navigator, "locks");
    }
  });

  describe("con localStorage que falla", () => {
    afterEach(() => vi.restoreAllMocks());

    it("se comporta como si no hubiera dato y refresca igual", async () => {
      vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("bloqueado");
      });
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("bloqueado");
      });
      const refresh = refreshHandler();
      meHandler(refresh);
      expect((await get("/auth/me")).status).toBe(200);
      expect(refresh.count).toBe(1);
    });
  });
});

describe("portal del comprador", () => {
  it("401 SESSION_EXPIRED avisa la sesión vencida y no refresca", async () => {
    const onExpired = vi.fn();
    setBuyerSessionExpiredHandler(onExpired);
    const refresh = refreshHandler();
    server.use(http.get(apiUrl("/buyer/processes"), () => unauthorized("SESSION_EXPIRED")));

    expect((await get("/buyer/processes")).status).toBe(401);
    expect(onExpired).toHaveBeenCalledOnce();
    expect(refresh.count).toBe(0);
  });

  it("403 CONSENT_REQUIRED avisa el consentimiento pendiente", async () => {
    const onConsent = vi.fn();
    setConsentRequiredHandler(onConsent);
    server.use(
      http.put(apiUrl("/buyer/applications/a-1/property"), () =>
        HttpResponse.json(
          {
            code: "CONSENT_REQUIRED",
            message: "Falta un consentimiento.",
            details: [],
            request_id: null,
          },
          { status: 403 },
        ),
      ),
    );

    const response = await apiFetch(
      new Request(apiUrl("/buyer/applications/a-1/property"), { method: "PUT" }),
    );
    expect(response.status).toBe(403);
    expect(onConsent).toHaveBeenCalledOnce();
  });
});
