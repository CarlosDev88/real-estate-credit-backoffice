import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ADMIN_BOOTSTRAP,
  apiError,
  dialog,
  meWith,
  MUNICIPALITIES,
  page,
  recordWrite,
  setMobile,
  type WriteCall,
} from "@/features/admin-common/test-kit";
import { parsePartnersParams, PARTNERS_DEFAULTS } from "@/features/admin-partners/list-params";
import { PartnersScreen } from "@/features/admin-partners/partners-screen";
import type { Membership, Partner, PartnerDetail } from "@/features/admin-partners/queries";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
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
    usePathname: () => "/admin/constructoras",
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

const ADMIN = [
  "partners.read",
  "partners.create",
  "partners.update",
  "partners.manage_status",
  "partner_members.read",
  "partner_members.create",
  "users.read",
];

function makePartner(n: number, overrides: Partial<Partner> = {}): Partner {
  return {
    id: `20000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    legal_name: `Constructora ${n} S.A.S.`,
    trade_name: `Marca ${n}`,
    tax_id: `90000000${n}`,
    status: "ACTIVE",
    status_label: "Activo",
    contact_name: `Contacto ${n}`,
    contact_email: `contacto${n}@example.com`,
    contact_phone: "",
    created_at: "2026-11-10T15:00:00Z",
    updated_at: "2026-11-10T15:00:00Z",
    ...overrides,
  };
}

const PARTNERS = [makePartner(1), makePartner(2, { trade_name: "", status: "INACTIVE" })];
const detail = (partner: Partner): PartnerDetail => ({
  ...partner,
  metrics: {
    projects_by_status: { DRAFT: 2, PENDING_REVIEW: 1, ACTIVE: 4, ARCHIVED: 0 },
    active_members: 3,
  },
});
const MEMBER: Membership = {
  id: "m-1",
  partner_id: PARTNERS[0]!.id,
  partner_name: "Marca 1",
  user: { id: "u-1", name: "Rosa Díaz", email: "rosa@example.com" },
  job_title: "Gerente",
  status: "ACTIVE",
  status_label: "Activo",
  started_at: "2026-10-01",
  ended_at: null,
  created_at: "2026-10-01T15:00:00Z",
  updated_at: "2026-10-01T15:00:00Z",
};

function useApi({ permissions = ADMIN, partners = PARTNERS } = {}) {
  const calls = { lists: [] as URLSearchParams[], writes: [] as WriteCall[] };
  const find = (id: string) => partners.find((p) => p.id === id);
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(ADMIN_BOOTSTRAP)),
    http.get(apiUrl("/metadata/catalogs/municipality"), () => HttpResponse.json(MUNICIPALITIES)),
    http.get(apiUrl("/partners"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.lists.push(query);
      return HttpResponse.json(page(partners, query));
    }),
    http.get(apiUrl("/partners/:id"), ({ params }) => {
      const partner = find(String(params.id));
      return partner
        ? HttpResponse.json(detail(partner))
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.get(apiUrl("/partners/:id/members"), ({ request }) =>
      HttpResponse.json(page([MEMBER], new URL(request.url).searchParams)),
    ),
    http.post(apiUrl("/partners"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makePartner(9), { status: 201 });
    }),
    http.patch(apiUrl("/partners/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(
        detail({ ...find(String(params.id))!, ...((await request.json()) as object) }),
      );
    }),
    http.post(apiUrl("/partners/:id/deactivate"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({ ...find(String(params.id))!, status: "INACTIVE" });
    }),
    http.post(apiUrl("/partners/:id/activate"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({ ...find(String(params.id))!, status: "ACTIVE" });
    }),
    http.post(apiUrl("/partners/:id/members"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      const body = (await request.json()) as { email?: string };
      return body.email
        ? HttpResponse.json({ id: "inv-1", email: body.email }, { status: 202 })
        : HttpResponse.json(MEMBER, { status: 201 });
    }),
    http.get(apiUrl("/users"), () =>
      HttpResponse.json(
        page(
          [
            {
              id: "30000000-0000-4000-8000-000000000001",
              name: "Luis Mora",
              email: "luis@example.com",
            },
          ],
          new URLSearchParams(""),
        ),
      ),
    ),
  );
  return calls;
}

function go(search: string) {
  window.history.replaceState(null, "", `/admin/constructoras${search}`);
}

async function renderScreen() {
  const user = userEvent.setup();
  renderWithProviders(<PartnersScreen />);
  await screen.findAllByText("Marca 1");
  return user;
}

beforeEach(() => setMobile(false));

describe("parámetros de /admin/constructoras", () => {
  it("lee la URL y descarta lo inválido", () => {
    expect(parsePartnersParams(new URLSearchParams(""))).toEqual(PARTNERS_DEFAULTS);
    expect(
      parsePartnersParams(
        new URLSearchParams("status=INACTIVE&city=05001&ordering=legal_name&constructora=x"),
      ),
    ).toMatchObject({
      status: "INACTIVE",
      city: "05001",
      ordering: "legal_name",
      constructora: "",
    });
    expect(parsePartnersParams(new URLSearchParams("status=X&ordering=tax_id"))).toMatchObject({
      status: "",
      ordering: "-created_at",
    });
  });
});

describe("constructoras", { timeout: 20_000 }, () => {
  it("lista con nombre comercial, NIT, contacto y estado; filtra en la URL", async () => {
    const calls = useApi();
    const user = await renderScreen();

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Constructora↕", "NIT", "Contacto", "Teléfono", "Estado", "Creada↓"]);
    const row = screen.getByRole("link", { name: "Marca 1" }).closest("tr")!;
    expect(within(row).getByText("Constructora 1 S.A.S.")).toBeInTheDocument();
    expect(within(row).getByText("contacto1@example.com")).toBeInTheDocument();
    // Sin nombre comercial, la razón social.
    expect(screen.getByRole("link", { name: "Constructora 2 S.A.S." })).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por estado" }));
    await user.click(await screen.findByTitle("Inactivo"));
    await waitFor(() => expect(window.location.search).toBe("?status=INACTIVE"));
    await waitFor(() => expect(calls.lists.at(-1)?.get("status")).toBe("INACTIVE"));

    await user.click(
      screen.getByRole("combobox", { name: "Filtrar por municipio de sus proyectos" }),
    );
    await user.click(await screen.findByTitle("Medellín (Antioquia)"));
    await waitFor(() => expect(calls.lists.at(-1)?.get("city_code")).toBe("05001"));
  });

  it("vacío y error", async () => {
    useApi({ partners: [] });
    go("?search=zzz");
    renderWithProviders(<PartnersScreen />);
    expect(await screen.findByText("No hay constructoras con estos filtros")).toBeInTheDocument();
  });

  it("crear: valida formato, NIT duplicado al campo, y abre el panel de la nueva", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Nueva constructora" }));
    const modal = await dialog("Nueva constructora");
    await user.type(within(modal).getByLabelText(/Correo del contacto/), "no-es-correo");
    await user.click(within(modal).getByRole("button", { name: "Crear constructora" }));
    expect(await within(modal).findByText("Escribe la razón social.")).toBeInTheDocument();
    expect(within(modal).getByText("Escribe el NIT.")).toBeInTheDocument();
    expect(within(modal).getByText("Escribe un correo válido.")).toBeInTheDocument();

    server.use(
      http.post(apiUrl("/partners"), () =>
        HttpResponse.json(apiError("DUPLICATE_TAX_ID", "Ya existe una constructora con ese NIT."), {
          status: 409,
        }),
      ),
    );
    await user.clear(within(modal).getByLabelText(/Correo del contacto/));
    await user.type(within(modal).getByLabelText("Razón social"), "Nueva S.A.S.");
    await user.type(within(modal).getByLabelText("NIT"), "900111222");
    await user.click(within(modal).getByRole("button", { name: "Crear constructora" }));
    expect(
      await within(modal).findByText("Ya existe una constructora con ese NIT."),
    ).toBeInTheDocument();

    // Sin el conflicto: se crea y se abre su panel.
    server.use(
      http.post(apiUrl("/partners"), async ({ request }) => {
        await recordWrite(calls.writes, request);
        return HttpResponse.json(makePartner(9), { status: 201 });
      }),
    );
    await user.clear(within(modal).getByLabelText("NIT"));
    await user.type(within(modal).getByLabelText("NIT"), "900111223");
    // En jsdom la animación de salida del ícono "loading" no termina: queda en el nombre.
    await user.click(within(modal).getByRole("button", { name: /Crear constructora/ }));
    expect(await screen.findByText("Constructora creada")).toBeInTheDocument();
    expect(calls.writes.at(-1)).toMatchObject({
      method: "POST",
      body: { legal_name: "Nueva S.A.S.", tax_id: "900111223", contact_email: "" },
    });
    await waitFor(() =>
      expect(window.location.search).toBe("?constructora=20000000-0000-4000-8000-000000000009"),
    );
  });

  it("panel: datos, métricas por estado (catálogo) y miembros", async () => {
    useApi();
    go(`?constructora=${PARTNERS[0]!.id}`);
    await renderScreen();
    const panel = await dialog("Marca 1");
    expect(within(panel).getByText("900000001")).toBeInTheDocument();
    expect(await within(panel).findByText("En validación")).toBeInTheDocument();
    expect(within(panel).getByText("Miembros activos").nextSibling).toHaveTextContent("3");
    const members = await within(panel).findByRole("list", { name: "Miembros" });
    expect(within(members).getByText("Rosa Díaz")).toBeInTheDocument();
    expect(within(members).getByText(/Gerente/)).toBeInTheDocument();
  });

  it("editar manda solo lo cambiado y no deja cambiar el NIT", async () => {
    const calls = useApi();
    go(`?constructora=${PARTNERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(within(await dialog("Marca 1")).getByRole("button", { name: "Editar" }));
    const modal = await dialog("Editar constructora");
    expect(within(modal).getByLabelText("NIT")).toBeDisabled();
    await user.type(within(modal).getByLabelText(/Teléfono del contacto/), "6041234567");
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/partners/${PARTNERS[0]!.id}`,
        body: { contact_phone: "6041234567" },
      }),
    );
  });

  it("desactivar pide motivo; activar no", async () => {
    const calls = useApi();
    go(`?constructora=${PARTNERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(within(await dialog("Marca 1")).getByRole("button", { name: "Desactivar" }));
    const modal = await dialog("Desactivar constructora");
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));
    expect(await within(modal).findByText("Escribe el motivo.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Motivo"), "Terminó el convenio");
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/partners/${PARTNERS[0]!.id}/deactivate`,
        body: { reason: "Terminó el convenio" },
      }),
    );
    expect(await screen.findByText("Constructora desactivada")).toBeInTheDocument();
  });

  it("agregar miembro por correo (202) y un usuario existente (201)", async () => {
    const calls = useApi();
    go(`?constructora=${PARTNERS[0]!.id}`);
    const user = await renderScreen();
    const panel = await dialog("Marca 1");
    await user.click(await within(panel).findByRole("button", { name: "Agregar miembro" }));
    let modal = await dialog("Agregar miembro");
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));
    expect(await within(modal).findByText("Escribe el correo.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Correo"), "nuevo@example.com");
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));
    expect(await screen.findByText("Invitación enviada")).toBeInTheDocument();
    expect(calls.writes).toContainEqual({
      method: "POST",
      path: `/api/v1/partners/${PARTNERS[0]!.id}/members`,
      body: { email: "nuevo@example.com", job_title: "" },
    });

    await user.click(within(panel).getByRole("button", { name: "Agregar miembro" }));
    modal = await dialog("Agregar miembro");
    await user.click(within(modal).getByRole("radio", { name: "Agregar un usuario existente" }));
    await user.click(within(modal).getByRole("button", { name: "Agregar miembro" }));
    expect(await within(modal).findByText("Elige el usuario.")).toBeInTheDocument();
    await user.click(within(modal).getByRole("combobox", { name: "Usuario" }));
    await user.click(await screen.findByTitle("Luis Mora · luis@example.com"));
    await user.type(within(modal).getByLabelText(/Cargo/), "Directora");
    await user.click(within(modal).getByRole("button", { name: "Agregar miembro" }));
    expect(await screen.findByText("Miembro agregado")).toBeInTheDocument();
    expect(calls.writes).toContainEqual({
      method: "POST",
      path: `/api/v1/partners/${PARTNERS[0]!.id}/members`,
      body: {
        user_id: "30000000-0000-4000-8000-000000000001",
        job_title: "Directora",
        started_at: null,
      },
    });
  });

  it("agregar miembro: el conflicto va debajo del correo", async () => {
    useApi();
    server.use(
      http.post(apiUrl("/partners/:id/members"), () =>
        HttpResponse.json(apiError("INVITATION_ALREADY_PENDING", "Ya tiene una invitación."), {
          status: 409,
        }),
      ),
    );
    go(`?constructora=${PARTNERS[0]!.id}`);
    const user = await renderScreen();
    await user.click(
      await within(await dialog("Marca 1")).findByRole("button", { name: "Agregar miembro" }),
    );
    const modal = await dialog("Agregar miembro");
    await user.type(within(modal).getByLabelText("Correo"), "nuevo@example.com");
    await user.click(within(modal).getByRole("button", { name: "Enviar invitación" }));
    expect(await within(modal).findByText("Ya tiene una invitación.")).toBeInTheDocument();
  });

  it("sin permisos de escritura: sin crear, editar ni miembros", async () => {
    useApi({ permissions: ["partners.read"] });
    go(`?constructora=${PARTNERS[0]!.id}`);
    await renderScreen();
    const panel = await dialog("Marca 1");
    expect(screen.queryByRole("button", { name: "Nueva constructora" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(within(panel).queryByText("Miembros", { selector: "h3" })).not.toBeInTheDocument();
  });

  it("una constructora que no existe", async () => {
    useApi();
    go("?constructora=20000000-0000-4000-8000-000000000777");
    await renderScreen();
    expect(await screen.findByText("Esta constructora ya no existe")).toBeInTheDocument();
  });

  it("en móvil, tarjetas", async () => {
    setMobile(true);
    useApi();
    await renderScreen();
    const list = screen.getByRole("list", { name: "Constructoras" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText(/NIT 900000001/)).toBeInTheDocument();
  });
});
