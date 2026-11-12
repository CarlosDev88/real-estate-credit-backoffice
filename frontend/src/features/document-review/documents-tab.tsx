"use client";

import { Alert, Button } from "antd";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/ui/status-badge";
import { HouseIcon } from "@/components/ui/icons";
import type { FinancialProfile, Participant } from "@/features/applications/workspace-queries";
import {
  useCurrentFiles,
  useDocumentSlots,
  type DocumentFile,
  type DocumentSlot,
} from "@/features/document-review/queries";
import { ReviewDrawer } from "@/features/document-review/review-drawer";
import { ReopenModal, useFileViewer, WaiveModal } from "@/features/document-review/slot-dialogs";
import {
  isAwaitingReview,
  scanMessage,
  slotActions,
  useSlotStatusLabel,
  validityText,
  type SlotPermissions,
} from "@/features/document-review/slot-rules";
import { formatBytes } from "@/lib/format";

/** Título del grupo de los documentos de la solicitud (sin participante). */
export const APPLICATION_GROUP_TITLE = "Solicitud";
const APPLICATION_GROUP_NOTE = "Inmueble y trámite";

interface Group {
  key: string;
  title: string;
  note: string | null;
  initials: string | null;
  slots: DocumentSlot[];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts.slice(0, 1);
  return letters.map((p) => p?.charAt(0).toUpperCase() ?? "").join("");
}

/**
 * Grupos por participante, en el orden de los participantes, y al final los de la
 * solicitud ("Solicitud · Inmueble y trámite"), como en el mockup.
 */
export function groupSlots(
  slots: DocumentSlot[],
  participants: Participant[],
  profiles: Map<string, FinancialProfile>,
): Group[] {
  const byParticipant = new Map<string, DocumentSlot[]>();
  const own: DocumentSlot[] = [];
  for (const slot of slots) {
    if (!slot.participant) own.push(slot);
    else
      byParticipant.set(slot.participant.id, [
        ...(byParticipant.get(slot.participant.id) ?? []),
        slot,
      ]);
  }
  const order = [
    ...participants.map((p) => p.id),
    ...[...byParticipant.keys()].filter((id) => !participants.some((p) => p.id === id)),
  ];
  const groups: Group[] = [];
  for (const id of order) {
    const list = byParticipant.get(id);
    if (!list?.length) continue;
    const name = list[0]!.participant!.full_name;
    groups.push({
      key: id,
      title: name,
      note: profiles.get(id)?.employment_profile.label ?? null,
      initials: initials(name),
      slots: list,
    });
  }
  if (own.length) {
    groups.push({
      key: "application",
      title: APPLICATION_GROUP_TITLE,
      note: APPLICATION_GROUP_NOTE,
      initials: null,
      slots: own,
    });
  }
  return groups;
}

function DocIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={16} height={16} aria-hidden="true">
      <path d="M5 2h7l4 4v12H5V2Zm7 1.5V7h3.5L12 3.5Z" />
    </svg>
  );
}

/** Mensaje al comprador del último rechazo de la versión vigente. */
function rejectionMessage(slot: DocumentSlot, file: DocumentFile | undefined): string | null {
  if (slot.status !== "REJECTED") return null;
  const last = file?.reviews[0];
  return last?.decision === "REJECTED" ? (last.buyer_comment ?? null) : null;
}

interface RowProps {
  slot: DocumentSlot;
  file: DocumentFile | undefined;
  statusLabel: string;
  can: SlotPermissions;
  viewer: ReturnType<typeof useFileViewer>;
  onReview: () => void;
  onWaive: () => void;
  onReopen: () => void;
}

function SlotRow({ slot, file, statusLabel, can, viewer, onReview, onWaive, onReopen }: RowProps) {
  const actions = slotActions(slot, can);
  const current = slot.current_file;
  const facts = current
    ? [current.client_filename, formatBytes(file?.file.size_bytes), validityText(slot)]
    : [slot.waiver_reason ? `Exonerado: ${slot.waiver_reason.label}` : "Sin archivo"];
  const scan = scanMessage(current?.scan_status);
  const rejection = rejectionMessage(slot, file);
  const viewError = viewer.errorFor(current?.id);

  return (
    <li
      className={`border-border-default grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border px-4 py-2.5 min-[861px]:grid-cols-[auto_minmax(0,1fr)_auto_auto] ${
        current ? "bg-bg-surface" : "bg-bg-subtle border-dashed"
      }`}
    >
      <span className="bg-bg-muted text-text-secondary grid size-[34px] place-items-center rounded-md">
        <DocIcon />
      </span>
      <div className="min-w-0">
        <div className="font-medium">{slot.label}</div>
        <div className="text-text-tertiary truncate text-xs">
          {facts.filter(Boolean).join(" · ")}
        </div>
      </div>
      <span className="col-start-2 row-start-2 justify-self-start min-[861px]:col-start-auto min-[861px]:row-start-auto">
        <StatusBadge kind="documentSlot" code={slot.status} label={statusLabel} />
      </span>
      <div className="col-start-3 row-start-1 flex flex-wrap justify-end gap-1 min-[861px]:col-start-auto">
        {actions.view && current && (
          <Button
            size="small"
            type="text"
            loading={viewer.loadingFor(current.id)}
            onClick={() =>
              viewer.show({
                fileId: current.id,
                name: current.client_filename,
                mimeType: file?.file.detected_mime_type,
                sizeBytes: file?.file.size_bytes,
              })
            }
          >
            Ver<span className="sr-only"> {slot.label}</span>
          </Button>
        )}
        {actions.review && (
          <Button size="small" onClick={onReview}>
            Revisar<span className="sr-only"> {slot.label}</span>
          </Button>
        )}
        {actions.waive && (
          <Button size="small" type="text" onClick={onWaive}>
            Exonerar<span className="sr-only"> {slot.label}</span>
          </Button>
        )}
        {actions.reopen && (
          <Button size="small" type="text" onClick={onReopen}>
            Reabrir<span className="sr-only"> {slot.label}</span>
          </Button>
        )}
      </div>
      {(rejection || scan || viewError) && (
        <div className="col-span-full grid gap-1 min-[861px]:col-start-2">
          {rejection && (
            <p className="bg-tone-danger-bg text-tone-danger-fg m-0 rounded-md px-2.5 py-1.5 text-sm">
              Mensaje al comprador: {rejection}
            </p>
          )}
          {scan && (
            <p className="text-tone-warning-fg m-0 text-sm" role="status">
              {scan}
            </p>
          )}
          {viewError && (
            <p className="text-tone-danger-fg m-0 text-sm" role="alert">
              {viewError}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

interface DocumentsTabProps {
  applicationId: string;
  participants: Participant[];
  profiles: Map<string, FinancialProfile>;
  can: SlotPermissions;
  /** Slot abierto en el panel (`?slot=`), o `null`. */
  openSlotId: string | null;
  onOpenSlot: (slotId: string | null) => void;
}

/** Pestaña Documentos: slots agrupados, acciones por fila, panel de revisión y visor. */
export function DocumentsTab({
  applicationId,
  participants,
  profiles,
  can,
  openSlotId,
  onOpenSlot,
}: DocumentsTabProps) {
  const slots = useDocumentSlots(applicationId);
  const files = useCurrentFiles(slots.data);
  const statusLabel = useSlotStatusLabel();
  const viewer = useFileViewer();
  const [waiving, setWaiving] = useState<DocumentSlot | null>(null);
  const [reopening, setReopening] = useState<DocumentSlot | null>(null);

  const groups = useMemo(
    () => groupSlots(slots.data ?? [], participants, profiles),
    [slots.data, participants, profiles],
  );
  const ordered = groups.flatMap((g) => g.slots);
  const open = ordered.find((s) => s.id === openSlotId) ?? null;

  // Siguiente por revisar, en el orden de la pantalla, después del abierto.
  const next = useMemo(() => {
    if (!open) return null;
    const index = ordered.indexOf(open);
    const rest = [...ordered.slice(index + 1), ...ordered.slice(0, index)];
    return rest.find(isAwaitingReview) ?? null;
  }, [open, ordered]);

  if (slots.isPending) {
    return (
      <div
        role="status"
        aria-label="Cargando documentos"
        className="bg-bg-surface border-border-default h-40 animate-pulse rounded-lg border"
      />
    );
  }
  if (slots.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="No pudimos cargar los documentos"
        description={slots.error.message}
        action={
          <Button size="small" onClick={() => void slots.refetch()}>
            Reintentar
          </Button>
        }
      />
    );
  }

  return (
    <div className="bg-bg-surface border-border-default rounded-lg border p-5">
      {groups.length === 0 ? (
        <p className="text-text-tertiary m-0 text-sm">Esta solicitud todavía no pide documentos.</p>
      ) : (
        <div className="grid gap-6">
          {groups.map((group) => (
            <section key={group.key} aria-labelledby={`group-${group.key}`}>
              <h3
                id={`group-${group.key}`}
                className="m-0 mb-3 flex items-center gap-2 text-base font-semibold"
              >
                <span
                  aria-hidden="true"
                  className="bg-bg-muted text-text-secondary grid size-6 place-items-center rounded-full text-[10px] font-semibold"
                >
                  {group.initials ?? <HouseIcon width={12} height={12} />}
                </span>
                {group.title}
                {group.note && (
                  <span className="text-text-tertiary font-normal">· {group.note}</span>
                )}
              </h3>
              <ul className="m-0 grid list-none gap-2 p-0">
                {group.slots.map((slot) => (
                  <SlotRow
                    key={slot.id}
                    slot={slot}
                    file={slot.current_file ? files.get(slot.current_file.id) : undefined}
                    statusLabel={statusLabel(slot.status)}
                    can={can}
                    viewer={viewer}
                    onReview={() => onOpenSlot(slot.id)}
                    onWaive={() => setWaiving(slot)}
                    onReopen={() => setReopening(slot)}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <ReviewDrawer
        applicationId={applicationId}
        slot={open}
        holder={open?.participant?.full_name ?? APPLICATION_GROUP_TITLE}
        next={next}
        onNext={(slot) => onOpenSlot(slot.id)}
        onClose={() => onOpenSlot(null)}
        viewer={viewer}
        can={can}
      />
      <WaiveModal applicationId={applicationId} slot={waiving} onClose={() => setWaiving(null)} />
      <ReopenModal
        applicationId={applicationId}
        slot={reopening}
        onClose={() => setReopening(null)}
      />
      {viewer.viewer}
    </div>
  );
}
