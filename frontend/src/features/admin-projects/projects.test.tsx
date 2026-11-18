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
import { actionsFor } from "@/features/admin-projects/actions";
import { parseProjectsParams, PROJECTS_DEFAULTS } from "@/features/admin-projects/list-params";
import { canEditProject } from "@/features/admin-projects/project-panel";
import { ProjectsScreen } from "@/features/admin-projects/projects-screen";
import type { Project, ProjectDetail } from "@/features/admin-projects/queries";
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
    usePathname: () => "/proyectos",
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

const PARTNER_ID = "20000000-0000-4000-8000-000000000001";
const ADVISOR = [
  "projects.read",
  "projects.create",
  "projects.update",
  "projects.submit",
  "projects.approve",
  "partners.read",
];
const PARTNER_USER = ["projects.read", "projects.create", "projects.update", "projects.submit"];

function makeProject(n: number, overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: `40000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    partner: { id: PARTNER_ID, name: "Andina" },
    name: `Torres ${n}`,
    code: n === 1 ? "TR-1" : null,
    status: "DRAFT",
    city: {
      code: "05001",
      label: "Medellín",
      department_code: "05",
      department_label: "Antioquia",
    },
    address: `Calle ${n} # 10-20`,
    description: "",
    estimated_delivery_date: "2027-06-30",
    created_by: { id: "u-1", name: "Rosa Díaz" },
    validated_by: null,
    validated_at: null,
    created_at: "2026-11-10T15:00:00Z",
    updated_at: "2026-11-12T15:00:00Z",
    available_actions: [],
    ...overrides,
  };
}

const PROJECTS = [
  makeProject(1, { available_actions: ["SUBMIT_FOR_REVIEW", "APPROVE_DRAFT", "ARCHIVE_DRAFT"] }),
  makeProject(2, {
    status: "PENDING_REVIEW",
    available_actions: ["APPROVE", "REJECT", "ARCHIVE_PENDING"],
  }),
  makeProject(3, { status: "ARCHIVED" }),
];

function useApi({
  permissions = ADVISOR,
  partnerId = null as string | null,
  projects = PROJECTS,
} = {}) {
  const calls = { lists: [] as URLSearchParams[], writes: [] as WriteCall[] };
  const find = (id: string) => projects.find((p) => p.id === id);
  const toList = (p: ProjectDetail): Project => {
    const { available_actions: _actions, ...rest } = p;
    void _actions;
    return rest;
  };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions, partnerId))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(ADMIN_BOOTSTRAP)),
    http.get(apiUrl("/metadata/catalogs/municipality"), () => HttpResponse.json(MUNICIPALITIES)),
    http.get(apiUrl("/partners"), () =>
      HttpResponse.json(
        page(
          [
            {
              id: PARTNER_ID,
              legal_name: "Constructora Andina S.A.S.",
              trade_name: "Andina",
              tax_id: "900",
              status: "ACTIVE",
              contact_name: "",
              contact_email: "",
              contact_phone: "",
              created_at: "2026-11-01T15:00:00Z",
              updated_at: "2026-11-01T15:00:00Z",
            },
          ],
          new URLSearchParams(""),
        ),
      ),
    ),
    http.get(apiUrl("/projects"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.lists.push(query);
      return HttpResponse.json(page(projects.map(toList), query));
    }),
    http.get(apiUrl("/projects/:id"), ({ params }) => {
      const project = find(String(params.id));
      return project
        ? HttpResponse.json(project)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.post(apiUrl("/projects"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makeProject(9), { status: 201 });
    }),
    http.patch(apiUrl("/projects/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(find(String(params.id)));
    }),
    http.post(apiUrl("/projects/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      const status = {
        submit: "PENDING_REVIEW",
        activate: "ACTIVE",
        reject: "DRAFT",
        archive: "ARCHIVED",
      }[String(params.action)];
      return HttpResponse.json({ ...find(String(params.id))!, status, available_actions: [] });
    }),
  );
  return calls;
}

function go(search: string) {
  window.history.replaceState(null, "", `/proyectos${search}`);
}

async function renderScreen() {
  const user = userEvent.setup();
  renderWithProviders(<ProjectsScreen />);
  await screen.findAllByText("Torres 1");
  // Con el catálogo de estados, las celdas se vuelven a pintar.
  await screen.findAllByText("En validación");
  return user;
}

beforeEach(() => setMobile(false));

describe("reglas de proyectos", () => {
  it("parámetros de la URL", () => {
    expect(parseProjectsParams(new URLSearchParams(""))).toEqual(PROJECTS_DEFAULTS);
    expect(
      parseProjectsParams(
        new URLSearchParams(
          `status=ACTIVE&partner=${PARTNER_ID}&city=05001&ordering=name&proyecto=x`,
        ),
      ),
    ).toMatchObject({
      status: "ACTIVE",
      partner: PARTNER_ID,
      city: "05001",
      ordering: "name",
      proyecto: "",
    });
    expect(parseProjectsParams(new URLSearchParams("status=X&partner=y"))).toMatchObject({
      status: "",
      partner: "",
    });
  });

  it("acciones: en el orden de la API, sin repetir y sin códigos desconocidos", () => {
    expect(
      actionsFor(["APPROVE", "REJECT", "ARCHIVE_PENDING", "ARCHIVE_ACTIVE", "OTRA"]).map(
        (a) => a.endpoint,
      ),
    ).toEqual(["activate", "reject", "archive"]);
  });

  it("editar: no archivados; la constructora solo en borrador", () => {
    const admin = { canEdit: true, partnerScoped: false };
    const partner = { canEdit: true, partnerScoped: true };
    expect(canEditProject(PROJECTS[1]!, admin)).toBe(true);
    expect(canEditProject(PROJECTS[2]!, admin)).toBe(false);
    expect(canEditProject(PROJECTS[0]!, partner)).toBe(true);
    expect(canEditProject(PROJECTS[1]!, partner)).toBe(false);
    expect(canEditProject(PROJECTS[0]!, { canEdit: false, partnerScoped: false })).toBe(false);
  });
});

describe("proyectos", { timeout: 20_000 }, () => {
  it("lista con constructora, municipio y estado del catálogo; filtra en la URL", async () => {
    const calls = useApi();
    const user = await renderScreen();
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual([
      "Proyecto↕",
      "Constructora",
      "Municipio",
      "Estado↕",
      "Entrega estimada↕",
      "Actualizado↕",
    ]);
    const row = screen.getByRole("link", { name: "Torres 1" }).closest("tr")!;
    expect(within(row).getByText("TR-1")).toBeInTheDocument();
    expect(within(row).getByText("Andina")).toBeInTheDocument();
    expect(within(row).getByText("Borrador")).toBeInTheDocument();
    expect(within(row).getByText("30 jun 2027")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por constructora" }));
    await user.click(await screen.findByTitle("Andina"));
    await waitFor(() => expect(calls.lists.at(-1)?.get("partner_id")).toBe(PARTNER_ID));
    await user.click(screen.getByRole("button", { name: /Entrega estimada/ }));
    await waitFor(() =>
      expect(window.location.search).toContain("ordering=-estimated_delivery_date"),
    );
  });

  it("en validación: aprobar es la principal; rechazar pide motivo", async () => {
    const calls = useApi();
    go(`?proyecto=${PROJECTS[1]!.id}`);
    const user = await renderScreen();
    const panel = await dialog("Torres 2");
    expect(within(panel).getByRole("button", { name: "Aprobar" })).toHaveClass("ant-btn-primary");
    expect(within(panel).getByRole("button", { name: "Archivar" })).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Rechazar" }));
    const modal = await dialog("Rechazar proyecto");
    await user.click(within(modal).getByRole("button", { name: "Rechazar" }));
    expect(await within(modal).findByText("Escribe el motivo.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Motivo"), "Falta la licencia");
    await user.click(within(modal).getByRole("button", { name: /Rechazar/ }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/projects/${PROJECTS[1]!.id}/reject`,
        body: { reason: "Falta la licencia" },
      }),
    );
    expect(await screen.findByText("Proyecto devuelto a borrador")).toBeInTheDocument();
  });

  it("aprobar con motivo opcional manda `activate`", async () => {
    const calls = useApi();
    go(`?proyecto=${PROJECTS[1]!.id}`);
    const user = await renderScreen();
    await user.click(within(await dialog("Torres 2")).getByRole("button", { name: "Aprobar" }));
    const modal = await dialog("Aprobar proyecto");
    await user.click(within(modal).getByRole("button", { name: "Aprobar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/projects/${PROJECTS[1]!.id}/activate`,
        body: {},
      }),
    );
  });

  it("la constructora: sin columna ni filtro de constructora; envía a validación", async () => {
    const calls = useApi({ permissions: PARTNER_USER, partnerId: PARTNER_ID });
    go(`?proyecto=${PROJECTS[0]!.id}`);
    const user = await renderScreen();
    expect(screen.queryByRole("columnheader", { name: "Constructora" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Filtrar por constructora" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Los proyectos de tu constructora y su validación."),
    ).toBeInTheDocument();

    const panel = await dialog("Torres 1");
    await user.click(within(panel).getByRole("button", { name: "Enviar a validación" }));
    const modal = await dialog("Enviar a validación");
    await user.click(within(modal).getByRole("button", { name: "Enviar a validación" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/projects/${PROJECTS[0]!.id}/submit`,
        body: {},
      }),
    );
  });

  it("archivado: sin acciones ni editar", async () => {
    useApi();
    go(`?proyecto=${PROJECTS[2]!.id}`);
    await renderScreen();
    const panel = await dialog("Torres 3");
    expect(within(panel).queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Archivar" })).not.toBeInTheDocument();
  });

  it("crear (asesor): pide constructora, municipio y dirección; nombre duplicado al campo", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Nuevo proyecto" }));
    const modal = await dialog("Nuevo proyecto");
    await user.click(within(modal).getByRole("button", { name: "Crear proyecto" }));
    expect(await within(modal).findByText("Escribe el nombre.")).toBeInTheDocument();
    expect(within(modal).getByText("Elige la constructora.")).toBeInTheDocument();
    expect(within(modal).getByText("Elige el municipio.")).toBeInTheDocument();
    expect(within(modal).getByText("Escribe la dirección.")).toBeInTheDocument();

    await user.type(within(modal).getByLabelText("Nombre"), "Parque Norte");
    await user.click(within(modal).getByRole("combobox", { name: "Constructora" }));
    await user.click(await screen.findByTitle("Andina"));
    await user.click(within(modal).getByRole("combobox", { name: "Municipio" }));
    await user.click(await screen.findByTitle("Medellín (Antioquia)"));
    await user.type(within(modal).getByLabelText("Dirección"), "Cra 1 # 2-3");

    server.use(
      http.post(
        apiUrl("/projects"),
        () =>
          HttpResponse.json(
            apiError("DUPLICATE_PROJECT_NAME", "Ya hay un proyecto con ese nombre."),
            {
              status: 409,
            },
          ),
        { once: true },
      ),
    );
    await user.click(within(modal).getByRole("button", { name: "Crear proyecto" }));
    expect(
      await within(modal).findByText("Ya hay un proyecto con ese nombre."),
    ).toBeInTheDocument();

    await user.click(within(modal).getByRole("button", { name: /Crear proyecto/ }));
    expect(await screen.findByText("Proyecto creado")).toBeInTheDocument();
    expect(calls.writes.at(-1)).toEqual({
      method: "POST",
      path: "/api/v1/projects",
      body: {
        name: "Parque Norte",
        code: null,
        city_code: "05001",
        address: "Cra 1 # 2-3",
        description: "",
        estimated_delivery_date: null,
        partner_id: PARTNER_ID,
      },
    });
    await waitFor(() =>
      expect(window.location.search).toContain("proyecto=40000000-0000-4000-8000-000000000009"),
    );
  });

  it("editar manda solo lo cambiado", async () => {
    const calls = useApi();
    go(`?proyecto=${PROJECTS[0]!.id}`);
    const user = await renderScreen();
    await user.click(within(await dialog("Torres 1")).getByRole("button", { name: "Editar" }));
    const modal = await dialog("Editar proyecto");
    expect(within(modal).queryByRole("combobox", { name: "Constructora" })).not.toBeInTheDocument();
    await user.clear(within(modal).getByLabelText(/Código/));
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/projects/${PROJECTS[0]!.id}`,
        body: { code: null },
      }),
    );
  });

  it("vacío con filtros y proyecto ajeno", async () => {
    useApi({ projects: [] });
    go("?status=ACTIVE&proyecto=40000000-0000-4000-8000-000000000777");
    renderWithProviders(<ProjectsScreen />);
    expect(await screen.findByText("No hay proyectos con estos filtros")).toBeInTheDocument();
    expect(await screen.findByText("Este proyecto no existe o no es tuyo")).toBeInTheDocument();
  });

  it("en móvil, tarjetas", async () => {
    setMobile(true);
    useApi();
    renderWithProviders(<ProjectsScreen />);
    const list = await screen.findByRole("list", { name: "Proyectos" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getAllByText("Andina · Medellín")).toHaveLength(3);
  });
});
