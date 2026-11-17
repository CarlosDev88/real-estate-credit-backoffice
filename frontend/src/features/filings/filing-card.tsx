"use client";

import { Button } from "antd";
import { useId, useState } from "react";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/ui/status-badge";
import { useDocumentSlots } from "@/features/document-review/queries";
import { productLabel } from "@/features/filings/filing-modals";
import { useFilingSnapshots, type Filing } from "@/features/filings/queries";
import { formatBytes, formatDateTime } from "@/lib/format";

export interface FilingCardPermissions {
  /** `filings.update`: corregir referencia o comentario. */
  update: boolean;
  /** Administrador o asesor asignado: ver los documentos entregados (API §20). */
  snapshots: boolean;
}

/**
 * La respuesta esperada venció: pasó `target_response_at` y el banco todavía no
 * respondió nada (sin respuestas registradas).
 */
export function isResponseOverdue(filing: Filing, now: number = Date.now()): boolean {
  return (
    !!filing.target_response_at &&
    filing.responses_count === 0 &&
    Date.parse(filing.target_response_at) < now
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary text-xs">{label}</dt>
      <dd className="m-0 text-sm font-medium break-words">{children}</dd>
    </div>
  );
}

const DASH = <span className="text-text-tertiary font-normal">—</span>;

/** Versiones entregadas, con la etiqueta del slot si sigue en el expediente. */
function Snapshots({ applicationId, filingId }: { applicationId: string; filingId: string }) {
  const snapshots = useFilingSnapshots(filingId, true);
  const slots = useDocumentSlots(applicationId);
  const labels = new Map((slots.data ?? []).map((s) => [s.id, s.label]));

  if (snapshots.isPending) {
    return (
      <p role="status" className="text-text-tertiary m-0 text-sm">
        Cargando los documentos…
      </p>
    );
  }
  if (snapshots.isError) {
    return (
      <div role="alert" className="flex items-center gap-2 text-sm">
        <span className="text-text-tertiary">No pudimos cargar los documentos entregados.</span>
        <Button size="small" onClick={() => void snapshots.refetch()}>
          Reintentar
        </Button>
      </div>
    );
  }
  const items = snapshots.data.items;
  if (items.length === 0) {
    return <p className="text-text-tertiary m-0 text-sm">No se entregaron archivos.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-1.5 p-0">
      {items.map((s) => (
        <li
          key={s.id}
          className="grid gap-0.5 text-sm min-[861px]:grid-cols-[minmax(0,1fr)_auto] min-[861px]:gap-3"
        >
          <span className="min-w-0 truncate font-medium">
            {labels.get(s.slot_id) ?? s.document_type_code}
          </span>
          <span className="text-text-tertiary min-w-0 truncate text-xs">
            {[`Versión ${s.version_number}`, s.client_filename, formatBytes(s.size_bytes)]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Una radicación: banco y producto, canal, referencia, quién, cuándo y su estado. */
export function FilingCard({
  filing,
  applicationId,
  can,
  onEdit,
  children,
}: {
  filing: Filing;
  applicationId: string;
  can: FilingCardPermissions;
  onEdit: () => void;
  /** Lo que va debajo (las respuestas del banco). */
  children?: ReactNode;
}) {
  const ids = useId();
  const [showSnapshots, setShowSnapshots] = useState(false);
  const overdue = isResponseOverdue(filing);
  const titleId = `${ids}-title`;

  return (
    <article
      aria-labelledby={titleId}
      className="bg-bg-surface border-border-default grid gap-4 rounded-lg border p-5"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h3 id={titleId} className="m-0 flex min-w-0 items-baseline gap-2 text-base font-semibold">
          <span className="font-mono">#{filing.sequence_number}</span>
          <span className="min-w-0">{productLabel(filing.bank_product)}</span>
        </h3>
        <StatusBadge kind="filing" code={filing.status} label={filing.status_label} />
        <div className="flex-1" />
        {can.update && (
          <Button size="small" onClick={onEdit}>
            Corregir referencia o comentario
            <span className="sr-only"> de la radicación #{filing.sequence_number}</span>
          </Button>
        )}
      </div>

      <dl className="m-0 grid grid-cols-2 gap-4 min-[861px]:grid-cols-5">
        <Fact label="Canal">{filing.channel.label}</Fact>
        <Fact label="Referencia">
          {filing.external_reference ? (
            <span className="font-mono">{filing.external_reference}</span>
          ) : (
            DASH
          )}
        </Fact>
        <Fact label="Radicada">
          {formatDateTime(filing.filed_at)}
          <small className="text-text-tertiary block text-xs font-normal">
            por {filing.filed_by.name}
          </small>
        </Fact>
        <Fact label="Respuesta esperada">
          {filing.target_response_at ? formatDateTime(filing.target_response_at) : DASH}
          {overdue && (
            <small className="text-tone-danger-fg block text-xs font-medium">Vencida</small>
          )}
        </Fact>
        <Fact label="Respuestas del banco">
          <span className="tabular-nums">{filing.responses_count}</span>
        </Fact>
      </dl>

      {filing.comment && (
        <p className="text-text-secondary m-0 text-sm">
          <span className="text-text-tertiary">Comentario interno: </span>
          {filing.comment}
        </p>
      )}

      {can.snapshots && (
        <div className="border-border-default grid gap-3 border-t pt-3">
          <Button
            type="link"
            className="w-fit px-0!"
            aria-expanded={showSnapshots}
            aria-controls={`${ids}-snapshots`}
            onClick={() => setShowSnapshots((v) => !v)}
          >
            {showSnapshots ? "Ocultar documentos entregados" : "Ver documentos entregados"}
          </Button>
          {showSnapshots && (
            <div id={`${ids}-snapshots`}>
              <Snapshots applicationId={applicationId} filingId={filing.id} />
            </div>
          )}
        </div>
      )}

      {children}
    </article>
  );
}
