// Datos de prueba de la pestaña Documentos (solo para las pruebas con MSW).
import { http, HttpResponse } from "msw";

import { APP_ID } from "@/features/applications/workspace.fixtures";
import type { DocumentFile, DocumentSlot } from "@/features/document-review/queries";
import { apiUrl, server } from "@/test/msw-server";

const PEOPLE = {
  sofia: {
    id: "pa-1",
    role: "PRIMARY",
    client_id: "cl-1",
    full_name: "Sofía Herrera",
    is_active: true,
  },
  daniel: {
    id: "pa-2",
    role: "CO_APPLICANT",
    client_id: "cl-2",
    full_name: "Daniel Mejía",
    is_active: true,
  },
};

interface SlotSpec {
  id: string;
  label: string;
  participant: keyof typeof PEOPLE | null;
  status: DocumentSlot["status"];
  scan?: string;
  validity?: number | null;
  waivable?: boolean;
  retired?: boolean;
  waiver?: string;
  documentDate?: string | null;
}

function slot(spec: SlotSpec, order: number): DocumentSlot {
  const hasFile = spec.status !== "PENDING" && spec.status !== "WAIVED";
  return {
    id: spec.id,
    application_id: APP_ID,
    participant: spec.participant ? PEOPLE[spec.participant] : null,
    document_type: {
      id: `dt-${spec.id}`,
      code: "DOC",
      name: spec.label,
      is_active: true,
      holder_scope: spec.participant ? "PARTICIPANT" : "APPLICATION",
      allowed_mime_types: [],
      max_size_bytes: 1,
    },
    label: spec.label,
    slot_index: 1,
    requirement_id: null,
    requirement_version: null,
    is_required: true,
    is_waivable: spec.waivable ?? false,
    minimum_files: 1,
    alternative_group_code: null,
    validity_days: spec.validity ?? null,
    sort_order: order,
    status: spec.status,
    waiver_reason: spec.waiver ? { code: "NOT_APPLICABLE", label: spec.waiver } : null,
    current_file: hasFile
      ? {
          id: `f-${spec.id}`,
          version_number: 2,
          status: spec.status === "UPLOADED" ? "IN_REVIEW" : spec.status,
          client_filename: `${spec.id}.pdf`,
          document_date: spec.documentDate ?? null,
          expires_at: spec.validity ? "2026-12-02" : null,
          scan_status: spec.scan ?? "CLEAN",
          created_at: "2026-11-10T09:00:00Z",
        }
      : null,
    locked_at: null,
    is_retired: spec.retired ?? false,
    retired_at: spec.retired ? "2026-11-05T09:00:00Z" : null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-10T09:00:00Z",
  } as DocumentSlot;
}

// En el orden de la API: los de la solicitud primero y después los de cada participante.
export const SLOT_SPECS: SlotSpec[] = [
  { id: "promesa", label: "Promesa de compraventa", participant: null, status: "UPLOADED" },
  {
    id: "tradicion",
    label: "Certificado de tradición",
    participant: null,
    status: "WAIVED",
    waiver: "No aplica al inmueble",
  },
  { id: "cedula", label: "Documento de identidad", participant: "sofia", status: "APPROVED" },
  {
    id: "laboral",
    label: "Certificado laboral",
    participant: "sofia",
    status: "UPLOADED",
    validity: 30,
    documentDate: "2026-11-02",
  },
  {
    id: "nomina",
    label: "Desprendible de nómina 2 de 3",
    participant: "sofia",
    status: "REJECTED",
  },
  {
    id: "viejo",
    label: "Documento retirado",
    participant: "sofia",
    status: "PENDING",
    retired: true,
  },
  {
    id: "extracto",
    label: "Extracto bancario 1 de 3",
    participant: "daniel",
    status: "PENDING",
    waivable: true,
  },
  {
    id: "cedula2",
    label: "Cédula del co-solicitante",
    participant: "daniel",
    status: "UPLOADED",
    scan: "PENDING",
  },
  {
    id: "infectado",
    label: "Soporte de ingresos",
    participant: "daniel",
    status: "UPLOADED",
    scan: "INFECTED",
  },
];

export const makeSlots = (specs: SlotSpec[] = SLOT_SPECS) => specs.map(slot);

export function makeFile(slotSpec: SlotSpec, overrides: Partial<DocumentFile> = {}): DocumentFile {
  return {
    id: `f-${slotSpec.id}`,
    slot_id: slotSpec.id,
    version_number: 2,
    status: "IN_REVIEW",
    is_current: true,
    client_filename: `${slotSpec.id}.pdf`,
    document_date: slotSpec.documentDate ?? null,
    expires_at: null,
    uploaded_by_buyer_session_id: "s-1",
    file: {
      id: `fm-${slotSpec.id}`,
      detected_mime_type: slotSpec.id === "cedula" ? "image/png" : "application/pdf",
      size_bytes: 421_888,
      sha256: "x",
      scan_status: slotSpec.scan ?? "CLEAN",
      scanned_at: null,
    },
    reviews:
      slotSpec.status === "REJECTED"
        ? [
            {
              id: "rv-1",
              decision: "REJECTED",
              reason: { code: "ILLEGIBLE", label: "Ilegible" },
              buyer_comment: "La foto está borrosa.",
              internal_comment: null,
              reviewer: { id: "u-1", name: "Paula Rincón" },
              created_at: "2026-11-09T10:00:00Z",
            },
          ]
        : [],
    created_at: "2026-11-10T09:00:00Z",
    ...overrides,
  } as DocumentFile;
}

export interface DocumentsApi {
  reviews: { slotId: string; body: Record<string, unknown> }[];
  downloads: string[];
  /** Respuesta de la descarga: la URL o un error con su estado. */
  download: { status: number; code?: string; message?: string };
  reviewError: { status: number; body: Record<string, unknown> } | null;
}

const SPEC_BY_FILE = new Map(SLOT_SPECS.map((s) => [`f-${s.id}`, s]));

/** Handlers de la pestaña Documentos (sobre los del expediente). */
export function useDocumentsApi(overrides: Partial<DocumentsApi> = {}): DocumentsApi {
  const state: DocumentsApi = {
    reviews: [],
    downloads: [],
    download: { status: 200 },
    reviewError: null,
    ...overrides,
  };
  let slots = makeSlots();
  server.use(
    http.get(apiUrl(`/applications/${APP_ID}/document-slots`), ({ request }) => {
      const status = new URL(request.url).searchParams.get("status");
      const items = status ? slots.filter((s) => s.status === status) : slots;
      return HttpResponse.json({
        items,
        page: 1,
        page_size: 100,
        total: items.length,
        next: null,
        previous: null,
      });
    }),
    http.get(apiUrl("/document-files/:id"), ({ params }) => {
      const spec = SPEC_BY_FILE.get(String(params.id));
      return spec
        ? HttpResponse.json(makeFile(spec))
        : HttpResponse.json(
            { code: "RESOURCE_NOT_FOUND", message: "x", details: [], request_id: "r" },
            { status: 404 },
          );
    }),
    http.get(apiUrl("/document-files/:id/scan-status"), ({ params }) => {
      const spec = SPEC_BY_FILE.get(String(params.id))!;
      return HttpResponse.json({
        document_file_id: params.id,
        status: "IN_REVIEW",
        scan_status: spec.scan ?? "CLEAN",
        scanned_at: null,
        detected_mime_type: "application/pdf",
        size_bytes: 421_888,
        sha256: "x",
      });
    }),
    http.get(apiUrl("/document-files/:id/download"), ({ params }) => {
      state.downloads.push(String(params.id));
      if (state.download.status !== 200) {
        return HttpResponse.json(
          {
            code: state.download.code ?? "SERVICE_UNAVAILABLE",
            message: state.download.message ?? "El almacenamiento no está disponible.",
            details: [],
            request_id: "r",
          },
          { status: state.download.status },
        );
      }
      return HttpResponse.json({
        url: `http://localhost:3000/api/v1/storage/objects/${String(params.id)}-${state.downloads.length}`,
        expires_at: "2026-11-12T10:05:00Z",
      });
    }),
    http.get(apiUrl("/document-slots/:id/versions"), ({ params }) => {
      const spec = SLOT_SPECS.find((s) => s.id === params.id)!;
      const old = makeFile(spec, {
        id: `old-${spec.id}`,
        version_number: 1,
        is_current: false,
        client_filename: `${spec.id}-v1.pdf`,
        reviews: [
          {
            id: "rv-0",
            decision: "REJECTED",
            reason: null,
            buyer_comment: "Estaba vencido.",
            internal_comment: null,
            reviewer: { id: "u-1", name: "Paula Rincón" },
            created_at: "2026-11-05T10:00:00Z",
          },
        ],
      });
      return HttpResponse.json({
        items: [makeFile(spec), old],
        page: 1,
        page_size: 50,
        total: 2,
        next: null,
        previous: null,
      });
    }),
    http.patch(apiUrl("/document-slots/:id/review"), async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      state.reviews.push({ slotId: String(params.id), body });
      if (state.reviewError) {
        return HttpResponse.json(state.reviewError.body, { status: state.reviewError.status });
      }
      const decision = String(body.decision);
      const status = decision === "REOPENED" ? "PENDING" : decision;
      slots = slots.map((s) => (s.id === params.id ? ({ ...s, status } as DocumentSlot) : s));
      return HttpResponse.json({ slots: slots.filter((s) => s.id === params.id) });
    }),
  );
  return state;
}
