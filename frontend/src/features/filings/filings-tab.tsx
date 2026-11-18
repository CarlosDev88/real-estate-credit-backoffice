"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useMe } from "@/features/auth/queries";
import type { Permissions } from "@/features/applications/workspace-header";
import type { ApplicationDetail } from "@/features/applications/workspace-queries";
import { useDocumentSlots } from "@/features/document-review/queries";
import { DeliveryPanel } from "@/features/filings/delivery-panel";
import { EvidenceModal, useEvidenceViewer } from "@/features/filings/evidence";
import { FilingBanner } from "@/features/filings/filing-banner";
import { FilingCard } from "@/features/filings/filing-card";
import { EditFilingModal } from "@/features/filings/filing-modals";
import {
  useFilingResponses,
  useFilings,
  type Filing,
  type FilingResponse,
} from "@/features/filings/queries";
import { RecordResponseModal } from "@/features/filings/response-modal";
import { ResponseTimeline } from "@/features/filings/response-timeline";

/** Estado en el que se entrega el paquete y se radica (API §20.1). */
export const READY_TO_FILE = "READY_TO_FILE";
/** Rol que ve los documentos entregados aunque no sea el asesor asignado (API §20). */
const ADMIN_ROLE = "ADMIN";
/** Si el slot ya no está en el expediente (o no se pueden leer los documentos). */
const UNKNOWN_SLOT = "Documento observado";

function isAdminOrAssigned(
  me: { id: string; roles: string[] } | undefined,
  detail: ApplicationDetail,
): boolean {
  return !!me && (me.roles.includes(ADMIN_ROLE) || me.id === detail.assigned_advisor.id);
}

interface Recording {
  filing: Filing;
  correcting: FilingResponse | null;
}

/** Pestaña "Radicación" del expediente: paquete, radicación y su historial. */
export function FilingsTab({
  detail,
  version,
  permissions,
  onOpenDocument,
}: {
  detail: ApplicationDetail;
  version: number;
  permissions: Permissions;
  /** Abre un documento en la pestaña Documentos (enlaces de las observaciones). */
  onOpenDocument: (slotId: string) => void;
}) {
  const filings = useFilings(detail.id);
  const me = useMe();
  const [editing, setEditing] = useState<Filing | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [attaching, setAttaching] = useState<FilingResponse | null>(null);
  const viewer = useEvidenceViewer();
  const slots = useDocumentSlots(detail.id);
  const latest = filings.data?.items[0];
  const latestResponses = useFilingResponses(latest?.id);

  const labels = new Map((slots.data ?? []).map((s) => [s.id, s.label]));
  const slotLabel = (slotId: string) => labels.get(slotId) ?? UNKNOWN_SLOT;

  const canPrepare = permissions.has("filings.prepare");
  const canCreate = permissions.has("filings.create");
  const isOwner = isAdminOrAssigned(me.data, detail);
  const isAdmin = !!me.data?.roles.includes(ADMIN_ROLE);
  const delivering = detail.status === READY_TO_FILE && (canPrepare || canCreate);
  const canRecord = permissions.has("filings.record_response") && detail.closed_at === null;
  const timelineCan = {
    record: canRecord,
    attachFor: (r: FilingResponse) =>
      permissions.has("filings.record_response") &&
      (isAdmin || (!!me.data && r.recorded_by?.id === me.data.id)),
  };

  return (
    <div className="grid gap-5">
      <FilingBanner
        detail={detail}
        responses={latestResponses.data}
        slotLabel={slotLabel}
        onOpenDocument={onOpenDocument}
      />
      {delivering && (
        <DeliveryPanel
          detail={detail}
          version={version}
          can={{ prepare: canPrepare, create: canCreate }}
        />
      )}

      {filings.isPending ? (
        <LoadingState label="Cargando radicaciones" blocks={[128]} />
      ) : filings.isError ? (
        <ErrorState
          title="No pudimos cargar las radicaciones"
          message={filings.error.message}
          onRetry={() => void filings.refetch()}
          retrying={filings.isFetching}
        />
      ) : filings.data.items.length === 0 ? (
        <div className="bg-bg-surface border-border-default rounded-lg border">
          <EmptyState
            title="Todavía no hay radicaciones"
            description="La radicación se registra después de entregar el paquete al banco."
          />
        </div>
      ) : (
        <section aria-labelledby="filings-title" className="grid gap-3">
          <h2 id="filings-title" className="m-0 text-lg leading-snug font-semibold">
            Radicaciones
          </h2>
          {filings.data.items.map((filing) => (
            <FilingCard
              key={filing.id}
              filing={filing}
              applicationId={detail.id}
              can={{ update: permissions.has("filings.update"), snapshots: isOwner }}
              onEdit={() => setEditing(filing)}
            >
              <ResponseTimeline
                filingId={filing.id}
                can={timelineCan}
                viewer={viewer}
                slotLabel={slotLabel}
                onOpenDocument={onOpenDocument}
                // Solo la última radicación recibe respuestas (API §20.2).
                onRecord={
                  canRecord && filing.id === latest?.id
                    ? () => setRecording({ filing, correcting: null })
                    : null
                }
                onCorrect={(response) => setRecording({ filing, correcting: response })}
                onAttach={setAttaching}
              />
            </FilingCard>
          ))}
        </section>
      )}

      <EditFilingModal
        applicationId={detail.id}
        filing={editing}
        onClose={() => setEditing(null)}
      />
      {recording && (
        <RecordResponseModal
          applicationId={detail.id}
          filing={recording.filing}
          version={version}
          open
          correcting={recording.correcting}
          onClose={() => setRecording(null)}
          onRecorded={(response) => {
            // La evidencia es opcional y va después de crear la respuesta.
            if (!recording.correcting) setAttaching(response);
          }}
        />
      )}
      <EvidenceModal response={attaching} onClose={() => setAttaching(null)} />
      {viewer.viewer}
    </div>
  );
}
