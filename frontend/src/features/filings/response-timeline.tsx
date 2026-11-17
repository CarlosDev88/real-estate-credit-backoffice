"use client";

import { Button } from "antd";
import type { ReactNode } from "react";

import { Money } from "@/components/ui/money";
import { StatusBadge } from "@/components/ui/status-badge";
import type { useEvidenceViewer } from "@/features/filings/evidence";
import {
  EVIDENCE_SCAN_CLEAN,
  EVIDENCE_SCAN_PENDING,
  useFilingResponses,
  type FilingResponse,
} from "@/features/filings/queries";
import { formatBytes, formatDateOnly, formatDateTime } from "@/lib/format";

export interface TimelinePermissions {
  /** `filings.record_response` en la última radicación: registrar y corregir. */
  record: boolean;
  /** Quien registró la respuesta o un administrador: adjuntar evidencia. */
  attachFor: (response: FilingResponse) => boolean;
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <p className="m-0 text-sm">
      <span className="text-text-tertiary">{label}: </span>
      {children}
    </p>
  );
}

function months(n: number) {
  return n === 1 ? "1 mes" : `${n} meses`;
}

/** Texto de la evidencia según su análisis; la API no manda la etiqueta (ver "Brechas"). */
function scanNote(status: string): string | null {
  if (status === EVIDENCE_SCAN_CLEAN) return null;
  if (status === EVIDENCE_SCAN_PENDING) return "Se está analizando el archivo.";
  return "El archivo no pasó el análisis y no se puede abrir.";
}

function ResponseItem({
  response,
  corrected,
  isLast,
  can,
  viewer,
  slotLabel,
  onOpenDocument,
  onCorrect,
  onAttach,
}: {
  response: FilingResponse;
  corrected: boolean;
  isLast: boolean;
  can: TimelinePermissions;
  viewer: ReturnType<typeof useEvidenceViewer>;
  slotLabel: (slotId: string) => string;
  onOpenDocument: (slotId: string) => void;
  onCorrect: () => void;
  onAttach: () => void;
}) {
  const evidence = response.evidence;
  const scan = evidence ? scanNote(evidence.scan_status) : null;
  const viewError = viewer.errorFor(response.id);
  const hasAmounts =
    response.approved_amount_cop != null ||
    response.approved_term_months != null ||
    response.valid_until != null ||
    response.disbursed_amount_cop != null;

  return (
    <li className="relative grid gap-1.5 pb-4 pl-4 last:pb-0">
      <span
        aria-hidden="true"
        className="bg-border-strong absolute top-1.5 -left-[5.5px] size-2.5 rounded-full"
      />
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge
          kind="filing"
          code={response.response_type}
          label={response.response_type_label}
        />
        <span className="text-text-secondary text-sm">{formatDateTime(response.received_at)}</span>
        {response.external_reference && (
          <span className="text-text-tertiary font-mono text-xs">
            {response.external_reference}
          </span>
        )}
        {response.corrects_response_id && (
          <span className="text-text-tertiary text-xs">· Corrige la anterior</span>
        )}
        {corrected && <span className="text-text-tertiary text-xs">· Corregida después</span>}
      </div>

      {response.reason && <Line label="Motivo">{response.reason.label}</Line>}
      {response.public_message && (
        <Line label="Mensaje al comprador">{response.public_message}</Line>
      )}
      {hasAmounts && (
        <dl className="m-0 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {response.approved_amount_cop != null && (
            <div>
              <dt className="text-text-tertiary inline">Monto aprobado: </dt>
              <dd className="m-0 inline font-medium">
                <Money value={response.approved_amount_cop} />
              </dd>
            </div>
          )}
          {response.approved_term_months != null && (
            <div>
              <dt className="text-text-tertiary inline">Plazo: </dt>
              <dd className="m-0 inline font-medium">{months(response.approved_term_months)}</dd>
            </div>
          )}
          {response.valid_until && (
            <div>
              <dt className="text-text-tertiary inline">Vigente hasta: </dt>
              <dd className="m-0 inline font-medium">{formatDateOnly(response.valid_until)}</dd>
            </div>
          )}
          {response.disbursed_amount_cop != null && (
            <div>
              <dt className="text-text-tertiary inline">Monto desembolsado: </dt>
              <dd className="m-0 inline font-medium">
                <Money value={response.disbursed_amount_cop} />
              </dd>
            </div>
          )}
        </dl>
      )}

      {response.observations && response.observations.length > 0 && (
        <div className="grid gap-1">
          <span className="text-text-tertiary text-sm">Documentos observados:</span>
          <ul className="m-0 grid list-none gap-1.5 p-0">
            {response.observations.map((o) => (
              <li key={o.id} className="bg-bg-subtle rounded-md px-3 py-2 text-sm">
                <Button
                  type="link"
                  size="small"
                  className="h-auto! px-0! font-medium"
                  onClick={() => onOpenDocument(o.document_slot_id)}
                >
                  {slotLabel(o.document_slot_id)}
                </Button>
                <span className="text-text-tertiary"> · {o.reason.label}</span>
                {o.resolved_at && (
                  <span className="text-tone-success-fg">
                    {" "}
                    · Resuelta el {formatDateTime(o.resolved_at)}
                  </span>
                )}
                <span className="block">{o.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {response.internal_comment && <Line label="Nota interna">{response.internal_comment}</Line>}

      {evidence && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-text-tertiary">Evidencia:</span>
          <span className="min-w-0 truncate">
            {evidence.filename} · {formatBytes(evidence.size_bytes)}
          </span>
          {evidence.scan_status === EVIDENCE_SCAN_CLEAN && (
            <Button
              size="small"
              loading={viewer.loadingFor(response.id)}
              onClick={() => viewer.show(response)}
            >
              Ver evidencia
            </Button>
          )}
          {scan && (
            <span role="status" className="text-tone-warning-fg text-xs">
              {scan}
            </span>
          )}
          {viewError && (
            <span role="alert" className="text-tone-danger-fg text-xs">
              {viewError}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {response.recorded_by && (
          <span className="text-text-tertiary text-xs">Registró {response.recorded_by.name}</span>
        )}
        {evidence === null && can.attachFor(response) && (
          <Button size="small" type="text" onClick={onAttach}>
            Adjuntar evidencia
          </Button>
        )}
        {isLast && can.record && (
          <Button size="small" type="text" onClick={onCorrect}>
            Corregir esta respuesta
          </Button>
        )}
      </div>
    </li>
  );
}

/** Respuestas del banco de una radicación, en orden cronológico. */
export function ResponseTimeline({
  filingId,
  can,
  viewer,
  slotLabel,
  onOpenDocument,
  onRecord,
  onCorrect,
  onAttach,
}: {
  filingId: string;
  can: TimelinePermissions;
  viewer: ReturnType<typeof useEvidenceViewer>;
  slotLabel: (slotId: string) => string;
  onOpenDocument: (slotId: string) => void;
  /** Solo en la última radicación, con permiso. */
  onRecord: (() => void) | null;
  onCorrect: (response: FilingResponse) => void;
  onAttach: (response: FilingResponse) => void;
}) {
  const responses = useFilingResponses(filingId);
  const items = responses.data ?? [];
  const correctedIds = new Set(items.map((r) => r.corrects_response_id).filter(Boolean));

  return (
    <section
      aria-label="Respuestas del banco"
      className="border-border-default grid gap-3 border-t pt-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="m-0 text-sm font-semibold">Respuestas del banco</h4>
        <div className="flex-1" />
        {/* Botón normal: la acción principal de la vista es la del encabezado. */}
        {onRecord && (
          <Button size="small" onClick={onRecord}>
            Registrar respuesta
          </Button>
        )}
      </div>
      {responses.isPending ? (
        <p role="status" className="text-text-tertiary m-0 text-sm">
          Cargando las respuestas…
        </p>
      ) : responses.isError ? (
        <div role="alert" className="flex items-center gap-2 text-sm">
          <span className="text-text-tertiary">No pudimos cargar las respuestas.</span>
          <Button size="small" onClick={() => void responses.refetch()}>
            Reintentar
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="text-text-tertiary m-0 text-sm">El banco todavía no ha respondido.</p>
      ) : (
        <ol className="border-border-default m-0 ml-1 grid list-none border-l p-0 pl-0">
          {items.map((response, i) => (
            <ResponseItem
              key={response.id}
              response={response}
              corrected={correctedIds.has(response.id)}
              isLast={i === items.length - 1 && !!onRecord}
              can={can}
              viewer={viewer}
              slotLabel={slotLabel}
              onOpenDocument={onOpenDocument}
              onCorrect={() => onCorrect(response)}
              onAttach={() => onAttach(response)}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
