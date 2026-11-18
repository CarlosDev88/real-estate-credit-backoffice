import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BANKS_ADMIN,
  BANKS_BOOTSTRAP,
  makeBank,
  PRODUCT,
  PRODUCT_ID,
} from "@/features/admin-banks/banks.fixtures";
import { BanksScreen } from "@/features/admin-banks/banks-screen";
import { BANKS_DEFAULTS, parseBanksParams } from "@/features/admin-banks/list-params";
import {
  apiError,
  dialog,
  meWith,
  page,
  recordWrite,
  setMobile,
  type WriteCall,
} from "@/features/admin-common/test-kit";
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
    usePathname: () => "/admin/bancos",
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

const BANKS = [makeBank(1), makeBank(2, { status: "INACTIVE" })];

function useApi({ permissions = BANKS_ADMIN, banks = BANKS } = {}) {
  const calls = { lists: [] as URLSearchParams[], writes: [] as WriteCall[] };
  const find = (id: string) => banks.find((b) => b.id === id);
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BANKS_BOOTSTRAP)),
    http.get(apiUrl("/banks"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.lists.push(query);
      return HttpResponse.json(page(banks, query));
    }),
    http.get(apiUrl("/banks/:id"), ({ params }) => {
      const bank = find(String(params.id));
      return bank
        ? HttpResponse.json(bank)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.post(apiUrl("/banks"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makeBank(9), { status: 201 });
    }),
    http.patch(apiUrl("/banks/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(find(String(params.id)));
    }),
    http.post(apiUrl("/banks/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(find(String(params.id)));
    }),
    http.post(apiUrl("/bank-products"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(PRODUCT, { status: 201 });
    }),
  );
  return calls;
}

const go = (search: string) => window.history.replaceState(null, "", `/admin/bancos${search}`);

async function renderScreen() {
  const user = userEvent.setup();
  renderWithProviders(<BanksScreen />);
  await screen.findAllByText("Banco Número 1");
  return user;
}

beforeEach(() => {
  setMobile(false);
  nav.push.mockClear();
});

describe("bancos", { timeout: 20_000 }, () => {
  it("parámetros de la URL", () => {
    expect(parseBanksParams(new URLSearchParams(""))).toEqual(BANKS_DEFAULTS);
    expect(parseBanksParams(new URLSearchParams("status=X&ordering=-code&banco=1"))).toMatchObject({
      status: "",
      ordering: "-code",
      banco: "",
    });
  });

  it("lista con código, NIT y estado; orden por nombre por defecto", async () => {
    const calls = useApi();
    const user = await renderScreen();
    expect(calls.lists.at(-1)?.get("ordering")).toBe("name");
    const row = screen.getByRole("link", { name: "Banco Número 1" }).closest("tr")!;
    expect(within(row).getByText("BANCO_1")).toBeInTheDocument();
    expect(within(row).getByText("860000001-1")).toBeInTheDocument();
    expect(within(row).getByText("BN1")).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Filtrar por estado" }));
    await user.click(await screen.findByTitle("Inactivo"));
    await waitFor(() => expect(calls.lists.at(-1)?.get("status")).toBe("INACTIVE"));
  });

  it("panel con sus productos y enlace a cada uno", async () => {
    useApi();
    go(`?banco=${BANKS[0]!.id}`);
    await renderScreen();
    const panel = await dialog("Banco Número 1");
    const products = within(panel).getByRole("list", { name: "Productos" });
    expect(within(products).getByRole("link", { name: "Hipotecario VIS" })).toHaveAttribute(
      "href",
      `/admin/bancos/productos/${PRODUCT_ID}`,
    );
  });

  it("nuevo banco: código con el formato del contrato y duplicado al campo", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Nuevo banco" }));
    const modal = await dialog("Nuevo banco");
    await user.type(within(modal).getByLabelText("Código"), "banco 3");
    await user.click(within(modal).getByRole("button", { name: "Crear banco" }));
    expect(await within(modal).findByText(/Usa mayúsculas, números y _/)).toBeInTheDocument();
    expect(within(modal).getByText("Escribe el nombre.")).toBeInTheDocument();

    server.use(
      http.post(
        apiUrl("/banks"),
        () =>
          HttpResponse.json(apiError("DUPLICATE_CODE", "Ya existe un banco con ese código."), {
            status: 409,
          }),
        { once: true },
      ),
    );
    await user.clear(within(modal).getByLabelText("Código"));
    await user.type(within(modal).getByLabelText("Código"), "BANCO_3");
    await user.type(within(modal).getByLabelText("Nombre"), "Banco Tres");
    await user.click(within(modal).getByRole("button", { name: "Crear banco" }));
    expect(
      await within(modal).findByText("Ya existe un banco con ese código."),
    ).toBeInTheDocument();

    await user.click(within(modal).getByRole("button", { name: /Crear banco/ }));
    expect(await screen.findByText("Banco creado")).toBeInTheDocument();
    expect(calls.writes.at(-1)).toEqual({
      method: "POST",
      path: "/api/v1/banks",
      body: {
        code: "BANCO_3",
        name: "Banco Tres",
        short_name: "",
        tax_id: "",
        operational_notes: "",
      },
    });
  });

  it("editar manda solo lo cambiado; desactivar con motivo opcional", async () => {
    const calls = useApi();
    go(`?banco=${BANKS[0]!.id}`);
    const user = await renderScreen();
    const panel = await dialog("Banco Número 1");
    await user.click(within(panel).getByRole("button", { name: "Editar" }));
    const modal = await dialog("Editar banco");
    expect(within(modal).getByLabelText("Código")).toBeDisabled();
    await user.type(within(modal).getByLabelText(/Notas operativas/), "Radicar por correo.");
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: `/api/v1/banks/${BANKS[0]!.id}`,
        body: { operational_notes: "Radicar por correo." },
      }),
    );

    await user.click(within(panel).getByRole("button", { name: "Desactivar" }));
    const confirm = await dialog("Desactivar banco");
    await user.click(within(confirm).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/banks/${BANKS[0]!.id}/deactivate`,
        body: {},
      }),
    );
  });

  it("nuevo producto desde el panel: valida, manda finalidades y abre su página", async () => {
    const calls = useApi();
    go(`?banco=${BANKS[0]!.id}`);
    const user = await renderScreen();
    const panel = await dialog("Banco Número 1");
    await user.click(within(panel).getByRole("button", { name: "Nuevo producto" }));
    const modal = await dialog("Nuevo producto");
    await user.click(within(modal).getByRole("button", { name: "Crear producto" }));
    expect(await within(modal).findByText("Escribe el código.")).toBeInTheDocument();
    expect(within(modal).getByText("Elige el tipo.")).toBeInTheDocument();

    await user.type(within(modal).getByLabelText("Código"), "LEASING_1");
    await user.type(within(modal).getByLabelText("Nombre"), "Leasing 1");
    await user.click(within(modal).getByRole("combobox", { name: "Tipo de producto" }));
    await user.click(await screen.findByTitle("Leasing habitacional"));
    await user.type(within(modal).getByLabelText(/Plazo máximo/), "240");
    await user.click(within(modal).getByRole("checkbox", { name: "Remodelación" }));
    await user.click(within(modal).getByRole("button", { name: "Crear producto" }));

    await waitFor(() =>
      expect(nav.push).toHaveBeenCalledWith(`/admin/bancos/productos/${PRODUCT_ID}`),
    );
    expect(calls.writes.at(-1)).toEqual({
      method: "POST",
      path: "/api/v1/bank-products",
      body: {
        code: "LEASING_1",
        name: "Leasing 1",
        product_type_code: "LEASING",
        min_amount_cop: null,
        max_amount_cop: null,
        min_term_months: null,
        max_term_months: 240,
        valid_to: null,
        purpose_codes: ["REMODEL"],
        bank_id: BANKS[0]!.id,
      },
    });
  });

  it("solo lectura: sin crear ni editar", async () => {
    useApi({ permissions: ["banks.read"] });
    go(`?banco=${BANKS[0]!.id}`);
    await renderScreen();
    const panel = await dialog("Banco Número 1");
    expect(screen.queryByRole("button", { name: "Nuevo banco" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Nuevo producto" })).not.toBeInTheDocument();
  });

  it("vacío, banco inexistente y móvil", async () => {
    useApi({ banks: [] });
    go("?search=zzz&banco=50000000-0000-4000-8000-000000000777");
    renderWithProviders(<BanksScreen />);
    expect(await screen.findByText("No hay bancos con estos filtros")).toBeInTheDocument();
    expect(await screen.findByText("Este banco ya no existe")).toBeInTheDocument();
  });

  it("en móvil, tarjetas", async () => {
    setMobile(true);
    useApi();
    await renderScreen();
    const list = screen.getByRole("list", { name: "Bancos" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});
