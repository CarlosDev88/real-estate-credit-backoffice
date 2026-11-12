import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackofficeGuard } from "@/features/auth/backoffice-guard";
import { LoginScreen } from "@/features/auth/login-screen";
import type * as Navigation from "@/lib/api/navigation";
import { redirectTo } from "@/lib/api/navigation";
import { setAuthFailureHandler } from "@/lib/api/session";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";
import { ThemeProvider } from "@/providers/theme-provider";

const router = vi.hoisted(() => ({ replace: vi.fn(), pathname: "/solicitudes" }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => router.pathname,
}));
vi.mock("@/lib/api/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof Navigation>()),
  redirectTo: vi.fn(),
}));

const ME = {
  id: "u-1",
  name: "Asesora Pruebas E2E",
  email: "asesor@example.com",
  role: "ADVISOR",
  roles: ["ADVISOR"],
  permissions: ["applications.read"],
  scope: { assigned_applications_only: true, partner_id: null },
};
const unauthorized = () =>
  HttpResponse.json(
    { code: "NOT_AUTHENTICATED", message: "x", details: [], request_id: null },
    { status: 401 },
  );

function withTheme(ui: React.ReactElement) {
  return (
    <ThemeProvider initialMode="light" hasCookie>
      {ui}
    </ThemeProvider>
  );
}

beforeEach(() => {
  router.replace.mockReset();
  router.pathname = "/solicitudes";
  vi.mocked(redirectTo).mockReset();
  setAuthFailureHandler(null);
});

describe("BackofficeGuard", () => {
  it("con sesión pinta el shell con el menú que dan los permisos", async () => {
    server.use(http.get(apiUrl("/auth/me"), () => HttpResponse.json(ME)));
    renderWithProviders(withTheme(<BackofficeGuard>contenido</BackofficeGuard>));

    expect(screen.getByRole("status")).toHaveTextContent("Cargando…");
    expect(await screen.findByRole("link", { name: "Solicitudes" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("main")).toHaveTextContent("contenido");
  });

  it("sin el permiso de la ruta lleva al destino por defecto", async () => {
    server.use(http.get(apiUrl("/auth/me"), () => HttpResponse.json({ ...ME, permissions: [] })));
    renderWithProviders(withTheme(<BackofficeGuard>contenido</BackofficeGuard>));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/sin-modulos"));
  });

  it("si /auth/me falla por otra razón, muestra el error con Reintentar", async () => {
    server.use(
      http.get(apiUrl("/auth/me"), () =>
        HttpResponse.json(
          { code: "BOOM", message: "Algo falló.", details: [], request_id: "r" },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(withTheme(<BackofficeGuard>contenido</BackofficeGuard>));
    expect(
      await screen.findByRole("heading", { name: "No pudimos cargar tu sesión" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Algo falló.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("logout: si sale bien recarga en /login; si falla, avisa y se queda", async () => {
    let logoutOk = false;
    server.use(
      http.get(apiUrl("/auth/me"), () => HttpResponse.json(ME)),
      http.post(apiUrl("/auth/logout"), () =>
        logoutOk
          ? new HttpResponse(null, { status: 204 })
          : HttpResponse.json(
              {
                code: "CSRF_FAILED",
                message: "Falta el token CSRF.",
                details: [],
                request_id: "r",
              },
              { status: 403 },
            ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(withTheme(<BackofficeGuard>contenido</BackofficeGuard>));

    const account = await screen.findByRole("button", { name: /Asesora Pruebas E2E/ });
    await user.click(account);
    await user.click(await screen.findByRole("menuitem", { name: "Cerrar sesión" }));
    expect(await screen.findByText("Falta el token CSRF.")).toBeInTheDocument();
    expect(redirectTo).not.toHaveBeenCalled();

    logoutOk = true;
    await user.click(account);
    await user.click(await screen.findByRole("menuitem", { name: "Cerrar sesión" }));
    await waitFor(() => expect(redirectTo).toHaveBeenCalledWith("/login"));
  });
});

describe("LoginScreen", () => {
  it("con sesión válida lleva al destino (next visible)", async () => {
    server.use(http.get(apiUrl("/auth/me"), () => HttpResponse.json(ME)));
    renderWithProviders(withTheme(<LoginScreen next="/solicitudes/abc" />));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/solicitudes/abc"));
  });

  it("sin sesión muestra el formulario y no redirige", async () => {
    server.use(
      http.get(apiUrl("/auth/me"), unauthorized),
      http.post(apiUrl("/auth/refresh"), unauthorized),
    );
    window.history.replaceState(null, "", "/login");
    renderWithProviders(withTheme(<LoginScreen next={null} />));
    expect(screen.getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.getByText("¿Estás comprando vivienda?")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(router.replace).not.toHaveBeenCalled();
    expect(redirectTo).not.toHaveBeenCalled();
  });

  it("al ingresar ignora un next externo", async () => {
    server.use(
      http.get(apiUrl("/auth/me"), unauthorized),
      http.post(apiUrl("/auth/refresh"), unauthorized),
      http.post(apiUrl("/auth/login"), () =>
        HttpResponse.json({
          user: { id: "u-1", name: "A", email: "a@example.com", role: "ADVISOR" },
          permissions: ["applications.read"],
          session_expires_at: "2026-11-12T23:00:00Z",
        }),
      ),
    );
    window.history.replaceState(null, "", "/login");
    const user = userEvent.setup();
    renderWithProviders(withTheme(<LoginScreen next="https://evil.example/solicitudes" />));
    await user.type(screen.getByLabelText("Correo", { exact: true }), "a@example.com");
    await user.type(screen.getByLabelText("Contraseña", { exact: true }), "secreta");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/solicitudes"));
  });
});
