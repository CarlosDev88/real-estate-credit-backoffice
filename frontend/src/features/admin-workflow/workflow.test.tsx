import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  dialog,
  meWith,
  page,
  recordWrite,
  setMobile,
  type WriteCall,
} from "@/features/admin-common/test-kit";
import type { Transition } from "@/features/admin-workflow/queries";
import { parseTransitionsParams, WorkflowScreen } from "@/features/admin-workflow/workflow-screen";
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
    usePathname: () => "/admin/flujos",
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

const PERMISSIONS = ["workflow.read", "workflow.update", "workflow.publish", "roles.read"];

const item = (code: string, label: string, order: number) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active: true,
  parent_id: null,
  parent_code: null,
  metadata: {},
});
const BOOTSTRAP = {
  metadata_version: 1,
  actor: "ADMIN",
  permissions: [],
  catalogs: {
    project_status: [
      item("DRAFT", "Borrador", 1),
      item("PENDING_REVIEW", "En validación", 2),
      item("ACTIVE", "Activo", 3),
    ],
    application_status: [item("DRAFT", "Borrador", 1), item("FILED", "Radicada", 2)],
  },
  on_demand_catalogs: [],
  features: {},
};

function makeTransition(n: number, overrides: Partial<Transition> = {}): Transition {
  return {
    id: `c0000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    flow_type: "PROJECT",
    code: n === 1 ? "SUBMIT_FOR_REVIEW" : "APPROVE",
    from_status: n === 1 ? "DRAFT" : "PENDING_REVIEW",
    to_status: n === 1 ? "PENDING_REVIEW" : "ACTIVE",
    label: n === 1 ? "Enviar a validación" : "Aprobar",
    required_permission: n === 1 ? "projects.submit" : "projects.approve",
    guard_code: null,
    roles: n === 1 ? ["ADMIN", "CONSTRUCTION_PARTNER"] : ["ADVISOR"],
    is_active: n === 1,
    system_only: false,
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
    ...overrides,
  };
}
const TRANSITIONS = [makeTransition(1), makeTransition(2)];
const ROLES = [
  {
    id: "r1",
    code: "ADMIN",
    name: "Administrador",
    description: "",
    is_active: true,
    permissions: [],
  },
  { id: "r2", code: "ADVISOR", name: "Asesor", description: "", is_active: true, permissions: [] },
  {
    id: "r3",
    code: "CONSTRUCTION_PARTNER",
    name: "Constructora",
    description: "",
    is_active: true,
    permissions: [],
  },
];

function useApi() {
  const calls = { lists: [] as URLSearchParams[], writes: [] as WriteCall[] };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(PERMISSIONS))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/roles"), () =>
      HttpResponse.json(page(ROLES, new URLSearchParams("page_size=100"))),
    ),
    http.get(apiUrl("/workflow-transitions"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.lists.push(query);
      return HttpResponse.json(page(TRANSITIONS, query));
    }),
    http.patch(apiUrl("/workflow-transitions/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(TRANSITIONS.find((t) => t.id === params.id));
    }),
    http.post(apiUrl("/workflow-transitions/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(TRANSITIONS.find((t) => t.id === params.id));
    }),
  );
  return calls;
}

const go = (search: string) => window.history.replaceState(null, "", `/admin/flujos${search}`);

beforeEach(() => setMobile(false));

describe("flujos", { timeout: 20_000 }, () => {
  it("parámetros", () => {
    expect(parseTransitionsParams(new URLSearchParams("flujo=X&active=y"))).toMatchObject({
      flujo: "APPLICATION",
      active: "",
    });
  });

  it("listado por flujo con estados del catálogo y nombres de roles", async () => {
    const calls = useApi();
    go("?flujo=PROJECT");
    const user = userEvent.setup();
    renderWithProviders(<WorkflowScreen />);
    const row = (await screen.findByRole("button", { name: "Enviar a validación" })).closest("tr")!;
    await waitFor(() =>
      expect(within(row).getByText("Administrador, Constructora")).toBeInTheDocument(),
    );
    expect(within(row).getByText("Borrador")).toBeInTheDocument();
    expect(within(row).getByText("En validación")).toBeInTheDocument();
    expect(calls.lists.at(-1)?.get("flow_type")).toBe("PROJECT");

    await user.click(screen.getByRole("tab", { name: "Solicitudes de crédito" }));
    await waitFor(() => expect(window.location.search).toBe(""));
    await waitFor(() => expect(calls.lists.at(-1)?.get("flow_type")).toBe("APPLICATION"));
  });

  it("activa: no se edita hasta desactivarla", async () => {
    const calls = useApi();
    go(`?flujo=PROJECT&abierta=${TRANSITIONS[0]!.id}`);
    const user = userEvent.setup();
    renderWithProviders(<WorkflowScreen />);
    const panel = await dialog("Enviar a validación");
    expect(within(panel).getByText("Para editarla, desactívala primero")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Editar" })).toBeDisabled();
    await user.click(within(panel).getByRole("button", { name: "Desactivar" }));
    const confirm = await dialog("Desactivar Enviar a validación");
    await user.click(within(confirm).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/workflow-transitions/${TRANSITIONS[0]!.id}/deactivate`,
        body: null,
      }),
    );
  });

  it("inactiva: editar etiqueta y roles", async () => {
    const calls = useApi();
    go(`?flujo=PROJECT&abierta=${TRANSITIONS[1]!.id}`);
    const user = userEvent.setup();
    renderWithProviders(<WorkflowScreen />);
    const panel = await dialog("Aprobar");
    await user.click(within(panel).getByRole("button", { name: "Editar" }));
    const modal = await dialog("Editar APPROVE");
    const label = within(modal).getByLabelText("Etiqueta");
    await user.clear(label);
    await user.type(label, "Aprobar proyecto");
    await user.click(await within(modal).findByRole("checkbox", { name: "Administrador" }));
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/workflow-transitions/${TRANSITIONS[1]!.id}`,
        body: { label: "Aprobar proyecto", roles: ["ADVISOR", "ADMIN"] },
      }),
    );
  });

  it("en móvil, tarjetas", async () => {
    setMobile(true);
    useApi();
    go("?flujo=PROJECT");
    renderWithProviders(<WorkflowScreen />);
    const list = await screen.findByRole("list", { name: "Transiciones" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});
