import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AcceptInvitationScreen } from "@/features/admin-users/accept-invitation-screen";
import { apiError } from "@/features/admin-users/admin-users.fixtures";
import { apiUrl, server } from "@/test/msw-server";
import { ThemeProvider } from "@/providers/theme-provider";
import { renderWithProviders } from "@/test/render";

function open(search: string) {
  window.history.replaceState(null, "", `/aceptar-invitacion${search}`);
  const user = userEvent.setup();
  renderWithProviders(
    <ThemeProvider initialMode="light" hasCookie>
      <AcceptInvitationScreen />
    </ThemeProvider>,
  );
  return user;
}

async function fill(user: ReturnType<typeof userEvent.setup>, password = "Clave-Segura-2026") {
  await user.type(await screen.findByLabelText("Nombre"), "Laura");
  await user.type(screen.getByLabelText("Apellido"), "Gómez");
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.type(screen.getByLabelText("Repite la contraseña"), password);
  await user.click(screen.getByRole("button", { name: "Activar mi cuenta" }));
}

describe("aceptar invitación", { timeout: 20_000 }, () => {
  it("quita el token de la URL y lo manda con el nombre y la contraseña", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/invitations/accept"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          id: "u-1",
          email: "laura@example.com",
          name: "Laura Gómez",
          roles: ["ADVISOR"],
        });
      }),
    );
    const user = open("?token=secreto-123");
    expect(await screen.findByRole("heading", { name: "Activa tu cuenta" })).toBeInTheDocument();
    expect(window.location.search).toBe("");
    expect(window.location.pathname).toBe("/aceptar-invitacion");

    await fill(user);
    expect(
      await screen.findByRole("heading", { name: "Tu cuenta está lista" }),
    ).toBeInTheDocument();
    expect(screen.getByText("laura@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
    expect(bodies).toEqual([
      {
        token: "secreto-123",
        first_name: "Laura",
        last_name: "Gómez",
        password: "Clave-Segura-2026",
        password_confirmation: "Clave-Segura-2026",
      },
    ]);
  });

  it("sin token: el enlace no es válido", async () => {
    open("");
    expect(
      await screen.findByRole("heading", { name: "Este enlace no es válido" }),
    ).toBeInTheDocument();
  });

  it("sin token según el servidor: el aviso sale en el primer render (PERF-08)", () => {
    window.history.replaceState(null, "", "/aceptar-invitacion");
    renderWithProviders(
      <ThemeProvider initialMode="light" hasCookie>
        <AcceptInvitationScreen hasToken={false} />
      </ThemeProvider>,
    );
    // Sin esperar efectos ni el formulario: es lo que pinta el servidor.
    expect(screen.getByRole("heading", { name: "Este enlace no es válido" })).toBeInTheDocument();
    expect(screen.queryByText("Abriendo tu invitación…")).toBeNull();
  });

  it("valida el formato antes de enviar", async () => {
    const user = open("?token=t");
    await user.click(await screen.findByRole("button", { name: "Activar mi cuenta" }));
    expect(await screen.findByText("Escribe tu nombre.")).toBeInTheDocument();
    expect(screen.getByText("Escribe una contraseña.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Contraseña"), "una");
    await user.type(screen.getByLabelText("Repite la contraseña"), "otra");
    await user.click(screen.getByRole("button", { name: "Activar mi cuenta" }));
    expect(await screen.findByText("Las contraseñas no coinciden.")).toBeInTheDocument();
  });

  it("vencida o usada: pantalla de la invitación que ya no sirve", async () => {
    server.use(
      http.post(apiUrl("/invitations/accept"), () =>
        HttpResponse.json(apiError("INVITATION_INVALID", "La invitación no es válida o venció."), {
          status: 400,
        }),
      ),
    );
    const user = open("?token=t");
    await fill(user);
    expect(
      await screen.findByRole("heading", { name: "Esta invitación ya no sirve" }),
    ).toBeInTheDocument();
    expect(screen.getByText("La invitación no es válida o venció.")).toBeInTheDocument();
    expect(screen.getByText(/Pídele una invitación nueva/)).toBeInTheDocument();
  });

  it("si ya tiene cuenta, lo manda al login", async () => {
    server.use(
      http.post(apiUrl("/invitations/accept"), () =>
        HttpResponse.json(apiError("USER_ALREADY_EXISTS", "Ya tienes una cuenta."), {
          status: 409,
        }),
      ),
    );
    const user = open("?token=t");
    await fill(user);
    expect(
      await screen.findByRole("heading", { name: "Ya tienes una cuenta" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("la política de contraseñas va debajo del campo", async () => {
    server.use(
      http.post(apiUrl("/invitations/accept"), () =>
        HttpResponse.json(
          apiError("VALIDATION_ERROR", "Datos inválidos.", [
            { field: "password", code: "password_too_short", message: "Muy corta." },
          ]),
          { status: 400 },
        ),
      ),
    );
    const user = open("?token=t");
    await fill(user, "corta");
    expect(await screen.findByText("Muy corta.")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("demasiados intentos: aviso con la espera", async () => {
    server.use(
      http.post(apiUrl("/invitations/accept"), () =>
        HttpResponse.json(apiError("RATE_LIMITED", "Demasiados intentos."), {
          status: 429,
          headers: { "Retry-After": "120" },
        }),
      ),
    );
    const user = open("?token=t");
    await fill(user);
    await waitFor(() => expect(screen.getByText("Demasiados intentos.")).toBeInTheDocument());
    expect(screen.getByText("Vuelve a intentarlo en 2 minutos.")).toBeInTheDocument();
  });
});
