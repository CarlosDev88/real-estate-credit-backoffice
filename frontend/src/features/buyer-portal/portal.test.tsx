import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccessScreen, tooManyAttemptsMessage } from "@/features/buyer-portal/access-screen";
import { ConsentsScreen } from "@/features/buyer-portal/consents-screen";
import { remainingText } from "@/features/buyer-portal/expiry";
import { PortalHome, firstName } from "@/features/buyer-portal/home-screen";
import { CONSENTS_PATH, PortalGuard } from "@/features/buyer-portal/portal-guard";
import {
  APP_ID,
  apiError,
  consentFixture,
  portalHandlers,
  sessionFixture,
} from "@/features/buyer-portal/portal.fixtures";
import { initials } from "@/features/buyer-portal/portal-shell";
import { api, call } from "@/lib/api/client";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";
import { ThemeProvider } from "@/providers/theme-provider";

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), pathname: "/portal" }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => router.pathname,
}));

function renderPortal(ui: ReactElement) {
  return renderWithProviders(
    <ThemeProvider initialMode="light" hasCookie>
      {ui}
    </ThemeProvider>,
  );
}

beforeEach(() => {
  router.replace.mockReset();
  router.push.mockReset();
  router.pathname = "/portal";
});

describe("/acceso", () => {
  it("borra el token de la URL antes de enviarlo y, si sale bien, va al portal", async () => {
    window.history.replaceState(null, "", "/acceso?token=abc123");
    let sent: unknown = null;
    let searchWhenSent: string | null = null;
    server.use(
      http.post(apiUrl("/buyer-access/consume"), async ({ request }) => {
        searchWhenSent = window.location.search;
        sent = await request.json();
        return HttpResponse.json({
          buyer: { display_name: "Sofía Herrera" },
          application: sessionFixture().application,
          session_expires_at: "2026-11-18T10:00:00Z",
        });
      }),
    );
    renderPortal(<AccessScreen />);

    expect(window.location.pathname + window.location.search).toBe("/acceso");
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/portal"));
    expect(sent).toEqual({ token: "abc123" });
    expect(searchWhenSent).toBe("");
  });

  it.each([
    ["MAGIC_LINK_EXPIRED", "Este enlace venció"],
    ["MAGIC_LINK_CONSUMED", "Este enlace ya se usó"],
    ["MAGIC_LINK_REVOKED", "Este enlace ya no sirve"],
    ["MAGIC_LINK_INVALID", "Este enlace no es válido"],
  ])("%s: su pantalla, el mensaje de la API y pedir un enlace nuevo", async (code, title) => {
    window.history.replaceState(null, "", "/acceso?token=t");
    server.use(
      http.post(apiUrl("/buyer-access/consume"), () => apiError(401, code, `Mensaje ${code}.`)),
    );
    renderPortal(<AccessScreen />);

    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByText(`Mensaje ${code}.`)).toBeInTheDocument();
    expect(screen.getByText("Pídele un enlace nuevo a tu asesor.")).toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("429: demasiados intentos con los minutos de Retry-After", async () => {
    window.history.replaceState(null, "", "/acceso?token=t");
    server.use(
      http.post(apiUrl("/buyer-access/consume"), () =>
        HttpResponse.json(
          { code: "RATE_LIMITED", message: "Límite alcanzado.", details: [], request_id: "r" },
          { status: 429, headers: { "Retry-After": "600" } },
        ),
      ),
    );
    renderPortal(<AccessScreen />);
    expect(
      await screen.findByRole("heading", { name: "Demasiados intentos, espera 10 minutos." }),
    ).toBeInTheDocument();
  });

  it("sin token, enlace no válido sin llamar a la API", () => {
    window.history.replaceState(null, "", "/acceso");
    renderPortal(<AccessScreen />);
    expect(screen.getByRole("heading", { name: "Este enlace no es válido" })).toBeInTheDocument();
  });

  it("error del servidor: permite reintentar con el mismo token", async () => {
    window.history.replaceState(null, "", "/acceso?token=t");
    let calls = 0;
    server.use(
      http.post(apiUrl("/buyer-access/consume"), () => {
        calls += 1;
        return calls === 1
          ? apiError(503, "SERVICE_UNAVAILABLE", "Servicio no disponible.")
          : HttpResponse.json({
              buyer: { display_name: "S" },
              application: sessionFixture().application,
              session_expires_at: "2026-11-18T10:00:00Z",
            });
      }),
    );
    const user = userEvent.setup();
    renderPortal(<AccessScreen />);
    await user.click(await screen.findByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/portal"));
    expect(calls).toBe(2);
  });

  it("textos de 429 sin Retry-After y con un minuto", () => {
    expect(tooManyAttemptsMessage(null)).toBe("Demasiados intentos, espera unos minutos.");
    expect(tooManyAttemptsMessage(30)).toBe("Demasiados intentos, espera 1 minuto.");
  });
});

describe("PortalGuard", () => {
  it("con sesión pinta el encabezado, la navegación y el contenido", async () => {
    server.use(...portalHandlers());
    renderPortal(<PortalGuard>contenido</PortalGuard>);

    expect(screen.getByRole("status")).toHaveTextContent("Cargando…");
    expect(await screen.findByRole("main")).toHaveTextContent("contenido");
    expect(screen.getByRole("button", { name: "Cuenta de Sofía Herrera" })).toHaveTextContent("SH");
    expect(screen.getAllByText("SOL-000182").length).toBeGreaterThan(0);
    const bottom = screen.getByRole("navigation", { name: "Navegación del portal" });
    expect(within(bottom).getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByText("Avisos")).not.toBeInTheDocument();
  });

  it("muestra en Documentos cuántos le tocan al comprador", async () => {
    const session = sessionFixture();
    server.use(
      http.get(apiUrl("/buyer/session"), () => HttpResponse.json(session)),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/document-slots`), () =>
        HttpResponse.json({
          items: [{ needs_action: true }, { needs_action: true }, { needs_action: false }],
          page: 1,
          page_size: 100,
          total: 3,
          next: null,
          previous: null,
        }),
      ),
    );
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    const bottom = await screen.findByRole("navigation", { name: "Navegación del portal" });
    await waitFor(() =>
      expect(within(bottom).getByRole("link", { name: /Documentos/ })).toHaveTextContent(
        "Documentos2 pendientes",
      ),
    );
  });

  it("401 de la sesión: 'Tu acceso venció', sin datos de la solicitud", async () => {
    server.use(
      http.get(apiUrl("/buyer/session"), () => apiError(401, "SESSION_EXPIRED", "Venció.")),
    );
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    expect(await screen.findByRole("heading", { name: "Tu acceso venció" })).toBeInTheDocument();
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
    expect(screen.queryByText("SOL-000182")).not.toBeInTheDocument();
  });

  it("un 401 SESSION_EXPIRED de otra petición del portal también lleva a esa pantalla", async () => {
    server.use(
      ...portalHandlers(),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/consents`), () =>
        apiError(401, "SESSION_EXPIRED", "Venció."),
      ),
    );
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await screen.findByText("contenido");

    await act(async () => {
      await call(
        api.GET("/api/v1/buyer/applications/{application_id}/consents", {
          params: { path: { application_id: APP_ID } },
        }),
      ).catch(() => null);
    });
    expect(await screen.findByRole("heading", { name: "Tu acceso venció" })).toBeInTheDocument();
    expect(screen.queryByText("SOL-000182")).not.toBeInTheDocument();
  });

  it("si la sesión falla por otra razón, ofrece reintentar", async () => {
    server.use(http.get(apiUrl("/buyer/session"), () => apiError(500, "BOOM", "Algo falló.")));
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    expect(
      await screen.findByRole("heading", { name: "No pudimos cargar tu solicitud" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("con consentimientos pendientes redirige a /portal/consentimientos", async () => {
    server.use(...portalHandlers(sessionFixture({ pending_consents: ["DATA_PROCESSING"] })));
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(CONSENTS_PATH));
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
  });

  it("en la página de consentimientos pinta el contenido sin navegación", async () => {
    router.pathname = CONSENTS_PATH;
    server.use(...portalHandlers(sessionFixture({ pending_consents: ["DATA_PROCESSING"] })));
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    expect(await screen.findByText("contenido")).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Navegación del portal" }),
    ).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("un 403 CONSENT_REQUIRED lleva a los consentimientos", async () => {
    server.use(
      ...portalHandlers(),
      http.put(apiUrl(`/buyer/applications/${APP_ID}/property`), () =>
        apiError(403, "CONSENT_REQUIRED", "Falta un consentimiento."),
      ),
    );
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await screen.findByText("contenido");
    await act(async () => {
      await call(
        api.PUT("/api/v1/buyer/applications/{application_id}/property", {
          params: { path: { application_id: APP_ID }, header: { "If-Match": '"1"' } },
          body: {} as never,
        }),
      ).catch(() => null);
    });
    expect(router.replace).toHaveBeenCalledWith(CONSENTS_PATH);
  });

  it("Salir cierra la sesión y muestra 'Saliste del portal'", async () => {
    let loggedOut = false;
    server.use(
      ...portalHandlers(),
      http.post(apiUrl("/buyer/session/logout"), () => {
        loggedOut = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await user.click(await screen.findByRole("button", { name: "Cuenta de Sofía Herrera" }));
    await user.click(await screen.findByRole("menuitem", { name: "Salir" }));

    expect(await screen.findByRole("heading", { name: "Saliste del portal" })).toBeInTheDocument();
    expect(loggedOut).toBe(true);
    expect(screen.queryByText("SOL-000182")).not.toBeInTheDocument();
  });

  it("si Salir falla, avisa y se queda", async () => {
    server.use(
      ...portalHandlers(),
      http.post(apiUrl("/buyer/session/logout"), () =>
        apiError(403, "CSRF_FAILED", "Falta el token CSRF."),
      ),
    );
    const user = userEvent.setup();
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await user.click(await screen.findByRole("button", { name: "Cuenta de Sofía Herrera" }));
    await user.click(await screen.findByRole("menuitem", { name: "Salir" }));
    expect(await screen.findByText("Falta el token CSRF.")).toBeInTheDocument();
    expect(screen.getByText("contenido")).toBeInTheDocument();
  });

  it.each([
    [{ is_closed: true, is_editable: false }, "Tu solicitud está cerrada"],
    [{ is_closed: false, is_editable: false }, "Tu solicitud ya no admite cambios"],
  ])("franja de solo lectura (%o)", async (flags, title) => {
    const base = sessionFixture();
    server.use(
      ...portalHandlers(
        sessionFixture({
          application: { ...base.application, ...flags, public_status_label: "Desistida" },
        }),
      ),
    );
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    const banner = await screen.findByText(title);
    expect(banner.parentElement).toHaveTextContent(`${title} · Desistida`);
  });

  it("sin franja si la solicitud es editable", async () => {
    server.use(...portalHandlers());
    renderPortal(<PortalGuard>contenido</PortalGuard>);
    await screen.findByText("contenido");
    expect(screen.queryByText(/Tu solicitud (está cerrada|ya no admite)/)).not.toBeInTheDocument();
  });

  it("el inicio saluda y avisa cuándo vence el acceso", async () => {
    server.use(...portalHandlers());
    renderPortal(
      <PortalGuard>
        <PortalHome />
      </PortalGuard>,
    );
    expect(await screen.findByRole("heading", { name: "Hola, Sofía" })).toBeInTheDocument();
    expect(screen.getByText(/Tu acceso vence en/)).toHaveTextContent(
      "Tu acceso vence en 21 horas. Si se vence, pide un enlace nuevo a tu asesor.",
    );
  });
});

describe("ConsentsScreen", () => {
  const optional = consentFixture({
    id: "c-mkt",
    code: "MARKETING",
    title: "Comunicaciones comerciales",
    body: "Acepto recibir ofertas.",
    required: false,
    status: "ACCEPTED",
    accepted_at: "2026-11-17T15:00:00Z",
  });

  function renderConsents() {
    router.pathname = CONSENTS_PATH;
    return renderPortal(
      <PortalGuard>
        <ConsentsScreen />
      </PortalGuard>,
    );
  }

  it("acepta un obligatorio y, sin pendientes, Continuar lleva al inicio", async () => {
    let accepted = false;
    const posted: unknown[] = [];
    server.use(
      http.get(apiUrl("/buyer/session"), () =>
        HttpResponse.json(
          sessionFixture({ pending_consents: accepted ? [] : ["DATA_PROCESSING"] }),
        ),
      ),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/consents`), () =>
        HttpResponse.json({
          items: [
            consentFixture(
              accepted ? { status: "ACCEPTED", accepted_at: "2026-11-17T16:00:00Z" } : {},
            ),
            optional,
          ],
          pending_required: accepted ? [] : ["DATA_PROCESSING"],
        }),
      ),
      http.post(apiUrl(`/buyer/applications/${APP_ID}/consents`), async ({ request }) => {
        posted.push(await request.json());
        accepted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderConsents();

    const continueButton = await screen.findByRole("button", { name: "Continuar" });
    expect(continueButton).toBeDisabled();
    expect(
      screen.getByText("Acepta los consentimientos obligatorios para continuar."),
    ).toBeVisible();

    // El texto del consentimiento está plegado.
    const toggle = screen.getAllByRole("button", { name: "Leer el texto completo" })[0]!;
    expect(screen.getByText("Autorizo el tratamiento de mis datos.")).not.toBeVisible();
    await user.click(toggle);
    expect(screen.getByText("Autorizo el tratamiento de mis datos.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Acepto" }));
    expect(posted).toEqual([{ consent_definition_id: "c-data", action: "ACCEPTED" }]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Continuar" })).toBeEnabled());
    expect(screen.queryByRole("button", { name: "Acepto" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/portal"));
  });

  it("retira un opcional aceptado después de confirmar", async () => {
    const posted: unknown[] = [];
    server.use(
      ...portalHandlers(),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/consents`), () =>
        HttpResponse.json({
          items: [
            consentFixture({ status: "ACCEPTED", accepted_at: "2026-11-17T15:00:00Z" }),
            optional,
          ],
          pending_required: [],
        }),
      ),
      http.post(apiUrl(`/buyer/applications/${APP_ID}/consents`), async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderConsents();

    // Un obligatorio aceptado no se puede retirar desde aquí; el opcional sí.
    const withdraw = await screen.findAllByRole("button", { name: "Retirar mi consentimiento" });
    expect(withdraw).toHaveLength(1);
    expect(screen.getAllByText(/Aceptado el/)).toHaveLength(2);

    await user.click(withdraw[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("¿Retirar tu consentimiento?");
    expect(posted).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Retirar" }));
    await waitFor(() =>
      expect(posted).toEqual([{ consent_definition_id: "c-mkt", action: "WITHDRAWN" }]),
    );
  });

  it("con la solicitud cerrada no deja aceptar", async () => {
    const base = sessionFixture({ pending_consents: ["DATA_PROCESSING"] });
    server.use(
      ...portalHandlers({
        ...base,
        application: { ...base.application, is_closed: true, is_editable: false },
      }),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/consents`), () =>
        HttpResponse.json({ items: [consentFixture()], pending_required: ["DATA_PROCESSING"] }),
      ),
    );
    renderConsents();
    expect(await screen.findByRole("button", { name: "Acepto" })).toBeDisabled();
  });

  it("si la lista falla, muestra el error con Reintentar", async () => {
    server.use(
      ...portalHandlers(sessionFixture({ pending_consents: ["DATA_PROCESSING"] })),
      http.get(apiUrl(`/buyer/applications/${APP_ID}/consents`), () =>
        apiError(404, "RESOURCE_NOT_FOUND", "No existe."),
      ),
    );
    renderConsents();
    expect(await screen.findByText("No existe.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("utilidades", () => {
  const now = Date.parse("2026-11-17T10:00:00Z");

  it("remainingText: horas, minutos y vencido", () => {
    expect(remainingText("2026-11-18T07:30:00Z", now)).toBe("21 horas");
    expect(remainingText("2026-11-17T11:10:00Z", now)).toBe("1 hora");
    expect(remainingText("2026-11-17T10:30:00Z", now)).toBe("30 minutos");
    expect(remainingText("2026-11-17T10:00:20Z", now)).toBe("1 minuto");
    expect(remainingText("2026-11-17T09:00:00Z", now)).toBeNull();
    expect(remainingText("no es fecha", now)).toBeNull();
  });

  it("iniciales y primer nombre", () => {
    expect(initials("Sofía Herrera Gómez")).toBe("SG");
    expect(initials("Sofía")).toBe("S");
    expect(firstName("  Sofía Herrera ")).toBe("Sofía");
  });
});
