import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BANKS_ADMIN,
  BANKS_BOOTSTRAP,
  CONDITION,
  makeRule,
  PRODUCT,
  PRODUCT_ID,
} from "@/features/admin-banks/banks.fixtures";
import { parseRulesParams, RULES_DEFAULTS } from "@/features/admin-banks/list-params";
import { ProductScreen } from "@/features/admin-banks/product-screen";
import type { Rule } from "@/features/admin-banks/queries";
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
    usePathname: () => `/admin/bancos/productos/${PRODUCT_ID}`,
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

const ACTIVE = makeRule(1);
const DRAFT = makeRule(2, { condition: { ...CONDITION, right: 300 } });
const RULES = [ACTIVE, DRAFT];

function useApi({ permissions = BANKS_ADMIN, rules = RULES } = {}) {
  const calls = { lists: [] as URLSearchParams[], writes: [] as WriteCall[] };
  const find = (id: string) => rules.find((r) => r.id === id);
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(meWith(permissions))),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BANKS_BOOTSTRAP)),
    http.get(apiUrl("/bank-products/:id"), () => HttpResponse.json(PRODUCT)),
    http.put(apiUrl("/bank-products/:id/purposes"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(PRODUCT);
    }),
    http.post(apiUrl("/bank-products/:id/:action"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({ ...PRODUCT, status: "INACTIVE" });
    }),
    http.get(apiUrl("/bank-policy-rules"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      calls.lists.push(query);
      return HttpResponse.json(page(rules, query));
    }),
    http.get(apiUrl("/bank-policy-rules/:id"), ({ params }) => {
      const rule = find(String(params.id));
      return rule
        ? HttpResponse.json(rule)
        : HttpResponse.json(apiError("RESOURCE_NOT_FOUND", "No existe."), { status: 404 });
    }),
    http.get(apiUrl("/bank-policy-rules/:id/versions"), () =>
      HttpResponse.json(page(rules, new URLSearchParams("page_size=100"))),
    ),
    http.post(apiUrl("/bank-policy-rules"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json(makeRule(5, { code: "NUEVA" }), { status: 201 });
    }),
    http.patch(apiUrl("/bank-policy-rules/:id"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      const rule = find(String(params.id))!;
      // Sobre una versión publicada nace un borrador nuevo (201).
      return rule.status === "DRAFT"
        ? HttpResponse.json(rule)
        : HttpResponse.json(DRAFT, { status: 201 });
    }),
    http.post(apiUrl("/bank-policy-rules/:id/test"), async ({ request }) => {
      await recordWrite(calls.writes, request);
      return HttpResponse.json({
        rule: { id: DRAFT.id, code: DRAFT.code, version: 2 },
        results: [
          {
            name: "Caso 1",
            outcome: "MISSING_DATA",
            unresolved_fields: ["financing.term_months"],
            expected: "PASSED",
            matches_expected: false,
          },
        ],
      });
    }),
    http.post(apiUrl("/bank-policy-rules/:id/:action"), async ({ request, params }) => {
      await recordWrite(calls.writes, request);
      const status = params.action === "activate" ? "ACTIVE" : "INACTIVE";
      return HttpResponse.json({ ...find(String(params.id))!, status });
    }),
  );
  return calls;
}

const go = (search: string) =>
  window.history.replaceState(null, "", `/admin/bancos/productos/${PRODUCT_ID}${search}`);

async function renderScreen(rule: string | RegExp = "PLAZO_MAXIMO") {
  const user = userEvent.setup();
  renderWithProviders(<ProductScreen productId={PRODUCT_ID} />);
  await screen.findByRole("heading", { name: "Hipotecario VIS", level: 1 });
  await screen.findAllByText(rule);
  return user;
}

const rulePath = (rule: Rule, action = "") =>
  `/api/v1/bank-policy-rules/${rule.id}${action ? `/${action}` : ""}`;

beforeEach(() => setMobile(false));

describe("producto bancario", { timeout: 20_000 }, () => {
  it("parámetros de las reglas", () => {
    expect(parseRulesParams(new URLSearchParams(""))).toEqual(RULES_DEFAULTS);
    expect(
      parseRulesParams(
        new URLSearchParams("status=DRAFT&severity=WARNING&purpose=REMODEL&regla=x"),
      ),
    ).toMatchObject({ status: "DRAFT", severity: "WARNING", purpose: "REMODEL", regla: "" });
  });

  it("datos, finalidades y reglas del producto", async () => {
    const calls = useApi();
    await renderScreen();
    expect(screen.getByRole("link", { name: "Volver a BN1" })).toHaveAttribute(
      "href",
      "/admin/bancos?banco=50000000-0000-4000-8000-000000000001",
    );
    expect(screen.getByText("60 meses a 360 meses")).toBeInTheDocument();
    expect(screen.getByText("Compra de vivienda nueva")).toBeInTheDocument();
    expect(calls.lists.at(-1)?.get("bank_product_id")).toBe(PRODUCT_ID);
    const table = screen.getByRole("table", { name: "Reglas" });
    expect(within(table).getAllByText("financing.term_months ≤ 240")).toHaveLength(1);
    expect(within(table).getByText("Activa")).toBeInTheDocument();
    expect(within(table).getByText("Borrador")).toBeInTheDocument();
  });

  it("cambiar finalidades manda la lista completa", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Cambiar finalidades" }));
    const modal = await dialog("Finalidades del producto");
    await user.click(within(modal).getByRole("checkbox", { name: "Remodelación" }));
    await user.click(within(modal).getByRole("button", { name: "Guardar finalidades" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PUT",
        path: `/api/v1/bank-products/${PRODUCT_ID}/purposes`,
        body: { purpose_codes: ["PURCHASE_NEW", "REMODEL"] },
      }),
    );
  });

  it("desactivar el producto (motivo opcional)", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Desactivar" }));
    const modal = await dialog("Desactivar producto");
    await user.type(within(modal).getByLabelText(/Motivo/), "Cambió la tasa");
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: `/api/v1/bank-products/${PRODUCT_ID}/deactivate`,
        body: { reason: "Cambió la tasa" },
      }),
    );
  });

  it("regla activa: versiones, desactivar y nueva versión (201 abre el borrador)", async () => {
    const calls = useApi();
    go(`?regla=${ACTIVE.id}`);
    const user = await renderScreen();
    const panel = await dialog("PLAZO_MAXIMO");
    const versions = await within(panel).findByRole("list", { name: "Versiones" });
    expect(within(versions).getByText("v1 (esta)")).toBeInTheDocument();
    expect(within(versions).getByRole("button", { name: "v2" })).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Desactivar" }));
    const confirm = await dialog("Desactivar PLAZO_MAXIMO v1");
    await user.click(within(confirm).getByRole("button", { name: "Desactivar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: rulePath(ACTIVE, "deactivate"),
        body: null,
      }),
    );

    await user.click(within(panel).getByRole("button", { name: "Nueva versión" }));
    const modal = await dialog("Editar PLAZO_MAXIMO");
    expect(within(modal).getByText(/al guardar se crea el borrador v2/)).toBeInTheDocument();
    const message = within(modal).getByLabelText("Mensaje");
    await user.clear(message);
    await user.type(message, "Plazo máximo 20 años.");
    await user.click(within(modal).getByRole("button", { name: "Crear borrador" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "PATCH",
        path: rulePath(ACTIVE),
        body: { message: "Plazo máximo 20 años." },
      }),
    );
    expect(await screen.findByText("Se creó el borrador v2")).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe(`?regla=${DRAFT.id}`));
  });

  it("borrador: publicar; el error de la condición va al campo", async () => {
    const calls = useApi();
    go(`?regla=${DRAFT.id}`);
    const user = await renderScreen();
    const panel = await dialog("PLAZO_MAXIMO");
    await user.click(within(panel).getByRole("button", { name: "Publicar" }));
    const confirm = await dialog("Publicar PLAZO_MAXIMO v2");
    await user.click(within(confirm).getByRole("button", { name: "Publicar" }));
    await waitFor(() =>
      expect(calls.writes).toContainEqual({
        method: "POST",
        path: rulePath(DRAFT, "activate"),
        body: null,
      }),
    );

    server.use(
      http.patch(apiUrl("/bank-policy-rules/:id"), () =>
        HttpResponse.json(
          apiError("VALIDATION_ERROR", "Datos inválidos.", [
            { field: "condition.left", code: "invalid", message: "Campo no permitido." },
          ]),
          { status: 400 },
        ),
      ),
    );
    await user.click(within(panel).getByRole("button", { name: "Editar" }));
    const modal = await dialog("Editar PLAZO_MAXIMO");
    const condition = within(modal).getByLabelText("Condición (JSON)");
    await user.clear(condition);
    await user.type(condition, "{{");
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    expect(await within(modal).findByText("No es un JSON válido.")).toBeInTheDocument();
    await user.clear(condition);
    await user.type(condition, '{{"field": "x.y"}');
    await user.click(within(modal).getByRole("button", { name: "Guardar" }));
    expect(
      await within(modal).findByText("condition.left: Campo no permitido."),
    ).toBeInTheDocument();
  });

  it("probar una regla: casos con contexto y resultado", async () => {
    const calls = useApi();
    go(`?regla=${DRAFT.id}`);
    const user = await renderScreen();
    await user.click(within(await dialog("PLAZO_MAXIMO")).getByRole("button", { name: "Probar" }));
    const modal = await dialog("Probar PLAZO_MAXIMO v2");
    const context = within(modal).getByLabelText("Contexto (JSON)");
    // Arranca con los campos que usa la condición.
    expect(context).toHaveValue('{\n  "financing": {\n    "term_months": null\n  }\n}');
    await user.click(within(modal).getByRole("combobox", { name: "Resultado esperado" }));
    await user.click(await screen.findByTitle("Cumple"));
    await user.click(within(modal).getByRole("button", { name: "Agregar caso" }));
    expect(within(modal).getAllByLabelText("Contexto (JSON)")).toHaveLength(2);
    await user.click(within(modal).getByRole("button", { name: "Quitar el caso 2" }));

    await user.click(within(modal).getByRole("button", { name: "Probar" }));
    const results = await within(modal).findByRole("list", { name: "Resultados de la prueba" });
    expect(within(results).getByText("Faltan datos")).toBeInTheDocument();
    expect(within(results).getByText("Se esperaba: Cumple")).toBeInTheDocument();
    expect(within(results).getByText("financing.term_months")).toBeInTheDocument();
    expect(calls.writes.at(-1)).toEqual({
      method: "POST",
      path: rulePath(DRAFT, "test"),
      body: {
        cases: [
          { name: "Caso 1", expected: "PASSED", context: { financing: { term_months: null } } },
        ],
      },
    });
  });

  it("nueva regla: formato del código y JSON; queda en borrador", async () => {
    const calls = useApi();
    const user = await renderScreen();
    await user.click(screen.getByRole("button", { name: "Nueva regla" }));
    const modal = await dialog("Nueva regla");
    await user.type(within(modal).getByLabelText("Código"), "nueva");
    await user.click(within(modal).getByRole("button", { name: "Crear regla" }));
    expect(await within(modal).findByText(/Usa mayúsculas/)).toBeInTheDocument();
    expect(within(modal).getByText("Escribe el mensaje.")).toBeInTheDocument();
    expect(within(modal).getByText(/Se lee:/)).toHaveTextContent("financing.term_months ≤ 360");

    await user.clear(within(modal).getByLabelText("Código"));
    await user.type(within(modal).getByLabelText("Código"), "NUEVA");
    await user.type(within(modal).getByLabelText("Mensaje"), "Plazo largo.");
    await user.click(within(modal).getByRole("radio", { name: "Advertencia" }));
    await user.click(within(modal).getByRole("button", { name: "Crear regla" }));
    expect(await screen.findByText("Regla creada")).toBeInTheDocument();
    expect(calls.writes.at(-1)).toMatchObject({
      method: "POST",
      path: "/api/v1/bank-policy-rules",
      body: {
        code: "NUEVA",
        bank_product_id: PRODUCT_ID,
        severity: "WARNING",
        purpose_code: null,
        message: "Plazo largo.",
        condition: { operator: "lte", left: { field: "financing.term_months" }, right: 360 },
        valid_to: null,
      },
    });
  });

  it("solo lectura: sin acciones en producto ni reglas", async () => {
    useApi({ permissions: ["banks.read", "bank_rules.read"] });
    go(`?regla=${ACTIVE.id}`);
    const user = await renderScreen();
    void user;
    const panel = await dialog("PLAZO_MAXIMO");
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nueva regla" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Probar" })).not.toBeInTheDocument();
  });

  it("en móvil, reglas en tarjetas", async () => {
    setMobile(true);
    useApi();
    await renderScreen(/PLAZO_MAXIMO v1/);
    const list = screen.getByRole("list", { name: "Reglas" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});
