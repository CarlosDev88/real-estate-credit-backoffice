import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiError,
  dialog,
  meWith,
  page,
  recordWrite,
  setMobile,
  type WriteCall,
} from "@/features/admin-common/test-kit";
import { DocumentsScreen } from "@/features/admin-documents/documents-screen";
import { DOCUMENTS_DEFAULTS, parseDocumentsParams } from "@/features/admin-documents/list-params";
import type { DocumentType, Requirement } from "@/features/admin-documents/queries";
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
    usePathname: () => "/admin/documentos",
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

const PERMISSIONS = [
  "document_requirements.read",
  "document_requirements.create",
  "document_requirements.update",
  "document_requirements.publish",
];

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
    loan_purpose: [item("PURCHASE_NEW", "Compra de vivienda nueva", 1)],
    employment_profile: [item("EMPLOYEE", "Empleado", 1), item("INDEPENDENT", "Independiente", 2)],
    property_condition: [item("NEW", "Nuevo", 1)],
  },
  on_demand_catalogs: [],
  features: {},
};

function makeType(n: number, overrides: Partial<DocumentType> = {}): DocumentType {
  return {
    id: `80000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    code: n === 1 ? "CEDULA" : `TIPO_${n}`,
    name: n === 1 ? "Cédula de ciudadanía" : `Tipo ${n}`,
    description: "",
    allowed_mime_types: ["application/pdf", "image/jpeg"],
    max_size_bytes: 5 * 1024 * 1024,
    default_validity_days: null,
    is_repeatable: false,
    holder_scope: "PARTICIPANT",
    is_active: true,
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
    ...overrides,
  };
}
const TYPES = [makeType(1), makeType(2, { is_active: false, holder_scope: "APPLICATION" })];

const PRODUCT = {
  id: "60000000-0000-4000-8000-000000000001",
  code: "HIPO",
  name: "Hipotecario",
  bank: { id: "b-1", code: "BN", name: "Banco Uno", short_name: "BN1" },
};

function makeRequirement(version: number, overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: `90000000-0000-4000-8000-${String(version).padStart(12, "0")}`,
    bank_product: null,
    document_type: {
      id: TYPES[0]!.id,
      code: "CEDULA",
      name: "Cédula de ciudadanía",
      is_active: true,
    },
    purpose: null,
    employment_profile: null,
    participant_role: "PRIMARY",
    property_condition: null,
    version,
    is_required: true,
    is_waivable: false,
    minimum_files: 1,
    alternative_group_code: null,
    validity_days: null,
    sort_order: 10,
    status: version === 1 ? "ACTIVE" : "DRAFT",
    valid_from: "2026-11-01T15:00:00Z",
    valid_to: null,
    created_at: "2026-11-01T15:00:00Z",
    updated_at: "2026-11-01T15:00:00Z",
    ...overrides,
  };
}
const REQUIREMENTS = [
  makeRequirement(1),
  makeRequirement(2, {
    bank_product: PRODUCT,
    employment_profile: { code: "INDEPENDENT", label: "Independiente" },
    is_waivable: true,
    minimum_files: 3,
  }),
];

function useApi({ permissions = PERMISSIONS } = {}) {
  const calls = { writes: [] as WriteCall[], requirementLists: [] as URLSearchParams[] };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/document-types"), ({ request }) =>
      HttpResponse.json(page(TYPES, new URL(request.url).searchParams)),
    ),
    http.get(apiUrl("/document-types/:id"), ({ params }) =>
      HttpResponse.json(TYPES.find((t) => t.id === params.id)),
    ),
    http.post(apiUrl("/document-types"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makeType(9), { status: 201 });
    }),
    http.post(apiUrl("/document-types/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({ ...TYPES.find((t) => t.id === params.id)!, is_active: false });
    }),
    http.get(apiUrl("/bank-products"), () =>
      HttpResponse.json(page([PRODUCT], new URLSearchParams("page_size=100"))),
    ),
    http.get(apiUrl("/document-requirements"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.requirementLists.push(query);
      return HttpResponse.json(page(REQUIREMENTS, query));
    }),
    http.get(apiUrl("/document-requirements/:id"), ({ params }) => {
      const requirement = REQUIREMENTS.find((r) => r.id === params.id);
      return requirement
        ? HttpResponse.json(requirement)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.post(apiUrl("/document-requirements"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makeRequirement(5), { status: 201 });
    }),
    http.patch(apiUrl("/document-requirements/:id"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(REQUIREMENTS[1], { status: 201 });
    }),
    http.post(apiUrl("/document-requirements/preview"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({
        participants: [
          {
            index: 0,
            role: "PRIMARY",
            employment_profile: { code: "EMPLOYEE", label: "Empleado" },
            documents: [
              {
                requirement_id: REQUIREMENTS[0]!.id,
                version: 1,
                document_type: REQUIREMENTS[0]!.document_type,
                is_required: true,
                is_waivable: false,
                minimum_files: 1,
                alternative_group_code: null,
                validity_days: 30,
                sort_order: 10,
                is_general: true,
              },
            ],
          },
        ],
        application_requirements: [],
      });
    }),
    http.post(apiUrl("/document-requirements/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({
        ...REQUIREMENTS.find((r) => r.id === params.id)!,
        status: "ACTIVE",
      });
    }),
  );
  return calls;
}

const go = (search: string) => window.history.replaceState(null, "", `/admin/documentos${search}`);

beforeEach(() => setMobile(false));

describe("documentos", { timeout: 20_000 }, () => {
  it("parámetros por pestaña", () => {
    expect(parseDocumentsParams(new URLSearchParams(""))).toEqual(DOCUMENTS_DEFAULTS);
    expect(
      parseDocumentsParams(
        new URLSearchParams("vista=requisitos&product=general&role=PRIMARY&search=x&active=true"),
      ),
    ).toMatchObject({
      vista: "requisitos",
      product: "general",
      role: "PRIMARY",
      search: "",
      active: "",
    });
  });

  it("tipos: listado y nuevo tipo (MB → bytes, formatos)", async () => {
    const calls = useApi();
    const user = userEvent.setup();
    renderWithProviders(<DocumentsScreen />);
    const row = (await screen.findByRole("button", { name: "Cédula de ciudadanía" })).closest(
      "tr",
    )!;
    expect(within(row).getByText("PDF, JPG")).toBeInTheDocument();
    expect(within(row).getByText("5 MB")).toBeInTheDocument();
    expect(screen.getByText("Una vez por solicitud")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Nuevo tipo" }));
    const modal = await dialog("Nuevo tipo documental");
    await user.click(within(modal).getByRole("checkbox", { name: "PDF" }));
    await user.click(within(modal).getByRole("button", { name: "Crear tipo" }));
    expect(await within(modal).findByText("Elige al menos un formato.")).toBeInTheDocument();
    expect(within(modal).getByText("Escribe el código.")).toBeInTheDocument();

    await user.type(within(modal).getByLabelText("Código"), "EXTRACTO");
    await user.type(within(modal).getByLabelText("Nombre"), "Extracto bancario");
    await user.click(within(modal).getByRole("checkbox", { name: "PNG" }));
    const size = within(modal).getByLabelText("Tamaño máximo por archivo");
    await user.clear(size);
    await user.type(size, "2");
    await user.click(within(modal).getByRole("checkbox", { name: /más de una vez/ }));
    await user.click(within(modal).getByRole("button", { name: "Crear tipo" }));
    await waitFor(() =>
      expect(calls.writes.at(-1)).toEqual({
        method: "POST",
        path: "/api/v1/document-types",
        body: {
          code: "EXTRACTO",
          name: "Extracto bancario",
          description: "",
          allowed_mime_types: ["image/png"],
          max_size_bytes: 2 * 1024 * 1024,
          default_validity_days: null,
          is_repeatable: true,
          holder_scope: "PARTICIPANT",
        },
      }),
    );
  });

  it("tipos: panel y desactivar con motivo opcional", async () => {
    const calls = useApi();
    go(`?abierto=${TYPES[0]!.id}`);
    const user = userEvent.setup();
    renderWithProviders(<DocumentsScreen />);
    const panel = await dialog("Cédula de ciudadanía");
    expect(await within(panel).findByText("CEDULA")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Desactivar" }));
    const modal = await dialog("Desactivar tipo documental");
    expect(within(modal).getByText(/Los expedientes ya armados no cambian/)).toBeInTheDocument();
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/document-types/${TYPES[0]!.id}/deactivate`,
        body: {},
      }),
    );
  });

  it("requisitos: alcance en texto, filtros en la URL y nuevo requisito", async () => {
    const calls = useApi();
    go("?vista=requisitos");
    const user = userEvent.setup();
    renderWithProviders(<DocumentsScreen />);
    await screen.findAllByRole("button", { name: "Cédula de ciudadanía" });
    expect(screen.getByText("General · Titular")).toBeInTheDocument();
    expect(screen.getByText("BN1 · Hipotecario · Independiente · Titular")).toBeInTheDocument();
    expect(screen.getByText("Obligatorio · exonerable · 3 archivos")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por producto" }));
    await user.click(await screen.findByTitle("Generales (sin producto)"));
    await waitFor(() => expect(calls.requirementLists.at(-1)?.get("general")).toBe("true"));

    await user.click(screen.getByRole("button", { name: "Nuevo requisito" }));
    const modal = await dialog("Nuevo requisito");
    await user.click(within(modal).getByRole("button", { name: "Crear requisito" }));
    expect(await within(modal).findByText("Elige el tipo documental.")).toBeInTheDocument();
    await user.click(within(modal).getByRole("combobox", { name: "Tipo documental" }));
    await user.click(await screen.findByTitle("Tipo 2 (inactivo)"));
    await user.click(within(modal).getByRole("combobox", { name: "Rol del participante" }));
    await user.click(await screen.findByTitle("Deudor solidario"));
    await user.click(within(modal).getByRole("checkbox", { name: "Se puede exonerar" }));
    await user.click(within(modal).getByRole("button", { name: "Crear requisito" }));
    await waitFor(() =>
      expect(calls.writes.at(-1)).toEqual({
        method: "POST",
        path: "/api/v1/document-requirements",
        body: {
          is_required: true,
          is_waivable: true,
          minimum_files: 1,
          alternative_group_code: null,
          validity_days: null,
          sort_order: 100,
          valid_to: null,
          document_type_id: TYPES[1]!.id,
          bank_product_id: null,
          purpose_code: null,
          employment_profile_code: null,
          participant_role: "SOLIDARY_DEBTOR",
          property_condition_code: null,
        },
      }),
    );
  });

  it("requisito publicado: nueva versión (201) abre el borrador; un borrador se publica", async () => {
    const calls = useApi();
    go(`?vista=requisitos&abierto=${REQUIREMENTS[0]!.id}`);
    const user = userEvent.setup();
    renderWithProviders(<DocumentsScreen />);
    const panel = await dialog("Cédula de ciudadanía");
    await user.click(within(panel).getByRole("button", { name: "Nueva versión" }));
    const modal = await dialog("Editar requisito de Cédula de ciudadanía");
    expect(within(modal).getByText("Alcance (no se cambia)")).toBeInTheDocument();
    const files = within(modal).getByLabelText("Archivos mínimos");
    await user.clear(files);
    await user.type(files, "2");
    await user.click(within(modal).getByRole("button", { name: "Crear borrador" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/document-requirements/${REQUIREMENTS[0]!.id}`,
        body: { minimum_files: 2 },
      }),
    );
    expect(await screen.findByText("Se creó el borrador v2")).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toContain(`abierto=${REQUIREMENTS[1]!.id}`));

    const draft = await dialog("Cédula de ciudadanía");
    await user.click(await within(draft).findByRole("button", { name: "Publicar" }));
    const confirm = await dialog("Publicar requisito v2");
    await user.click(within(confirm).getByRole("button", { name: "Publicar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/document-requirements/${REQUIREMENTS[1]!.id}/activate`,
        body: null,
      }),
    );
  });

  it("vista previa: caso con participantes y el checklist que saldría", async () => {
    const calls = useApi();
    go("?vista=vista-previa");
    const user = userEvent.setup();
    renderWithProviders(<DocumentsScreen />);
    expect(
      await screen.findByText("Arma un caso y mira qué documentos se pedirían"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Perfil laboral 1" }));
    await user.click(await screen.findByTitle("Empleado"));
    await user.click(screen.getByRole("button", { name: "Agregar participante" }));
    await user.click(screen.getByRole("button", { name: "Quitar el participante 2" }));
    await user.click(screen.getByRole("button", { name: "Ver checklist" }));
    const list = await screen.findByRole("list", { name: "Documentos del participante 1" });
    expect(within(list).getByText("Cédula de ciudadanía")).toBeInTheDocument();
    expect(within(list).getByText("General")).toBeInTheDocument();
    expect(within(list).getByText(/vigencia 30 días/)).toBeInTheDocument();
    expect(screen.getByText("No se le pide ningún documento.")).toBeInTheDocument();
    expect(calls.writes.at(-1)?.body).toEqual({
      bank_product_id: null,
      purpose_code: null,
      property_condition_code: null,
      at: null,
      participants: [{ role: "PRIMARY", employment_profile_code: "EMPLOYEE" }],
    });
  });

  it("solo lectura y móvil", async () => {
    setMobile(true);
    useApi({ permissions: ["document_requirements.read"] });
    renderWithProviders(<DocumentsScreen />);
    const list = await screen.findByRole("list", { name: "Tipos documentales" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Nuevo tipo" })).not.toBeInTheDocument();
  });
});
