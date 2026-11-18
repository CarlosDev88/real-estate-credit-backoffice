import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUsersScreen } from "@/features/admin-users/admin-users-screen";
import {
  ADMIN_ME,
  ADMIN_PERMISSIONS,
  apiError,
  makeInvitation,
  makeUser,
  page,
  PARTNERS,
  ROLES,
} from "@/features/admin-users/admin-users.fixtures";
import type { Invitation, User } from "@/features/admin-users/queries";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

// Router de prueba: `replace` escribe en la URL de jsdom y avisa a `useSearchParams`.
const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
    notify,
    push: vi.fn(),
    replace: vi.fn((href: string) => {
      window.history.replaceState(null, "", href);
      notify();
    }),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useRouter: () => nav,
    usePathname: () => "/admin/usuarios",
    useSearchParams: () => {
      const search = useSyncExternalStore(
        (cb) => {
          nav.listeners.add(cb);
          return () => nav.listeners.delete(cb);
        },
        () => window.location.search,
      );
      return new URLSearchParams(search);
    },
  };
});

const USERS = Array.from({ length: 3 }, (_, i) => makeUser(i + 1));
USERS[1] = makeUser(2, {
  roles: ["CONSTRUCTION_PARTNER"],
  partner: { id: PARTNERS[0]!.id, name: "Andina" },
  status: "PENDING",
});
USERS[2] = makeUser(3, { status: "INACTIVE", last_login: "2026-11-12T15:00:00Z" });
const SELF = makeUser(9, { id: ADMIN_ME.id, name: "Admin Principal", roles: ["ADMIN"] });

interface Calls {
  users: URLSearchParams[];
  invitations: URLSearchParams[];
  bodies: { method: string; path: string; body: unknown }[];
}

function useApi({
  users = [...USERS, SELF],
  invitations = [
    makeInvitation(1),
    makeInvitation(2, { status: "EXPIRED" }),
    makeInvitation(3, { status: "ACCEPTED" }),
  ],
  permissions = ADMIN_PERMISSIONS,
}: { users?: User[]; invitations?: Invitation[]; permissions?: string[] } = {}): Calls {
  const calls: Calls = { users: [], invitations: [], bodies: [] };
  const record = async (request: Request) => {
    const text = await request.text();
    calls.bodies.push({
      method: request.method,
      path: new URL(request.url).pathname,
      body: text ? JSON.parse(text) : null,
    });
  };
  const find = (id: string) => users.find((u) => u.id === id);
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json({ ...ADMIN_ME, permissions })),
    http.get(apiUrl("/roles"), () =>
      HttpResponse.json(page(ROLES, new URLSearchParams("page_size=100"))),
    ),
    http.get(apiUrl("/users"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.users.push(query);
      const status = query.get("status");
      return HttpResponse.json(
        page(
          users.filter((u) => !status || u.status === status),
          query,
        ),
      );
    }),
    http.get(apiUrl("/users/:id"), ({ params }) => {
      const user = find(String(params.id));
      return user
        ? HttpResponse.json(user)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.patch(apiUrl("/users/:id"), async ({ request, params }) => {
      await record(request.clone());
      const body = (await request.json()) as Partial<User>;
      return HttpResponse.json({ ...find(String(params.id))!, ...body });
    }),
    http.put(apiUrl("/users/:id/roles"), async ({ request, params }) => {
      await record(request.clone());
      const body = (await request.json()) as { role_codes: string[] };
      return HttpResponse.json({ ...find(String(params.id))!, roles: body.role_codes });
    }),
    http.post(apiUrl("/users/:id/deactivate"), async ({ request, params }) => {
      await record(request);
      return HttpResponse.json({ ...find(String(params.id))!, status: "INACTIVE" });
    }),
    http.post(apiUrl("/users/:id/activate"), async ({ request, params }) => {
      await record(request);
      return HttpResponse.json({ ...find(String(params.id))!, status: "ACTIVE" });
    }),
    http.get(apiUrl("/invitations"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.invitations.push(query);
      return HttpResponse.json(page(invitations, query));
    }),
    http.post(apiUrl("/invitations/:id/resend"), async ({ request, params }) => {
      await record(request);
      return HttpResponse.json(makeInvitation(9, { id: String(params.id) }), { status: 201 });
    }),
    http.delete(apiUrl("/invitations/:id"), async ({ request }) => {
      await record(request);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(apiUrl("/partners"), () => HttpResponse.json(page(PARTNERS, new URLSearchParams("")))),
  );
  return calls;
}

const last = (list: URLSearchParams[]) => list[list.length - 1];

function setMobile(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matches && query.includes("max-width: 860px"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

function go(search: string) {
  window.history.replaceState(null, "", `/admin/usuarios${search}`);
}

async function renderScreen(waitFor = "Usuario Número 1") {
  const user = userEvent.setup();
  renderWithProviders(<AdminUsersScreen />);
  await screen.findAllByText(waitFor);
  // Con los roles, las celdas se vuelven a pintar: se espera a que lleguen.
  await screen.findAllByText("Asesor");
  return user;
}

const rowOf = (name: string) => screen.getByRole("link", { name }).closest("tr")!;
/**
 * Diálogo por su título. En las pruebas, Ant Design le da `id="test-id"` a todos sus
 * componentes, así que el nombre accesible (`aria-labelledby`) no sirve para buscarlo.
 */
async function dialog(name: string): Promise<HTMLElement> {
  const find = () =>
    screen
      .queryAllByRole("dialog")
      .find((d) =>
        within(d).queryByText(name, { selector: ".ant-modal-title, .ant-drawer-title, h2" }),
      );
  await waitFor(() => expect(find()).toBeDefined());
  return find()!;
}

beforeEach(() => {
  setMobile(false);
  nav.replace.mockClear();
});

describe("usuarios", { timeout: 20_000 }, () => {
  it("lista los usuarios con el nombre de sus roles, constructora y estado", async () => {
    const calls = useApi();
    await renderScreen();

    expect(screen.getByRole("heading", { name: "Usuarios", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Usuarios" })).toHaveAttribute("aria-selected", "true");
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual([
      "Nombre↕",
      "Correo↕",
      "Roles",
      "Constructora",
      "Estado",
      "Último ingreso↕",
      "Creado↓",
    ]);

    await waitFor(() =>
      expect(within(rowOf("Usuario Número 1")).getByText("Asesor")).toBeVisible(),
    );
    const partner = rowOf("Usuario Número 2");
    expect(within(partner).getByText("Constructora")).toBeInTheDocument();
    expect(within(partner).getByText("Andina")).toBeInTheDocument();
    expect(within(partner).getByText("Pendiente de definir contraseña")).toBeInTheDocument();
    expect(within(rowOf("Usuario Número 3")).getByText("Inactivo")).toBeInTheDocument();
    expect(within(rowOf("Usuario Número 1")).getByText("Nunca")).toBeInTheDocument();

    expect(last(calls.users)?.get("ordering")).toBe("-created_at");
    expect(last(calls.users)?.get("page_size")).toBe("20");
  });

  it("filtra por estado y ordena, en la URL", async () => {
    const calls = useApi();
    const user = await renderScreen();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por estado" }));
    await user.click(await screen.findByTitle("Inactivo"));
    await waitFor(() => expect(window.location.search).toBe("?status=INACTIVE"));
    await waitFor(() => expect(last(calls.users)?.get("status")).toBe("INACTIVE"));

    await user.click(screen.getByRole("button", { name: /Correo/ }));
    await waitFor(() => expect(window.location.search).toContain("ordering=-email"));

    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe("?ordering=-email"));
  });

  it("sin resultados con filtros, ofrece limpiarlos", async () => {
    useApi({ users: [] });
    go("?status=INACTIVE");
    const user = userEvent.setup();
    renderWithProviders(<AdminUsersScreen />);
    await screen.findByText("No hay usuarios con estos filtros");
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(await screen.findByText("Todavía no hay usuarios")).toBeInTheDocument();
  });

  it("error al cargar, con Reintentar", async () => {
    useApi();
    server.use(
      http.get(apiUrl("/users"), () =>
        HttpResponse.json(apiError("SERVER_ERROR", "Falló el servidor."), { status: 500 }),
      ),
    );
    renderWithProviders(<AdminUsersScreen />);
    expect(await screen.findByText("No pudimos cargar los usuarios")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("la fila abre el panel con el detalle, y se cierra", async () => {
    useApi();
    const user = await renderScreen();

    await user.click(within(rowOf("Usuario Número 2")).getByText("usuario2@example.com"));
    await waitFor(() => expect(window.location.search).toBe(`?usuario=${USERS[1]!.id}`));
    const panel = await dialog("Usuario Número 2");
    expect(within(panel).getByText("Constructora", { selector: "dt" })).toBeInTheDocument();
    expect(within(panel).getByText("Andina", { selector: "dd" })).toBeInTheDocument();
    // Pendiente de contraseña: se puede desactivar.
    expect(within(panel).getByRole("button", { name: "Desactivar" })).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("editar manda solo lo que cambió", async () => {
    const calls = useApi();
    go(`?usuario=${USERS[0]!.id}`);
    const user = await renderScreen();
    const panel = await dialog("Usuario Número 1");
    await user.click(within(panel).getByRole("button", { name: "Editar" }));

    const modal = await dialog("Editar usuario");
    const phone = within(modal).getByLabelText(/Teléfono/);
    await user.type(phone, "3001234567");
    const last = within(modal).getByLabelText("Apellido");
    await user.clear(last);
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    expect(await within(modal).findByText("Escribe el apellido.")).toBeInTheDocument();
    await user.type(last, "Pérez");
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));

    await waitFor(() =>
      expect(calls.bodies).toContainEqual({
        method: "PATCH",
        path: `/api/v1/users/${USERS[0]!.id}`,
        body: { last_name: "Pérez", phone: "3001234567" },
      }),
    );
    expect(await screen.findByText("Datos guardados")).toBeInTheDocument();
  });

  it("editar: el error de la API va a su campo", async () => {
    useApi();
    server.use(
      http.patch(apiUrl("/users/:id"), () =>
        HttpResponse.json(
          apiError("VALIDATION_ERROR", "Datos inválidos.", [
            { field: "phone", code: "invalid", message: "Teléfono inválido." },
          ]),
          { status: 400 },
        ),
      ),
    );
    go(`?usuario=${USERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(
      within(await dialog("Usuario Número 1")).getByRole("button", { name: "Editar" }),
    );
    const modal = await dialog("Editar usuario");
    await user.type(within(modal).getByLabelText(/Teléfono/), "x");
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    expect(await within(modal).findByText("Teléfono inválido.")).toBeInTheDocument();
  });

  it("cambiar roles: al elegir constructora pide cuál, y manda `PUT`", async () => {
    const calls = useApi();
    go(`?usuario=${USERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(
      within(await dialog("Usuario Número 1")).getByRole("button", { name: "Cambiar roles" }),
    );
    const modal = await dialog("Cambiar roles");
    // Los roles inactivos no se ofrecen.
    expect(within(modal).queryByText("Rol antiguo")).not.toBeInTheDocument();
    const advisor = await within(modal).findByRole("checkbox", { name: /Asesor/ });
    expect(advisor).toBeChecked();

    await user.click(advisor);
    await user.click(within(modal).getByRole("button", { name: "Guardar roles" }));
    expect(await within(modal).findByText("Elige al menos un rol.")).toBeInTheDocument();

    await user.click(within(modal).getByRole("checkbox", { name: /Constructora/ }));
    await user.click(within(modal).getByRole("combobox", { name: "Constructora" }));
    await user.click(await screen.findByTitle("Andina"));
    await user.click(within(modal).getByRole("button", { name: "Guardar roles" }));

    await waitFor(() =>
      expect(calls.bodies).toContainEqual({
        method: "PUT",
        path: `/api/v1/users/${USERS[0]!.id}/roles`,
        body: { role_codes: ["CONSTRUCTION_PARTNER"], partner_id: PARTNERS[0]!.id },
      }),
    );
    expect(await screen.findByText("Roles actualizados")).toBeInTheDocument();
  });

  it("desactivar pide el motivo y confirma", async () => {
    const calls = useApi();
    go(`?usuario=${USERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(
      within(await dialog("Usuario Número 1")).getByRole("button", { name: "Desactivar" }),
    );
    const modal = await dialog("Desactivar usuario");
    expect(within(modal).getByText(/pierde el acceso de inmediato/)).toBeInTheDocument();
    const confirm = within(modal).getByRole("button", { name: "Desactivar" });
    await user.click(confirm);
    expect(await within(modal).findByText("Escribe el motivo.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Motivo"), "Ya no trabaja aquí");
    await user.click(confirm);

    await waitFor(() =>
      expect(calls.bodies).toContainEqual({
        method: "POST",
        path: `/api/v1/users/${USERS[0]!.id}/deactivate`,
        body: { reason: "Ya no trabaja aquí" },
      }),
    );
    expect(await screen.findByText("Usuario desactivado")).toBeInTheDocument();
  });

  it("activar un inactivo: motivo opcional", async () => {
    const calls = useApi();
    go(`?usuario=${USERS[2]!.id}`);
    const user = await renderScreen();
    await user.click(
      within(await dialog("Usuario Número 3")).getByRole("button", { name: "Activar" }),
    );
    const modal = await dialog("Activar usuario");
    await user.click(within(modal).getByRole("button", { name: "Activar" }));
    await waitFor(() =>
      expect(calls.bodies).toContainEqual({
        method: "POST",
        path: `/api/v1/users/${USERS[2]!.id}/activate`,
        body: {},
      }),
    );
  });

  it("en su propia cuenta no hay Desactivar", async () => {
    useApi();
    go(`?usuario=${SELF.id}`);
    await renderScreen();
    const panel = await dialog("Admin Principal");
    expect(within(panel).getByText(/Es tu cuenta/)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Desactivar" })).not.toBeInTheDocument();
  });

  it("un usuario que ya no existe muestra su error en el panel", async () => {
    useApi();
    go("?usuario=00000000-0000-4000-8000-000000000998");
    await renderScreen();
    expect(await screen.findByText("Este usuario ya no existe")).toBeInTheDocument();
  });

  it("sin permisos de escritura: el panel no tiene acciones ni hay Invitar", async () => {
    useApi({ permissions: ["users.read", "roles.read"] });
    go(`?usuario=${USERS[0]!.id}`);
    await renderScreen();
    const panel = await dialog("Usuario Número 1");
    expect(within(panel).queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Invitar usuario" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Invitaciones" })).not.toBeInTheDocument();
  });

  it("en móvil, tarjetas en lugar de tabla", async () => {
    setMobile(true);
    useApi();
    await renderScreen();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Usuarios" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "Filtros" })).toBeInTheDocument();
  });

  it("en móvil, los filtros van en una hoja y los activos se ven como chips", async () => {
    setMobile(true);
    useApi();
    go("?status=INACTIVE");
    const user = await renderScreen("Usuario Número 3");

    expect(screen.getByRole("button", { name: "Filtros (1)" })).toBeInTheDocument();
    const chips = screen.getByRole("list", { name: "Filtros activos" });
    expect(within(chips).getByText("Inactivo")).toBeInTheDocument();
    await user.click(within(chips).getByRole("button", { name: "Quitar filtro Estado: Inactivo" }));
    await waitFor(() => expect(window.location.search).toBe(""));

    await user.click(screen.getByRole("button", { name: "Filtros" }));
    const sheet = await dialog("Filtros");
    expect(within(sheet).getByRole("combobox", { name: "Filtrar por rol" })).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Ver resultados" }));
  });
});

describe("invitaciones", { timeout: 20_000 }, () => {
  it("la pestaña lista las invitaciones con sus acciones según el estado", async () => {
    const calls = useApi();
    go("?vista=invitaciones");
    await renderScreen("invitado1@example.com");

    expect(screen.getByRole("tab", { name: "Invitaciones" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(last(calls.invitations)?.get("ordering")).toBe("-created_at");
    const row = (email: string) => screen.getByText(email).closest("tr")!;
    expect(within(row("invitado1@example.com")).getByText("Pendiente")).toBeInTheDocument();
    expect(
      within(row("invitado1@example.com")).getByRole("button", { name: /Revocar/ }),
    ).toBeInTheDocument();
    // Vencida: se reenvía pero no se revoca. Aceptada: sin acciones.
    expect(
      within(row("invitado2@example.com")).getByRole("button", { name: /Reenviar/ }),
    ).toBeInTheDocument();
    expect(
      within(row("invitado2@example.com")).queryByRole("button", { name: /Revocar/ }),
    ).not.toBeInTheDocument();
    expect(within(row("invitado3@example.com")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("reenviar y revocar (con confirmación)", async () => {
    const calls = useApi();
    go("?vista=invitaciones");
    const user = await renderScreen("invitado1@example.com");
    const first = makeInvitation(1);

    await user.click(
      screen.getByRole("button", { name: "Reenviar la invitación de invitado1@example.com" }),
    );
    expect(await screen.findByText("Invitación reenviada")).toBeInTheDocument();
    expect(calls.bodies).toContainEqual({
      method: "POST",
      path: `/api/v1/invitations/${first.id}/resend`,
      body: null,
    });

    await user.click(
      screen.getByRole("button", { name: "Revocar la invitación de invitado1@example.com" }),
    );
    const modal = await dialog("Revocar invitación");
    await user.click(within(modal).getByRole("button", { name: "Revocar" }));
    await waitFor(() =>
      expect(calls.bodies).toContainEqual({
        method: "DELETE",
        path: `/api/v1/invitations/${first.id}`,
        body: null,
      }),
    );
    expect(await screen.findByText("Invitación revocada")).toBeInTheDocument();
  });

  it("cambiar de pestaña limpia los filtros de la otra", async () => {
    useApi();
    go("?status=INACTIVE&search=ana");
    const user = userEvent.setup();
    renderWithProviders(<AdminUsersScreen />);
    await user.click(await screen.findByRole("tab", { name: "Invitaciones" }));
    await waitFor(() => expect(window.location.search).toBe("?vista=invitaciones"));
  });

  it("invitar: valida el formato, pide constructora para ese rol y manda `POST`", async () => {
    const posts: unknown[] = [];
    useApi();
    server.use(
      http.post(apiUrl("/invitations"), async ({ request }) => {
        const body = (await request.json()) as { email: string };
        posts.push(body);
        return HttpResponse.json(makeInvitation(7, { email: body.email }), { status: 201 });
      }),
    );
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Invitar usuario" }));
    const modal = await dialog("Invitar usuario");
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));
    expect(await within(modal).findByText("Escribe el correo.")).toBeInTheDocument();
    expect(within(modal).getByText("Elige el rol.")).toBeInTheDocument();

    await user.type(within(modal).getByLabelText("Correo"), "nueva@example.com");
    await user.click(within(modal).getByRole("combobox", { name: "Rol" }));
    await user.click(await screen.findByTitle("Constructora"));
    await user.click(within(modal).getByRole("combobox", { name: "Constructora" }));
    await user.click(await screen.findByTitle("Andina"));
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));

    await waitFor(() =>
      expect(posts).toEqual([
        { email: "nueva@example.com", role: "CONSTRUCTION_PARTNER", partner_id: PARTNERS[0]!.id },
      ]),
    );
    expect(await screen.findByText("Invitación enviada")).toBeInTheDocument();
    // La invitación nueva se ve en su pestaña.
    await waitFor(() => expect(window.location.search).toBe("?vista=invitaciones"));
  });

  it("invitar: un correo que ya tiene cuenta queda debajo del campo", async () => {
    useApi();
    server.use(
      http.post(apiUrl("/invitations"), () =>
        HttpResponse.json(apiError("USER_ALREADY_EXISTS", "Ya existe un usuario con ese correo."), {
          status: 409,
        }),
      ),
    );
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Invitar usuario" }));
    const modal = await dialog("Invitar usuario");
    await user.type(within(modal).getByLabelText("Correo"), "usuario1@example.com");
    await user.click(within(modal).getByRole("combobox", { name: "Rol" }));
    await user.click(await screen.findByTitle("Asesor"));
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));
    expect(
      await within(modal).findByText("Ya existe un usuario con ese correo."),
    ).toBeInTheDocument();
    expect(within(modal).getByLabelText("Correo")).toHaveAttribute("aria-invalid", "true");
  });

  it("en móvil, tarjetas con sus acciones", async () => {
    setMobile(true);
    useApi();
    go("?vista=invitaciones");
    await renderScreen("invitado1@example.com");
    const list = screen.getByRole("list", { name: "Invitaciones" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(
      within(list).getByRole("button", { name: "Revocar la invitación de invitado1@example.com" }),
    ).toBeInTheDocument();
  });
});
