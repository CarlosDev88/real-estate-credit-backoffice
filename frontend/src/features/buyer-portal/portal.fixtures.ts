import { http, HttpResponse } from "msw";

import type { BuyerConsent, BuyerSession } from "@/features/buyer-portal/queries";
import { apiUrl } from "@/test/msw-server";

export const APP_ID = "0b8e6a52-1f7e-4c55-9d6a-3f2c4a1b2c3d";

export function sessionFixture(overrides: Partial<BuyerSession> = {}): BuyerSession {
  return {
    session: {
      id: "s-1",
      created_at: "2026-11-17T10:00:00Z",
      expires_at: new Date(Date.now() + 21 * 3_600_000 + 60_000).toISOString(),
    },
    buyer: { display_name: "Sofía Herrera" },
    application: {
      id: APP_ID,
      code: "SOL-000182",
      public_status: "WAITING_DOCUMENTS",
      public_status_label: "Estamos revisando tus documentos",
      is_editable: true,
      is_closed: false,
    },
    pending_consents: [],
    ...overrides,
  };
}

export function consentFixture(overrides: Partial<BuyerConsent> = {}): BuyerConsent {
  return {
    id: "c-data",
    code: "DATA_PROCESSING",
    version: 1,
    title: "Tratamiento de datos personales",
    body: "Autorizo el tratamiento de mis datos.",
    content_hash: "h",
    effective_from: "2026-01-01T00:00:00Z",
    required: true,
    status: "PENDING",
    accepted_at: null,
    ...overrides,
  };
}

export function apiError(status: number, code: string, message = "Error de prueba.") {
  return HttpResponse.json({ code, message, details: [], request_id: "req-1" }, { status });
}

/** Sesión y slots vacíos: lo mínimo para pintar el marco del portal. */
export function portalHandlers(session: BuyerSession = sessionFixture()) {
  return [
    http.get(apiUrl("/buyer/session"), () => HttpResponse.json(session)),
    http.get(apiUrl(`/buyer/applications/${session.application.id}/document-slots`), () =>
      HttpResponse.json({
        items: [],
        page: 1,
        page_size: 100,
        total: 0,
        next: null,
        previous: null,
      }),
    ),
  ];
}
