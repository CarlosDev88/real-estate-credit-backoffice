"use client";

import { toneFor } from "@design/status-tones";
import { Button } from "antd";
import { useId, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { StatusBadge, TONE_CLASS } from "@/components/ui/status-badge";
import { useSlotVersions } from "@/features/buyer-documents/documents-queries";
import {
  groupByParticipant,
  sortSlots,
  statusTabs,
  summaryText,
} from "@/features/buyer-documents/slot-format";
import { UploadSheet } from "@/features/buyer-documents/upload-sheet";
import { useBuyerViewer, type ViewTarget } from "@/features/buyer-documents/use-buyer-viewer";
import { usePortal } from "@/features/buyer-portal/portal-context";
import {
  useBuyerDetail,
  useBuyerSlots,
  type BuyerDocumentSlot,
} from "@/features/buyer-portal/queries";
import { formatDate, formatDateOnly } from "@/lib/format";

const ALL = "all";

type Viewer = ReturnType<typeof useBuyerViewer>;

function ViewButton({ viewer, target }: { viewer: Viewer; target: ViewTarget }) {
  return (
    <Button
      onClick={() => viewer.show(target)}
      loading={viewer.loadingFor(target.fileId)}
      aria-label={`Ver ${target.name}`}
    >
      Ver
    </Button>
  );
}

function Versions({
  slot,
  viewer,
  open,
}: {
  slot: BuyerDocumentSlot;
  viewer: Viewer;
  open: boolean;
}) {
  const { applicationId } = usePortal();
  const versions = useSlotVersions(applicationId, slot.id, open);
  if (!open) return null;
  if (versions.isPending) {
    return (
      <p role="status" className="text-text-tertiary m-0 text-sm">
        Cargando versiones…
      </p>
    );
  }
  if (versions.isError) {
    return <p className="text-text-secondary m-0 text-sm">{versions.error.message}</p>;
  }
  return (
    <ol className="m-0 grid list-none gap-2 p-0 text-sm">
      {versions.data.map((version) => {
        const rejection = [version.rejection?.reason?.label, version.rejection?.buyer_comment]
          .filter(Boolean)
          .join(": ");
        const error = viewer.errorFor(version.id);
        return (
          <li
            key={version.id}
            className="bg-bg-subtle flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <b className="font-medium">
                Versión {version.version_number}
                {version.is_current && (
                  <span className="text-text-tertiary font-normal"> · Vigente</span>
                )}
              </b>
              <span className="text-text-tertiary block break-all">
                {version.client_filename} · {formatDate(version.created_at)}
              </span>
              {rejection && (
                <span className="text-tone-danger-fg block">Motivo del rechazo: {rejection}</span>
              )}
              {error && (
                <span role="alert" className="text-tone-danger-fg block">
                  {error}
                </span>
              )}
            </div>
            <ViewButton
              viewer={viewer}
              target={{
                fileId: version.id,
                name: version.client_filename,
                mimeType: version.mime_type,
                sizeBytes: version.size_bytes,
              }}
            />
          </li>
        );
      })}
    </ol>
  );
}

/** "Declaración de renta · Juan Pablo Valencia": dos participantes pueden tener la misma etiqueta. */
export function slotName(slot: BuyerDocumentSlot): string {
  return slot.participant ? `${slot.label} · ${slot.participant.full_name}` : slot.label;
}

function SlotCard({
  slot,
  viewer,
  onUpload,
}: {
  slot: BuyerDocumentSlot;
  viewer: Viewer;
  onUpload: (slot: BuyerDocumentSlot) => void;
}) {
  const [showVersions, setShowVersions] = useState(false);
  const versionsId = useId();
  const titleId = useId();
  const file = slot.current_file;
  const rejection = slot.rejection;
  const tone = toneFor("documentSlot", slot.status);
  const fileError = viewer.errorFor(file?.id);

  return (
    <article
      aria-labelledby={titleId}
      className={`bg-bg-surface grid gap-3 rounded-xl border p-4 ${
        tone === "danger" ? "border-tone-danger-border" : "border-border-default"
      }`}
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className="m-0 text-lg font-semibold">
            {slot.label}
          </h3>
          {slot.document_type.description && (
            <p className="text-text-secondary m-0 text-sm">{slot.document_type.description}</p>
          )}
        </div>
        <StatusBadge kind="documentSlot" code={slot.status} label={slot.public_status_label} />
      </div>

      {file && (
        <p className="text-text-secondary m-0 text-sm break-all">
          <span className="text-text-primary font-medium">{file.client_filename}</span> · subido el{" "}
          {formatDate(file.created_at)}
          {file.expires_at && ` · sirve hasta el ${formatDateOnly(file.expires_at)}`}
        </p>
      )}

      {rejection && (
        <div className={`rounded-md border px-3 py-2 text-sm ${TONE_CLASS.danger}`}>
          {rejection.reason && <b className="block font-semibold">{rejection.reason.label}</b>}
          {rejection.buyer_comment && (
            <p className="text-text-primary m-0">{rejection.buyer_comment}</p>
          )}
        </div>
      )}

      {fileError && (
        <p role="alert" className="text-tone-danger-fg m-0 text-sm">
          {fileError}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {slot.can_upload && (
          <Button
            type={slot.needs_action ? "primary" : "default"}
            onClick={() => onUpload(slot)}
            aria-label={`${file ? "Reemplazar" : "Subir"} ${slotName(slot)}`}
          >
            {file ? "Reemplazar" : "Subir"}
          </Button>
        )}
        {file && (
          <ViewButton
            viewer={viewer}
            target={{
              fileId: file.id,
              name: file.client_filename,
              mimeType: file.mime_type,
              sizeBytes: file.size_bytes,
            }}
          />
        )}
        {file && (
          <Button
            type="text"
            aria-expanded={showVersions}
            aria-controls={versionsId}
            onClick={() => setShowVersions((v) => !v)}
          >
            Versiones
          </Button>
        )}
      </div>
      <div id={versionsId}>
        <Versions slot={slot} viewer={viewer} open={showVersions} />
      </div>
    </article>
  );
}

function ReadyBar({ done, total }: { done: number; total: number }) {
  const ratio = total > 0 ? Math.min(1, done / total) : 0;
  return (
    <div className="grid gap-1.5 min-[900px]:min-w-64">
      <div className="flex text-sm">
        <span className="text-text-secondary">Documentos listos</span>
        <span className="flex-1" />
        <b className="tabular-nums">
          {done} de {total}
        </b>
      </div>
      <div
        role="img"
        aria-label={`${done} de ${total} documentos listos`}
        className="bg-bg-muted h-2 overflow-hidden rounded-full"
      >
        <i
          className="bg-brand-primary block h-full w-full origin-left rounded-full"
          style={{ transform: `scaleX(${ratio})` }}
        />
      </div>
    </div>
  );
}

/** Documentos del comprador (`/portal/documentos`, mockup `portal-documentos.html`). */
export function BuyerDocumentsScreen() {
  const { applicationId } = usePortal();
  const slotsQuery = useBuyerSlots(applicationId);
  const detailQuery = useBuyerDetail(applicationId);
  const viewer = useBuyerViewer();
  const [tab, setTab] = useState(ALL);
  const [uploading, setUploading] = useState<BuyerDocumentSlot | null>(null);

  const slots = slotsQuery.data;
  const sorted = slots ? sortSlots(slots) : [];
  const tabs = statusTabs(sorted);
  // Si la pestaña elegida se queda sin documentos (por ejemplo, tras subir el último), vuelve a "Todos".
  const active = tab === ALL || tabs.some((t) => t.key === tab) ? tab : ALL;
  const visible = active === ALL ? sorted : sorted.filter((s) => s.public_status === active);
  const pending = sorted.filter((s) => s.needs_action).length;
  const progress = detailQuery.data?.detail.progress;

  return (
    <div className="mx-auto grid max-w-[480px] gap-5 px-4 py-5 min-[900px]:max-w-[960px] min-[900px]:px-5 min-[900px]:pt-8 min-[900px]:pb-12">
      <PageHeader
        variant="portal"
        title="Tus documentos"
        description={slots ? summaryText(pending) : undefined}
        actions={
          progress && (
            <div className="w-full min-[900px]:w-auto">
              <ReadyBar
                done={progress.documents_completed_total}
                total={progress.documents_required_total}
              />
            </div>
          )
        }
      />

      {slotsQuery.isPending && <LoadingState variant="portal" blocks={[112, 112]} />}

      {slotsQuery.isError && (
        <ErrorState
          variant="page"
          title="No pudimos cargar tus documentos"
          message={slotsQuery.error.message}
          onRetry={() => void slotsQuery.refetch()}
          retrying={slotsQuery.isFetching}
        />
      )}

      {slots && slots.length === 0 && (
        <p className="text-text-secondary m-0">Tu asesor todavía no te ha pedido documentos.</p>
      )}

      {slots && slots.length > 0 && (
        <>
          <ScrollTabs
            ariaLabel="Filtrar documentos por estado"
            value={active}
            onChange={setTab}
            items={[
              { key: ALL, label: "Todos", count: sorted.length },
              ...tabs.map((t) => ({ key: t.key, label: t.label, count: t.count })),
            ]}
          />
          <div className="grid gap-6">
            {groupByParticipant(visible).map((group) => (
              <section key={group.key} aria-label={group.name ?? "Documentos de la solicitud"}>
                <h2 className="text-text-secondary m-0 mb-2 text-sm font-medium">
                  {group.name ? `${group.name} · ${group.roleLabel}` : "Documentos de la solicitud"}
                </h2>
                <div className="grid gap-3">
                  {group.slots.map((slot) => (
                    <SlotCard key={slot.id} slot={slot} viewer={viewer} onUpload={setUploading} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </>
      )}

      <UploadSheet slot={uploading} onClose={() => setUploading(null)} />
      {viewer.viewer}
    </div>
  );
}
