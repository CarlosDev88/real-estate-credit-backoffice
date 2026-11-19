import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { CommissionCard } from "@/features/commissions/commission-card";
import {
  parseCommissionParams,
  serializeCommissionParams,
  settlementsQuery,
} from "@/features/commissions/commissions-params";
import { CommissionsScreen } from "@/features/commissions/commissions-screen";
import {
  ADMIN_ME,
  ADVISOR_ME,
  ADVISORS,
  BANK_PRODUCTS,
  BANKS,
  BOOTSTRAP,
  BROKERS,
  MY_COMMISSION,
  PAID_SETTLEMENT,
  page,
  PLAN,
  READER_ME,
  SETTLEMENT,
  UNUSED_PLAN,
  VOIDED_SETTLEMENT,
} from "@/features/commissions/commissions.fixtures";
import { MyCommissionsScreen } from "@/features/commissions/my-commissions-screen";
import { bogotaDate, type CommissionSettlement } from "@/features/commissions/queries";
import { planPhase } from "@/features/commissions/plans-tab";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

// Router de prueba: `replace` escribe en la URL de jsdom y avisa a `useSearchParams`.
const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());
  return {
    listeners,
    notify,
    pathname: "/comisiones",
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
    usePathname: () => nav.pathname,
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

const TITLE_SELECTOR = ".ant-modal-title, .ant-drawer-title";

/** El modal o el panel con ese título (Ant Design no le da nombre accesible al `dialog`). */
async function dialogNamed(title: string): Promise<HTMLElement> {
  const heading = await screen.findByText(title, { selector: `${TITLE_SELECTOR}, h2` });
  const dialog = heading.closest<HTMLElement>('[role="dialog"]');
  if (!dialog) throw new Error(`Sin dialog para ${title}`);
  return dialog;
}

interface Post {
  url: string;
  body: unknown;
  key: string | null;
  ifMatch: string | null;
}

interface Calls {
  settlements: string[];
  plans: string[];
  mine: string[];
  posts: Post[];
  patches: Post[];
}

type Handler = Parameters<typeof server.use>[0];

function mockApi(
  options: {
    me?: object;
    settlements?: CommissionSettlement[];
    extra?: Handler[];
  } = {},
): Calls {
  const calls: Calls = { settlements: [], plans: [], mine: [], posts: [], patches: [] };
  const record = async (request: Request): Promise<Post> => {
    const text = await request.text();
    return {
      url: new URL(request.url).pathname,
      body: text ? JSON.parse(text) : null,
      key: request.headers.get("Idempotency-Key"),
      ifMatch: request.headers.get("If-Match"),
    };
  };
  server.use(
    ...(options.extra ?? []),
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(options.me ?? ADMIN_ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/banks"), () => HttpResponse.json(BANKS)),
    http.get(apiUrl("/users"), ({ request }) =>
      HttpResponse.json(
        new URL(request.url).searchParams.get("role") === "INDEPENDENT_BROKER" ? BROKERS : ADVISORS,
      ),
    ),
    http.get(apiUrl("/bank-products"), () => HttpResponse.json(BANK_PRODUCTS)),
    http.get(apiUrl("/commission-settlements"), ({ request }) => {
      calls.settlements.push(new URL(request.url).search);
      const rows = options.settlements ?? [SETTLEMENT, PAID_SETTLEMENT, VOIDED_SETTLEMENT];
      return HttpResponse.json(page(rows, 45));
    }),
    http.get(apiUrl("/commission-settlements/:id"), ({ params }) =>
      HttpResponse.json(
        [SETTLEMENT, PAID_SETTLEMENT, VOIDED_SETTLEMENT].find((s) => s.id === params.id),
      ),
    ),
    http.post(apiUrl("/commission-shares/:id/pay"), async ({ request }) => {
      calls.posts.push(await record(request));
      return HttpResponse.json({
        ...SETTLEMENT,
        shares: [
          { ...SETTLEMENT.shares[0]!, status: "PAID", status_label: "Pagada" },
          SETTLEMENT.shares[1]!,
        ],
      });
    }),
    http.post(apiUrl("/commission-settlements/:id/void"), async ({ request }) => {
      calls.posts.push(await record(request));
      return HttpResponse.json({ ...SETTLEMENT, status: "VOIDED", status_label: "Anulada" });
    }),
    http.get(apiUrl("/commission-plans"), ({ request }) => {
      calls.plans.push(new URL(request.url).search);
      return HttpResponse.json(page([PLAN, UNUSED_PLAN]));
    }),
    http.post(apiUrl("/commission-plans"), async ({ request }) => {
      calls.posts.push(await record(request));
      return HttpResponse.json(UNUSED_PLAN, { status: 201 });
    }),
    http.patch(apiUrl("/commission-plans/:id"), async ({ request }) => {
      calls.patches.push(await record(request));
      return HttpResponse.json(UNUSED_PLAN);
    }),
    http.post(apiUrl("/commission-plans/:id/close"), async ({ request }) => {
      calls.posts.push(await record(request));
      return HttpResponse.json(PLAN);
    }),
    http.get(apiUrl("/me/commissions"), ({ request }) => {
      calls.mine.push(new URL(request.url).search);
      return HttpResponse.json(page([MY_COMMISSION]));
    }),
  );
  return calls;
}

function at(path: string) {
  const [pathname] = path.split("?");
  nav.pathname = pathname ?? "/comisiones";
  window.history.replaceState(null, "", path);
}

describe("parámetros de /comisiones", () => {
  it("lee y escribe los filtros de la pestaña activa, sin los valores por defecto", () => {
    const params = parseCommissionParams(
      new URLSearchParams(
        "status=VOIDED&needs_review=true&bank_id=b-1&date_from=2026-11-01&page=2&liquidacion=st-1&x=1",
      ),
    );
    expect(params.tab).toBe("liquidaciones");
    expect(params.settlements).toMatchObject({
      status: "VOIDED",
      needs_review: "true",
      bank_id: "b-1",
      date_from: "2026-11-01",
      page: 2,
    });
    expect(params.open).toBe("st-1");
    expect(serializeCommissionParams(params)).toBe(
      "status=VOIDED&bank_id=b-1&needs_review=true&date_from=2026-11-01&liquidacion=st-1&page=2",
    );
    // `needs_review` va como booleano a la API.
    expect(settlementsQuery(params.settlements)).toMatchObject({ needs_review: true });
  });

  it("descarta valores que la API no acepta", () => {
    const params = parseCommissionParams(
      new URLSearchParams("tab=otra&status=PAID&needs_review=si&date_to=18/11/2026&page_size=7"),
    );
    expect(params.tab).toBe("liquidaciones");
    expect(params.settlements).toMatchObject({
      status: "",
      needs_review: "",
      date_to: "",
      page_size: 20,
    });
  });

  it("la fecha de Bogotá y la vigencia del plan", () => {
    expect(bogotaDate("2026-11-19T03:00:00Z")).toBe("2026-11-18");
    expect(planPhase(PLAN, "2026-11-18")).toBe("current");
    expect(planPhase(UNUSED_PLAN, "2026-11-18")).toBe("scheduled");
    expect(planPhase({ ...PLAN, valid_until: "2026-11-18" }, "2026-11-18")).toBe("closed");
  });
});

describe("Liquidaciones", () => {
  it("lista con la marca de revisión pendiente y los filtros van a la URL y a la API", async () => {
    at("/comisiones");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<CommissionsScreen />);

    const table = await screen.findByRole("table", { name: "Liquidaciones" });
    expect(within(table).getByText("SOL-000008")).toBeInTheDocument();
    expect(within(table).getByText("Revisión pendiente")).toBeInTheDocument();
    expect(within(table).getAllByText("Anulada").length).toBeGreaterThan(0);
    expect(within(table).getAllByText("Bruno Salas").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("combobox", { name: "Filtrar por revisión" }));
    await user.click(await screen.findByRole("option", { name: "pendiente" }));
    await waitFor(() => expect(window.location.search).toBe("?needs_review=true"));
    await waitFor(() => expect(calls.settlements.at(-1)).toContain("needs_review=true"));

    await user.click(screen.getByRole("combobox", { name: "Filtrar por broker" }));
    await user.click(await screen.findByRole("option", { name: "Bruno Salas" }));
    await waitFor(() => expect(calls.settlements.at(-1)).toContain("broker_id=u-bruno"));
  });

  it("paga una parte con fecha no futura, referencia e Idempotency-Key", async () => {
    at("/comisiones?liquidacion=st-1");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<CommissionsScreen />);

    const panel = await dialogNamed("SOL-000008");
    const shares = within(panel).getAllByRole("listitem");
    expect(shares).toHaveLength(2);
    await user.click(within(shares[0]!).getByRole("button", { name: "Registrar pago" }));

    const modal = await dialogNamed("Registrar pago");
    const date = within(modal).getByLabelText("Fecha del pago");
    expect(date).toHaveValue(bogotaDate(new Date()));
    await user.clear(date);
    await user.type(date, "2999-01-01");
    await user.click(within(modal).getByRole("button", { name: "Registrar pago" }));
    expect(
      await within(modal).findByText("La fecha del pago no puede ser futura."),
    ).toBeInTheDocument();
    expect(within(modal).getByText("Escribe la referencia del pago.")).toBeInTheDocument();

    await user.clear(date);
    await user.type(date, "2026-11-15");
    await user.type(within(modal).getByLabelText("Referencia"), "  TRF-2001 ");
    await user.click(within(modal).getByRole("button", { name: "Registrar pago" }));

    await waitFor(() => expect(calls.posts).toHaveLength(1));
    expect(calls.posts[0]).toMatchObject({
      url: "/api/v1/commission-shares/sh-adv/pay",
      body: { paid_at: "2026-11-15", payment_reference: "TRF-2001" },
    });
    expect(calls.posts[0]!.key).toMatch(/[0-9a-f-]{36}/);
    expect(await screen.findByText("Pago registrado")).toBeInTheDocument();
  });

  it("anula con motivo; con una parte pagada no deja anular", async () => {
    at("/comisiones?liquidacion=st-2");
    const calls = mockApi();
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<CommissionsScreen />);

    const paid = await dialogNamed("SOL-000009");
    expect(
      within(paid).getByText("Revisión pendiente", { selector: ".ant-alert-title" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anular liquidación" })).toBeDisabled();
    expect(screen.getByText("Tiene partes pagadas: no se puede anular.")).toBeInTheDocument();
    unmount();

    at("/comisiones?liquidacion=st-1");
    renderWithProviders(<CommissionsScreen />);
    await dialogNamed("SOL-000008");
    await user.click(screen.getByRole("button", { name: "Anular liquidación" }));
    const modal = await dialogNamed("Anular liquidación");
    await user.click(within(modal).getByRole("button", { name: "Anular liquidación" }));
    expect(await within(modal).findByText("Escribe el motivo.")).toBeInTheDocument();
    await user.type(within(modal).getByLabelText("Motivo"), "Desembolso duplicado");
    await user.click(within(modal).getByRole("button", { name: "Anular liquidación" }));

    await waitFor(() => expect(calls.posts).toHaveLength(1));
    expect(calls.posts[0]).toMatchObject({
      url: "/api/v1/commission-settlements/st-1/void",
      body: { reason: "Desembolso duplicado" },
    });
    expect(calls.posts[0]!.key).toBeTruthy();
  });

  it("solo consulta: sin pagar, anular, liquidar a mano ni la pestaña de planes", async () => {
    at("/comisiones?liquidacion=st-1");
    mockApi({ me: READER_ME });
    renderWithProviders(<CommissionsScreen />);

    const panel = await dialogNamed("SOL-000008");
    expect(within(panel).queryByRole("button", { name: "Registrar pago" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Anular liquidación" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Liquidar a mano" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Planes" })).toBeNull();
  });

  it("liquida a mano: marca las ya liquidadas y avisa si falta el plan", async () => {
    at("/comisiones");
    const settles: Post[] = [];
    let answer: "plan" | "ok" = "plan";
    const calls = mockApi({
      extra: [
        http.get(apiUrl("/applications"), () =>
          HttpResponse.json(
            page([
              { id: "app-8", code: "SOL-000008", applicant: { full_name: "Mariana Cárdenas" } },
              { id: "app-20", code: "SOL-000020", applicant: { full_name: "Tomás Gil" } },
            ]),
          ),
        ),
        http.post(apiUrl("/applications/:id/commission-settlement"), ({ request, params }) => {
          settles.push({
            url: String(params.id),
            body: null,
            key: request.headers.get("Idempotency-Key"),
            ifMatch: null,
          });
          if (answer === "plan") {
            return HttpResponse.json(
              {
                code: "COMMISSION_PLAN_NOT_FOUND",
                message: "No hay un plan de comisión vigente para el producto en esa fecha.",
                details: [],
                request_id: "r-1",
              },
              { status: 422 },
            );
          }
          return HttpResponse.json(
            { ...SETTLEMENT, id: "st-9", application: { id: "app-20", code: "SOL-000020" } },
            { status: 201 },
          );
        }),
      ],
    });
    const user = userEvent.setup();
    renderWithProviders(<CommissionsScreen />);

    await user.click(await screen.findByRole("button", { name: "Liquidar a mano" }));
    const modal = await dialogNamed("Liquidar a mano");
    await user.click(within(modal).getByRole("button", { name: "Liquidar" }));
    expect(await within(modal).findByText("Elige la solicitud.")).toBeInTheDocument();

    await user.click(within(modal).getByRole("combobox"));
    const done = await screen.findByRole("option", { name: /SOL-000008.*ya liquidada/ });
    expect(done).toHaveAttribute("aria-disabled", "true");
    await user.click(await screen.findByRole("option", { name: "SOL-000020 · Tomás Gil" }));
    await user.click(within(modal).getByRole("button", { name: "Liquidar" }));
    expect(
      await within(modal).findByText(
        "No hay un plan de comisión vigente para el producto en esa fecha.",
      ),
    ).toBeInTheDocument();

    answer = "ok";
    await user.click(within(modal).getByRole("button", { name: "Liquidar" }));
    await waitFor(() => expect(settles).toHaveLength(2));
    expect(settles[1]!.url).toBe("app-20");
    // Mismo intento, misma clave: el reintento no crea otra liquidación.
    expect(settles[1]!.key).toBe(settles[0]!.key);
    expect(await screen.findByText("Comisión liquidada")).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe("?liquidacion=st-9"));
    expect(calls.settlements.length).toBeGreaterThan(0);
  }, 20_000);
});

describe("Planes", () => {
  it("en uso solo se cierra; el otro se edita con If-Match", async () => {
    at("/comisiones?tab=planes");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<CommissionsScreen />);

    const table = await screen.findByRole("table", { name: "Planes de comisión" });
    expect(within(table).getByText("En uso")).toBeInTheDocument();
    expect(within(table).getByText("Programado")).toBeInTheDocument();
    expect(
      within(table).queryByRole("button", {
        name: "Editar el plan de Bancolombia · Hipotecario vivienda",
      }),
    ).toBeNull();

    await user.click(
      within(table).getByRole("button", {
        name: "Editar el plan de Davivienda · Leasing habitacional",
      }),
    );
    const modal = await dialogNamed("Editar plan");
    expect(within(modal).getByLabelText("Tasa")).toHaveValue("0.75");
    const advisor = within(modal).getByLabelText("Porción del asesor");
    await user.clear(advisor);
    await user.type(advisor, "80");
    // El broker se completa para sumar 100.
    expect(within(modal).getByLabelText("Porción del broker")).toHaveValue("20");
    await user.click(within(modal).getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(calls.patches).toHaveLength(1));
    expect(calls.patches[0]).toMatchObject({
      url: "/api/v1/commission-plans/pl-2",
      ifMatch: '"4"',
      body: { rate_pct: "0.75", advisor_share_pct: "80", broker_share_pct: "20" },
    });
  });

  it("crea un plan validando el reparto, y cierra uno en uso", async () => {
    at("/comisiones?tab=planes");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<CommissionsScreen />);

    await screen.findByRole("table", { name: "Planes de comisión" });
    await user.click(screen.getByRole("button", { name: "Nuevo plan" }));
    const modal = await dialogNamed("Nuevo plan");
    await user.click(within(modal).getByRole("combobox"));
    await user.click(
      await screen.findByRole("option", { name: "Bancolombia · Hipotecario vivienda" }),
    );
    await user.type(within(modal).getByLabelText("Tasa"), "1,5");
    await user.type(within(modal).getByLabelText("Porción del asesor"), "40");
    await user.click(within(modal).getByRole("button", { name: "Crear plan" }));
    expect(await within(modal).findByText("El asesor lleva la porción mayor.")).toBeInTheDocument();
    expect(calls.posts).toHaveLength(0);

    const advisor = within(modal).getByLabelText("Porción del asesor");
    await user.clear(advisor);
    await user.type(advisor, "70");
    await user.click(within(modal).getByRole("button", { name: "Crear plan" }));
    await waitFor(() => expect(calls.posts).toHaveLength(1));
    expect(calls.posts[0]).toMatchObject({
      url: "/api/v1/commission-plans",
      body: {
        bank_product_id: "bp-1",
        rate_pct: "1.5",
        advisor_share_pct: "70",
        broker_share_pct: "30",
        valid_until: null,
        notes: "",
      },
    });

    await user.click(
      screen.getByRole("button", { name: "Cerrar el plan de Bancolombia · Hipotecario vivienda" }),
    );
    const close = await dialogNamed("Cerrar plan");
    const until = within(close).getByLabelText("Deja de regir el");
    await user.clear(until);
    await user.type(until, "2026-12-01");
    await user.click(within(close).getByRole("button", { name: "Cerrar plan" }));
    await waitFor(() => expect(calls.posts).toHaveLength(2));
    expect(calls.posts[1]).toMatchObject({
      url: "/api/v1/commission-plans/pl-1/close",
      body: { valid_until: "2026-12-01" },
    });
  });
});

describe("Mis comisiones", () => {
  it("muestra solo la parte propia y filtra por estado", async () => {
    at("/mis-comisiones");
    const calls = mockApi({ me: ADVISOR_ME });
    const user = userEvent.setup();
    renderWithProviders(<MyCommissionsScreen />);

    const table = await screen.findByRole("table", { name: "Mis comisiones" });
    expect(within(table).getByText("Mariana Cárdenas Ríos")).toBeInTheDocument();
    expect(within(table).getByText("Pagada")).toBeInTheDocument();
    // Nunca la base, la tasa ni el total de la liquidación.
    for (const header of ["Base", "Tasa", "Total"]) {
      expect(within(table).queryByRole("columnheader", { name: header })).toBeNull();
    }

    await user.click(screen.getByRole("combobox", { name: "Filtrar por estado" }));
    await user.click(await screen.findByRole("option", { name: "Pendiente de pago" }));
    await waitFor(() => expect(window.location.search).toBe("?status=PENDING"));
    await waitFor(() => expect(calls.mine.at(-1)).toContain("status=PENDING"));
  });
});

describe("Tarjeta Comisión del expediente", () => {
  it("pide las liquidaciones de la solicitud y prefiere la vigente", async () => {
    const calls = mockApi({
      settlements: [
        { ...VOIDED_SETTLEMENT, application: { id: "app-8", code: "SOL-000008" } },
        SETTLEMENT,
      ],
    });
    renderWithProviders(<CommissionCard applicationId="app-8" code="SOL-000008" canManage />);

    const card = await screen.findByRole("region", { name: "Comisión" });
    expect(await within(card).findByText("Vigente")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver liquidación" })).toHaveAttribute(
      "href",
      "/comisiones?liquidacion=st-1",
    );
    // Vigente: no se ofrece liquidar otra vez.
    expect(within(card).queryByRole("button", { name: "Liquidar" })).toBeNull();
    expect(calls.settlements[0]).toContain("application_id=app-8");
    expect(calls.settlements[0]).not.toContain("date_from");
  });

  it("sin liquidación ofrece liquidar a quien puede", async () => {
    mockApi({ settlements: [] });
    renderWithProviders(<CommissionCard applicationId="app-8" code="SOL-000008" canManage />);
    const card = await screen.findByRole("region", { name: "Comisión" });
    expect(
      await within(card).findByText("Esta solicitud todavía no tiene liquidación de comisión."),
    ).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Liquidar" })).toBeInTheDocument();
  });
});
