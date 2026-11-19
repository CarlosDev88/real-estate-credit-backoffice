// Datos de prueba de la radicación (solo para las pruebas con MSW).
import { http, HttpResponse } from "msw";

import {
  ALL_PERMISSIONS,
  APP_ID,
  BOOTSTRAP,
  makeDetail,
  makeSlot,
  useWorkspaceApi,
  type WorkspaceApi,
} from "@/features/applications/workspace.fixtures";
import type {
  Filing,
  FilingResponse,
  FilingSnapshot,
  PackageJob,
} from "@/features/filings/queries";
import { apiUrl, server } from "@/test/msw-server";

export const FILING_PERMISSIONS = [
  ...ALL_PERMISSIONS,
  "documents.read",
  "filings.read",
  "filings.prepare",
  "filings.create",
  "filings.update",
  "filings.record_response",
];

const item = (
  code: string,
  label: string,
  order: number,
  metadata: Record<string, unknown> = {},
) => ({
  id: `${code}-id`,
  code,
  label,
  description: "",
  order,
  active: true,
  parent_id: null,
  parent_code: null,
  metadata,
});

/**
 * `metadata` de `filing_response_type` como lo publica la API (`response_type_metadata`):
 * los campos propios del tipo y después las notas.
 */
const NOTES = ["public_message", "internal_comment"];
export const RESPONSE_TYPE_METADATA: Record<string, Record<string, unknown>> = {
  RECEIVED: { fields: NOTES, required: [], reason_catalog: null },
  IN_ANALYSIS: { fields: NOTES, required: [], reason_catalog: null },
  RETURNED: {
    fields: ["reason_code", "observations", ...NOTES],
    required: ["reason_code", "public_message", "observations"],
    reason_catalog: "filing_return_reason",
  },
  APPROVED: {
    fields: ["approved_amount_cop", "approved_term_months", "valid_until", ...NOTES],
    required: ["approved_amount_cop", "approved_term_months", "public_message"],
    reason_catalog: null,
  },
  REJECTED: {
    fields: ["reason_code", ...NOTES],
    required: ["reason_code", "public_message"],
    reason_catalog: "filing_rejection_reason",
  },
  DISBURSED: {
    fields: ["disbursed_amount_cop", ...NOTES],
    required: ["disbursed_amount_cop"],
    reason_catalog: null,
  },
  OTHER: { fields: NOTES, required: ["internal_comment"], reason_catalog: null },
};
const responseType = (code: string, label: string, order: number) =>
  item(code, label, order, RESPONSE_TYPE_METADATA[code]);

export const FILING_BOOTSTRAP = {
  ...BOOTSTRAP,
  catalogs: {
    ...BOOTSTRAP.catalogs,
    filing_channel: [
      item("BANK_PORTAL", "Portal del banco", 1),
      item("EMAIL", "Correo electrónico", 2),
    ],
    filing_response_type: [
      responseType("RECEIVED", "Recibida", 1),
      responseType("IN_ANALYSIS", "En análisis", 2),
      responseType("RETURNED", "Devuelta con observaciones", 3),
      responseType("APPROVED", "Aprobada", 4),
      responseType("REJECTED", "Rechazada", 5),
      responseType("DISBURSED", "Desembolsada", 6),
      responseType("OTHER", "Otra", 7),
    ],
    filing_return_reason: [item("DOCUMENT_CORRECTION", "Corrección de documentos", 1)],
    filing_rejection_reason: [item("PAYMENT_CAPACITY", "Capacidad de pago insuficiente", 1)],
  },
};

const PRODUCT = makeDetail().bank_product!;

export function makeFiling(n: number, overrides: Partial<Filing> = {}): Filing {
  return {
    id: `fi-${n}`,
    application_id: APP_ID,
    sequence_number: n,
    status: "FILED",
    status_label: "Radicada",
    bank_product: PRODUCT,
    channel: { code: "BANK_PORTAL", label: "Portal del banco" },
    external_reference: `RAD-00${n}`,
    package_job_id: `job-${n}`,
    filed_by: { id: "u-1", name: "Paula Rincón" },
    filed_at: "2026-11-10T14:30:00Z",
    target_response_at: "2099-11-17T14:30:00Z",
    comment: null,
    responses_count: 0,
    is_response_overdue: false,
    application_status: "FILED",
    application_status_label: "Radicada",
    created_at: "2026-11-10T14:31:00Z",
    updated_at: "2026-11-10T14:31:00Z",
    ...overrides,
  };
}

export function makeJob(overrides: Partial<PackageJob> = {}): PackageJob {
  return {
    id: "job-9",
    application_id: APP_ID,
    application_version: 14,
    status: "COMPLETED",
    error_code: null,
    fingerprint: "abc",
    requested_by: { id: "u-1", name: "Paula Rincón" },
    created_at: "2026-11-17T14:00:00Z",
    started_at: "2026-11-17T14:00:01Z",
    completed_at: "2026-11-17T14:00:04Z",
    expires_at: "2026-11-24T14:00:04Z",
    output: { filename: "SOL-000182_expediente.zip", size_bytes: 2_483_021, sha256: "x" },
    documents: [
      {
        slot_id: "s-1",
        document_type: { code: "DOC", name: "Certificado laboral" },
        label: "Certificado laboral",
        holder: {
          scope: "PARTICIPANT",
          participant_id: "pa-1",
          role: "PRIMARY",
          role_name: "Titular",
          full_name: "Sofía Herrera",
          folder: "01_TITULAR_Sofia_Herrera",
        },
        status: "APPROVED",
        document_date: null,
        expires_at: null,
        file: {
          path: "01_TITULAR_Sofia_Herrera/Certificado_laboral.pdf",
          document_file_id: "f-1",
          version_number: 1,
          client_filename: "archivo-1.pdf",
          mime_type: "application/pdf",
          size_bytes: 1000,
          sha256: "x",
        },
        waiver_reason: null,
      },
    ],
    ...overrides,
  } as PackageJob;
}

export function makeResponse(n: number, overrides: Partial<FilingResponse> = {}): FilingResponse {
  return {
    id: `re-${n}`,
    filing_id: "fi-1",
    response_type: "RECEIVED",
    response_type_label: "Recibida",
    received_at: "2026-11-11T10:00:00Z",
    public_message: null,
    external_reference: null,
    reason: null,
    internal_comment: null,
    observations: [],
    approved_amount_cop: null,
    approved_term_months: null,
    valid_until: null,
    disbursed_amount_cop: null,
    evidence: null,
    recorded_by: { id: "u-1", name: "Paula Rincón" },
    corrects_response_id: null,
    created_at: "2026-11-11T10:01:00Z",
    ...overrides,
  };
}

export const SNAPSHOT: FilingSnapshot = {
  id: "sn-1",
  slot_id: "s-1",
  document_file_id: "f-1",
  version_number: 2,
  document_type_code: "EMPLOYMENT_LETTER",
  document_type_label: "Certificado laboral",
  slot_label: "Certificado laboral",
  client_filename: "certificado.pdf",
  mime_type: "application/pdf",
  size_bytes: 182_334,
  created_at: "2026-11-10T14:31:00Z",
  sha256: "x",
};

const page = <T>(items: T[]) => ({
  items,
  page: 1,
  page_size: 100,
  total: items.length,
  next: null,
  previous: null,
});

export interface FilingsApi extends WorkspaceApi {
  filings: Filing[];
  /** Lo que responde el `POST` del paquete. */
  requested: PackageJob;
  /** Lo que responden los `GET` del paquete, en orden (el último se repite). */
  polled: PackageJob[];
  /** Lista de paquetes de la solicitud (`GET .../document-package-jobs`); el `POST` suma. */
  packageJobs: PackageJob[];
  /** Respuestas por radicación. */
  responses: Record<string, FilingResponse[]>;
  bodies: { filing: unknown[]; patch: unknown[]; response: Record<string, unknown>[] };
  calls: WorkspaceApi["calls"] & { packageGet: number; filings: number };
}

/** El expediente completo, más la radicación. Cada prueba cambia lo que necesita. */
export function useFilingsApi(
  overrides: Partial<Omit<FilingsApi, keyof WorkspaceApi>> & Partial<WorkspaceApi> = {},
): FilingsApi {
  const {
    filings = [],
    requested = makeJob(),
    polled,
    packageJobs = [],
    responses = {},
    ...workspace
  } = overrides;
  const base = useWorkspaceApi({
    detail: makeDetail({ status: "READY_TO_FILE", status_label: "Lista para radicar" }),
    permissions: FILING_PERMISSIONS,
    slots: [makeSlot(1, "Certificado laboral")],
    slotsTotal: 1,
    ...workspace,
  });
  // Mismo objeto que usan los handlers del expediente: cambiar `detail` aquí se ve allá.
  const state: FilingsApi = Object.assign(base, {
    filings,
    requested,
    polled: polled ?? [requested],
    packageJobs,
    responses,
    bodies: { filing: [], patch: [], response: [] },
    calls: Object.assign(base.calls, { packageGet: 0, filings: 0 }),
  });

  server.use(
    http.get(apiUrl("/metadata/bootstrap"), () => HttpResponse.json(FILING_BOOTSTRAP)),
    http.get(apiUrl(`/applications/${APP_ID}/filings`), () => {
      state.calls.filings += 1;
      return HttpResponse.json(page(state.filings));
    }),
    http.post(apiUrl(`/applications/${APP_ID}/document-package-jobs`), () => {
      state.packageJobs = [
        state.requested,
        ...state.packageJobs.filter((j) => j.id !== state.requested.id),
      ];
      return HttpResponse.json(state.requested, { status: 201 });
    }),
    http.get(apiUrl(`/applications/${APP_ID}/document-package-jobs`), () =>
      HttpResponse.json(page(state.packageJobs)),
    ),
    http.get(apiUrl("/document-package-jobs/:jobId"), () => {
      const job = state.polled[Math.min(state.calls.packageGet, state.polled.length - 1)]!;
      state.calls.packageGet += 1;
      return HttpResponse.json(job);
    }),
    http.get(apiUrl("/document-package-jobs/:jobId/download"), () =>
      HttpResponse.json({
        url: "https://s3.example/zip?sig=1",
        expires_at: "2026-11-17T15:00:00Z",
      }),
    ),
    http.post(apiUrl(`/applications/${APP_ID}/filings`), async ({ request }) => {
      const body = await request.json();
      state.bodies.filing.push(body);
      const created = makeFiling(state.filings.length + 1);
      state.filings = [created, ...state.filings];
      state.detail = { ...state.detail, status: "FILED", status_label: "Radicada" };
      return HttpResponse.json(created, { status: 201, headers: { ETag: '"16"' } });
    }),
    http.patch(apiUrl("/filings/:filingId"), async ({ request, params }) => {
      const body = (await request.json()) as Partial<Filing>;
      state.bodies.patch.push(body);
      state.filings = state.filings.map((f) => (f.id === params.filingId ? { ...f, ...body } : f));
      return HttpResponse.json(state.filings.find((f) => f.id === params.filingId));
    }),
    http.get(apiUrl("/filings/:filingId/responses"), ({ params }) =>
      HttpResponse.json(page(state.responses[params.filingId as string] ?? [])),
    ),
    http.post(apiUrl("/filings/:filingId/responses"), async ({ request, params }) => {
      const body = (await request.json()) as Record<string, unknown>;
      state.bodies.response.push(body);
      const id = params.filingId as string;
      const list = state.responses[id] ?? [];
      const created = makeResponse(100 + list.length, {
        filing_id: id,
        response_type: body.response_type as string,
        response_type_label: String(body.response_type),
      });
      state.responses[id] = [...list, created];
      return HttpResponse.json(created, { status: 201, headers: { ETag: '"16"' } });
    }),
    http.get(apiUrl("/filing-responses/:id/evidence/download"), () =>
      HttpResponse.json({
        url: "https://s3.example/evidence?sig=1",
        expires_at: "2026-11-17T15:00:00Z",
      }),
    ),
    http.get(apiUrl("/filings/:filingId/document-snapshots"), () =>
      HttpResponse.json(page([SNAPSHOT])),
    ),
  );
  return state;
}

/** Error con el formato de la API. */
export const apiError = (
  status: number,
  code: string,
  message: string,
  details: { field?: string | null; code: string; message: string }[] = [],
) =>
  HttpResponse.json(
    { code, message, details: details.map((d) => ({ field: null, ...d })), request_id: "r-1" },
    { status },
  );
