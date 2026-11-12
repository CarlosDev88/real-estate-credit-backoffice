import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/login-form";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

const error = (status: number, code: string, message: string, extra: object = {}) =>
  HttpResponse.json({ code, message, details: [], request_id: "req-1", ...extra }, { status });

async function fill(email: string, password: string) {
  const user = userEvent.setup();
  if (email) await user.type(screen.getByLabelText("Correo"), email);
  if (password) await user.type(screen.getByLabelText("Contraseña"), password);
  await user.click(screen.getByRole("button", { name: "Ingresar" }));
  return user;
}

describe("LoginForm", () => {
  it("valida en el cliente y enlaza el error con aria-describedby", async () => {
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);
    await fill("no-es-correo", "");

    const email = screen.getByLabelText("Correo");
    expect(await screen.findByText("Escribe un correo válido.")).toHaveAttribute(
      "id",
      "email-error",
    );
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAttribute("aria-describedby", "email-error");
    expect(screen.getByText("Escribe tu contraseña.")).toBeInTheDocument();
  });

  it("con credenciales inválidas muestra el aviso y marca los dos campos", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), () =>
        error(401, "INVALID_CREDENTIALS", "El correo o la contraseña no son correctos."),
      ),
    );
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);
    await fill("ana@example.com", "mala");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("El correo o la contraseña no son correctos.");
    expect(alert).toHaveTextContent("Tras 5 intentos fallidos el acceso se bloquea 15 minutos.");
    for (const label of ["Correo", "Contraseña"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByLabelText(label)).toHaveAttribute("aria-describedby", "login-error");
    }
  });

  it("con 429 dice en cuántos minutos volver a intentar", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), () =>
        HttpResponse.json(
          { code: "RATE_LIMITED", message: "Demasiados intentos.", details: [], request_id: null },
          { status: 429, headers: { "Retry-After": "840" } },
        ),
      ),
    );
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);
    await fill("ana@example.com", "x");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demasiados intentos.Vuelve a intentarlo en 14 minutos.",
    );
  });

  it("con USER_INACTIVE muestra solo el mensaje de la API", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), () =>
        error(403, "USER_INACTIVE", "Tu usuario está inactivo."),
      ),
    );
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);
    await fill("ana@example.com", "x");

    expect(await screen.findByRole("alert")).toHaveTextContent(/^Tu usuario está inactivo\.$/);
    expect(screen.getByLabelText("Correo")).toHaveAttribute("aria-invalid", "false");
  });

  it("lleva los details[].field de la API a su campo", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), () =>
        error(400, "VALIDATION_ERROR", "Datos inválidos.", {
          details: [{ field: "email", code: "invalid", message: "Introduzca un correo válido." }],
        }),
      ),
    );
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);
    await fill("ana@example.com", "x");

    expect(await screen.findByText("Introduzca un correo válido.")).toHaveAttribute(
      "id",
      "email-error",
    );
  });

  it("al ingresar entrega la respuesta del login y alterna la contraseña visible", async () => {
    const onSuccess = vi.fn();
    server.use(
      http.post(apiUrl("/auth/login"), async ({ request }) => {
        expect(await request.json()).toEqual({ email: "ana@example.com", password: "secreta" });
        return HttpResponse.json({
          user: { id: "u-1", name: "Ana", email: "ana@example.com", role: "ADVISOR" },
          permissions: ["applications.read"],
          session_expires_at: "2026-11-12T23:00:00Z",
        });
      }),
    );
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);
    const user = await fill("ana@example.com", "secreta");

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(onSuccess.mock.calls[0]?.[0]).toMatchObject({ permissions: ["applications.read"] });

    const toggle = screen.getByRole("button", { name: "Mostrar contraseña" });
    await user.click(toggle);
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Ocultar contraseña" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
