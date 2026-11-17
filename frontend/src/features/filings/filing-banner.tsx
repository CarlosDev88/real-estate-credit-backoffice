"use client";

import { Alert, Button } from "antd";

import type { ApplicationDetail } from "@/features/applications/workspace-queries";
import type { FilingResponse } from "@/features/filings/queries";

/** Estados de la solicitud con banner en la pestaña (API §20.2). */
const BANK_OBSERVATION = "BANK_OBSERVATION";
const APPROVED = "APPROVED";
/** Transiciones manuales que ya ofrece el encabezado del expediente (F1). */
const READY_TO_REFILE = "MARK_READY_TO_REFILE";
const START_LEGALIZATION = "START_LEGALIZATION";

/** Observaciones sin resolver de las respuestas de la última radicación. */
export function openObservations(responses: FilingResponse[]) {
  return responses.flatMap((r) => r.observations ?? []).filter((o) => !o.resolved_at);
}

/** "Usa «Iniciar legalización» en las acciones de la solicitud." si la acción está disponible. */
function actionHint(detail: ApplicationDetail, code: string, before: string): string | null {
  const action = detail.available_actions.find((a) => a.code === code);
  return action ? `${before}, usa «${action.label}» en las acciones de la solicitud.` : null;
}

/**
 * Banner del estado: en observación, los documentos que el banco observó (con enlace a
 * cada uno) y, cuando se resuelven, cómo radicar de nuevo; aprobada, cómo seguir.
 */
export function FilingBanner({
  detail,
  responses,
  slotLabel,
  onOpenDocument,
}: {
  detail: ApplicationDetail;
  /** Respuestas de la última radicación. */
  responses: FilingResponse[] | undefined;
  slotLabel: (slotId: string) => string;
  onOpenDocument: (slotId: string) => void;
}) {
  if (detail.status === APPROVED) {
    return (
      <Alert
        type="success"
        showIcon
        title="El banco aprobó el crédito"
        description={actionHint(detail, START_LEGALIZATION, "Para seguir con la legalización")}
      />
    );
  }
  if (detail.status !== BANK_OBSERVATION || !responses) return null;

  const open = openObservations(responses);
  if (open.length === 0) {
    return (
      <Alert
        type="info"
        showIcon
        title="Las observaciones del banco están resueltas"
        description={actionHint(detail, READY_TO_REFILE, "Para radicar de nuevo")}
      />
    );
  }
  return (
    <Alert
      type="warning"
      showIcon
      title={
        open.length === 1
          ? "El banco observó 1 documento"
          : `El banco observó ${open.length} documentos`
      }
      description={
        <div className="grid gap-1">
          <ul className="m-0 grid list-none gap-0.5 p-0">
            {open.map((o) => (
              <li key={o.id}>
                <Button
                  type="link"
                  size="small"
                  className="h-auto! px-0!"
                  onClick={() => onOpenDocument(o.document_slot_id)}
                >
                  {slotLabel(o.document_slot_id)}
                </Button>
                <span className="text-text-secondary"> · {o.reason.label}</span>
              </li>
            ))}
          </ul>
          <span className="text-text-secondary text-sm">
            Cada observación queda resuelta cuando apruebas la versión nueva del documento.
          </span>
        </div>
      }
    />
  );
}
