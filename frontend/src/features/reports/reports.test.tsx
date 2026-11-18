import { renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { FUNNEL } from "@/features/dashboard/dashboard.fixtures";
import type { ExportJob, ReportApplication, ReportFunnel } from "@/features/reports/queries";
import { ReportsScreen } from "@/features/reports/reports-screen";
import {
  parseReportParams,
  reportQuery,
  serializeReportParams,
} from "@/features/reports/reports-params";
import { filenameFrom } from "@/features/reports/save-file";
import type * as SaveFile from "@/features/reports/save-file";
import { useIdempotencyKey } from "@/lib/api/idempotency";
import { apiUrl, server } from "@/test/msw-server";
import { renderWithProviders } from "@/test/render";

const saveBlob = vi.hoisted(() => vi.fn());
vi.mock("@/features/reports/save-file", async (importOriginal) => ({
  ...(await importOriginal<typeof SaveFile>()),
  saveBlob,
}));
const startDownload = vi.hoisted(() => vi.fn());
vi.mock("@/features/filings/download", () => ({ startDownload }));

// Router de prueba: `replace` escribe en la URL de jsdom y avisa a `useSearchParams`.
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
    usePathname: () => "/reportes",
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

const ME = {
  id: "u-1",
  name: "Lucía Rojas",
  email: "lucia@example.com",
  role: "ADVISOR",
  role_label: "Asesor",
  roles: ["ADVISOR"],
  permissions: ["reports.read", "reports.export", "banks.read"],
  scope: { assigned_applications_only: true, partner_id: null },
};

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
  actor: "INTERNAL",
  permissions: [],
  on_demand_catalogs: [],
  features: {},
  catalogs: {
    loan_purpose: [item("NEW", "Vivienda nueva", 1)],
    application_status: [item("FILED", "Radicada", 1), item("APPROVED", "Aprobada", 2)],
  },
};

const GROUPED: ReportFunnel = {
  period: FUNNEL.period,
  group_by: "advisor",
  stages: FUNNEL.stages,
  groups: [
    { key: "a-1", label: "Andrés Patiño", stages: FUNNEL.stages.map((s) => ({ ...s, count: 1 })) },
    { key: null, label: "Sin banco", stages: FUNNEL.stages },
  ],
};

const ROW: ReportApplication = {
  code: "SOL-000008",
  created_at: "2026-11-12T16:38:38-05:00",
  status: "FILED",
  status_label: "Radicada",
  purpose: "Vivienda nueva",
  advisor_name: "Lucía Rojas",
  client_name: "Mariana Cárdenas",
  client_document_masked: "******5908",
  bank_name: "Bancolombia",
  project_name: null,
  requested_amount: "294000000.00",
  last_status_change_at: "2026-11-15T10:00:00-05:00",
  filings_count: 1,
};

const job = (over: Partial<ExportJob>): ExportJob => ({
  id: "job-1",
  report_type: "applications",
  report_type_label: "Solicitudes",
  format: "csv",
  status: "COMPLETED",
  status_label: "Terminada",
  filters: {
    date_from: "2026-11-01",
    date_to: "2026-11-18",
    advisor_id: null,
    partner_id: null,
    project_id: null,
    bank_id: null,
    purpose_code: null,
    status: [],
  },
  row_count: 35,
  error_code: null,
  requested_by: { id: "u-1", name: "Lucía Rojas" },
  created_at: "2026-11-18T12:00:00-05:00",
  started_at: "2026-11-18T12:00:01-05:00",
  completed_at: "2026-11-18T12:00:02-05:00",
  expires_at: "2026-11-19T12:00:02-05:00",
  ...over,
});

const page = <T,>(items: T[], total = items.length) => ({
  items,
  page: 1,
  page_size: 20,
  total,
  next: null,
  previous: null,
});

interface Calls {
  funnel: string[];
  list: string[];
  csv: string[];
  posts: { body: unknown; key: string | null }[];
}

type Handler = Parameters<typeof server.use>[0];

function mockApi(
  overrides: Partial<Record<"csv" | "post" | "jobs" | "job" | "download", Handler>> = {},
) {
  const calls: Calls = { funnel: [], list: [], csv: [], posts: [] };
  server.use(
    http.get(apiUrl("/auth/me"), () => HttpResponse.json(ME)),
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(BOOTSTRAP)),
    http.get(apiUrl("/banks"), () => HttpResponse.json(page([]))),
    http.get(apiUrl("/reports/funnel"), ({ request }) => {
      const url = new URL(request.url);
      calls.funnel.push(url.search);
      return HttpResponse.json(
        url.searchParams.get("group_by")
          ? GROUPED
          : { period: FUNNEL.period, group_by: null, stages: FUNNEL.stages, groups: [] },
      );
    }),
    http.get(apiUrl("/reports/applications"), ({ request }) => {
      calls.list.push(new URL(request.url).search);
      return HttpResponse.json(page([ROW], 41));
    }),
    overrides.csv ??
      http.get(apiUrl("/reports/applications.csv"), ({ request }) => {
        calls.csv.push(new URL(request.url).search);
        return new HttpResponse("código\nSOL-000008\n", {
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition": 'attachment; filename="solicitudes_2026-11-01_2026-11-18.csv"',
          },
        });
      }),
    overrides.jobs ??
      http.get(apiUrl("/reports/applications/export-jobs"), () =>
        HttpResponse.json(
          page([
            ...(calls.posts.length
              ? [
                  job({
                    id: "job-new",
                    status: "PENDING",
                    status_label: "Pendiente",
                    row_count: null,
                  }),
                ]
              : []),
            job({ id: "job-old" }),
          ]),
        ),
      ),
    overrides.post ??
      http.post(apiUrl("/reports/applications/export-jobs"), async ({ request }) => {
        calls.posts.push({
          body: await request.json(),
          key: request.headers.get("Idempotency-Key"),
        });
        return HttpResponse.json(
          job({ id: "job-new", status: "PENDING", status_label: "Pendiente", row_count: null }),
          { status: 202 },
        );
      }),
    overrides.job ??
      http.get(apiUrl("/report-export-jobs/:id"), ({ params }) =>
        HttpResponse.json(job({ id: String(params.id) })),
      ),
    overrides.download ??
      http.get(apiUrl("/report-export-jobs/:id/download"), () =>
        HttpResponse.json({
          url: "https://storage.example/export.csv",
          expires_at: "2026-11-18T12:05:00Z",
        }),
      ),
  );
  return calls;
}

/** El panel "Mis exportaciones" (el `h2` del `SidePanel` está dentro del `dialog`). */
async function panel() {
  const heading = await screen.findByRole("heading", { name: "Mis exportaciones", level: 2 });
  return heading.closest<HTMLElement>('[role="dialog"]')!;
}

describe("reportes: URL y utilidades", () => {
  it("lee y escribe la pestaña, los filtros, varios estados y el agrupado", () => {
    const params = parseReportParams(
      new URLSearchParams(
        "tab=solicitudes&status=FILED&status=APPROVED&status=FILED&group_by=bank&page=2&purpose_code=NEW",
      ),
    );
    expect(params).toMatchObject({
      tab: "solicitudes",
      status: ["FILED", "APPROVED"],
      group_by: "bank",
      page: 2,
      purpose_code: "NEW",
    });
    expect(serializeReportParams(params)).toBe(
      "tab=solicitudes&purpose_code=NEW&status=FILED&status=APPROVED&group_by=bank&page=2",
    );
    const defaults = parseReportParams(new URLSearchParams("tab=otra&group_by=mes&page_size=7"));
    expect(serializeReportParams(defaults)).toBe("");
    expect(reportQuery({ ...defaults, status: [] })).toEqual({});
  });

  it("saca el nombre del archivo de Content-Disposition", () => {
    expect(filenameFrom('attachment; filename="a b.csv"', "x.csv")).toBe("a b.csv");
    expect(filenameFrom("attachment; filename*=UTF-8''reporte%20nov.csv", "x.csv")).toBe(
      "reporte nov.csv",
    );
    expect(filenameFrom("attachment; filename*=UTF-8''%E0%A4%A.csv; filename=b.csv", "x.csv")).toBe(
      "b.csv",
    );
    expect(filenameFrom(null, "x.csv")).toBe("x.csv");
  });

  it("la clave de idempotencia se reusa en el mismo intento y cambia al terminar o con otros filtros", () => {
    const { result, rerender } = renderHook(({ scope }) => useIdempotencyKey(scope), {
      initialProps: { scope: "a" },
    });
    const first = result.current.current();
    expect(result.current.current()).toBe(first);
    result.current.reset();
    const second = result.current.current();
    expect(second).not.toBe(first);
    rerender({ scope: "b" });
    expect(result.current.current()).not.toBe(second);
  });
});

describe("ReportsScreen", { timeout: 30_000 }, () => {
  it("embudo sin agrupar y agrupado por asesor, con la fila del total", async () => {
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<ReportsScreen />);

    expect(await screen.findByRole("table", { name: "Embudo de solicitudes" })).toBeInTheDocument();
    expect(screen.getByText("Periodo: 1 nov 2026 – 18 nov 2026")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Agrupar por" }));
    await user.click(await screen.findByRole("option", { name: "asesor" }));
    await waitFor(() => expect(window.location.search).toBe("?group_by=advisor"));
    const table = await screen.findByRole("table", { name: "Embudo por asesor" });
    expect(within(table).getByRole("columnheader", { name: "Asesor" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /Total/ })).toHaveTextContent("35");
    expect(within(table).getByRole("row", { name: /Andrés Patiño/ })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /Sin banco/ })).toBeInTheDocument();
    expect(calls.funnel).toContain("?group_by=advisor");
  });

  it("estado multivalor en la URL y en la consulta; pestaña Solicitudes con paginación", async () => {
    window.history.replaceState(null, "", "/reportes?status=FILED&status=APPROVED");
    const calls = mockApi();
    const user = userEvent.setup();
    renderWithProviders(<ReportsScreen />);
    await screen.findByRole("table", { name: "Embudo de solicitudes" });
    expect(calls.funnel[0]).toBe("?status=FILED&status=APPROVED");

    await user.click(screen.getByRole("tab", { name: "Solicitudes" }));
    const table = await screen.findByRole("table", { name: "Solicitudes del reporte" });
    const row = within(table).getByRole("row", { name: /SOL-000008/ });
    // El documento llega enmascarado y se muestra tal cual.
    expect(row).toHaveTextContent("******5908");
    expect(row).toHaveTextContent("Radicada");
    expect(screen.getByText("Mostrando 1–20 de 41")).toBeInTheDocument();
    expect(calls.list[0]).toBe("?status=FILED&status=APPROVED&page=1&page_size=20");
    // "Agrupar por" es del embudo.
    expect(screen.queryByRole("combobox", { name: "Agrupar por" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    await waitFor(() => expect(window.location.search).toBe("?tab=solicitudes"));
  });

  it("descarga el CSV con los filtros; con 422 EXPORT_TOO_LARGE ofrece preparar la exportación", async () => {
    window.history.replaceState(null, "", "/reportes?purpose_code=NEW");
    let tooLarge = false;
    const calls = mockApi({
      csv: http.get(apiUrl("/reports/applications.csv"), ({ request }) => {
        calls.csv.push(new URL(request.url).search);
        if (tooLarge) {
          return HttpResponse.json(
            {
              code: "EXPORT_TOO_LARGE",
              message: "Supera las 5000 filas.",
              details: [],
              request_id: "r",
            },
            { status: 422 },
          );
        }
        return new HttpResponse("a\n", {
          headers: { "Content-Disposition": 'attachment; filename="solicitudes.csv"' },
        });
      }),
    });
    const user = userEvent.setup();
    renderWithProviders(<ReportsScreen />);
    await screen.findByRole("table", { name: "Embudo de solicitudes" });

    await user.click(screen.getByRole("button", { name: "Descargar CSV" }));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1));
    expect(saveBlob.mock.calls[0]?.[1]).toBe("solicitudes.csv");
    expect(calls.csv[0]).toBe("?purpose_code=NEW");
    expect(await screen.findByText("Descarga iniciada")).toBeInTheDocument();

    tooLarge = true;
    await user.click(screen.getByRole("button", { name: "Descargar CSV" }));
    const alert = await screen.findByText("El reporte es muy grande para descargarlo directo");
    expect(screen.getByText("Supera las 5000 filas.")).toBeInTheDocument();
    const offer = alert.closest<HTMLElement>(".ant-alert")!;
    await user.click(within(offer).getByRole("button", { name: "Preparar exportación" }));

    await waitFor(() => expect(calls.posts).toHaveLength(1));
    expect(calls.posts[0]?.body).toEqual({ purpose_code: "NEW" });
    expect(calls.posts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    const drawer = await panel();
    // La nueva queda arriba, pendiente, y se consulta hasta terminar.
    await waitFor(() => expect(within(drawer).getAllByRole("listitem")).toHaveLength(2));
    await waitFor(
      () =>
        expect(
          within(within(drawer).getAllByRole("listitem")[0]!).getByRole("button", {
            name: /^Descargar/,
          }),
        ).toBeInTheDocument(),
      { timeout: 8000 },
    );
  });

  it("descarga una exportación terminada y maneja 410 (vencida) y 429 al preparar", async () => {
    const posts: (string | null)[] = [];
    let gone = false;
    mockApi({
      post: http.post(apiUrl("/reports/applications/export-jobs"), ({ request }) => {
        posts.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.json(
          {
            code: "TOO_MANY_EXPORTS",
            message: "Ya tienes 3 exportaciones en curso.",
            details: [],
            request_id: "r",
          },
          { status: 429 },
        );
      }),
      download: http.get(apiUrl("/report-export-jobs/:id/download"), () =>
        gone
          ? HttpResponse.json(
              {
                code: "EXPORT_EXPIRED",
                message: "La exportación venció.",
                details: [],
                request_id: "r",
              },
              { status: 410 },
            )
          : HttpResponse.json({
              url: "https://storage.example/e.csv",
              expires_at: "2026-11-18T12:05:00Z",
            }),
      ),
    });
    const user = userEvent.setup();
    renderWithProviders(<ReportsScreen />);
    await screen.findByRole("table", { name: "Embudo de solicitudes" });

    await user.click(screen.getByRole("button", { name: "Mis exportaciones" }));
    const drawer = await panel();
    const download = await within(drawer).findByRole("button", { name: /^Descargar/ });
    await user.click(download);
    await waitFor(() =>
      expect(startDownload).toHaveBeenCalledWith("https://storage.example/e.csv"),
    );

    gone = true;
    await user.click(download);
    expect(await screen.findByText("La exportación venció.")).toBeInTheDocument();

    // 429: el mensaje queda junto al botón. Reintentar usa la misma clave.
    const prepare = within(drawer).getByRole("button", { name: "Preparar exportación" });
    await user.click(prepare);
    expect(await within(drawer).findByRole("alert")).toHaveTextContent(
      "Ya tienes 3 exportaciones en curso.",
    );
    expect(prepare).toHaveAttribute("aria-describedby", "prepare-export-error");
    await user.click(prepare);
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toBe(posts[0]);
  });

  it("un filtro fuera del alcance se muestra en el filtro", async () => {
    mockApi();
    server.use(
      http.get(apiUrl("/reports/funnel"), () =>
        HttpResponse.json(
          {
            code: "VALIDATION_ERROR",
            message: "Inválido",
            details: [{ field: "status", code: "INVALID", message: "Estado desconocido." }],
            request_id: "r",
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<ReportsScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Estado: Estado desconocido.");
    expect(screen.getByText(/Corrige el filtro marcado/)).toBeInTheDocument();
  });

  it("sin reports.export no hay botones de exportar", async () => {
    mockApi();
    server.use(
      http.get(apiUrl("/auth/me"), () =>
        HttpResponse.json({ ...ME, permissions: ["reports.read"] }),
      ),
    );
    renderWithProviders(<ReportsScreen />);
    await screen.findByRole("table", { name: "Embudo de solicitudes" });
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Descargar CSV" })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Mis exportaciones" })).not.toBeInTheDocument();
  });
});

describe("ReportsScreen en móvil", { timeout: 30_000 }, () => {
  it("las solicitudes van en tarjetas y los filtros extra en la hoja", async () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("max-width: 860px"),
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    );
    window.history.replaceState(null, "", "/reportes?tab=solicitudes&status=FILED");
    mockApi();
    const user = userEvent.setup();
    renderWithProviders(<ReportsScreen />);

    const cards = await screen.findByRole("list", { name: "Solicitudes del reporte" });
    expect(within(cards).getByText("SOL-000008")).toBeInTheDocument();
    expect(within(cards).getByText("******5908")).toBeInTheDocument();
    const chips = screen.getByRole("list", { name: "Filtros activos" });
    expect(await within(chips).findByText("Radicada")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Quitar filtro Estado: Radicada" }));
    await waitFor(() => expect(window.location.search).toBe("?tab=solicitudes"));
  });
});
