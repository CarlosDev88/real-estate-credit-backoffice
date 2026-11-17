"use client";

import { Alert, Button } from "antd";
import { useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { useMe } from "@/features/auth/queries";
import type { Permissions } from "@/features/applications/workspace-header";
import type { ApplicationDetail } from "@/features/applications/workspace-queries";
import { DeliveryPanel } from "@/features/filings/delivery-panel";
import { FilingCard } from "@/features/filings/filing-card";
import { EditFilingModal } from "@/features/filings/filing-modals";
import { useFilings, type Filing } from "@/features/filings/queries";

/** Estado en el que se entrega el paquete y se radica (API §20.1). */
export const READY_TO_FILE = "READY_TO_FILE";
/** Rol que ve los documentos entregados aunque no sea el asesor asignado (API §20). */
const ADMIN_ROLE = "ADMIN";

/** Pestaña "Radicación" del expediente: paquete, radicación y su historial. */
export function FilingsTab({
  detail,
  version,
  permissions,
}: {
  detail: ApplicationDetail;
  version: number;
  permissions: Permissions;
}) {
  const filings = useFilings(detail.id);
  const me = useMe();
  const [editing, setEditing] = useState<Filing | null>(null);

  const canPrepare = permissions.has("filings.prepare");
  const canCreate = permissions.has("filings.create");
  const isOwner =
    !!me.data && (me.data.roles.includes(ADMIN_ROLE) || me.data.id === detail.assigned_advisor.id);
  const delivering = detail.status === READY_TO_FILE && (canPrepare || canCreate);

  return (
    <div className="grid gap-5">
      {delivering && (
        <DeliveryPanel
          detail={detail}
          version={version}
          can={{ prepare: canPrepare, create: canCreate }}
        />
      )}

      {filings.isPending ? (
        <div
          role="status"
          aria-label="Cargando radicaciones"
          className="bg-bg-surface border-border-default h-32 animate-pulse rounded-lg border"
        />
      ) : filings.isError ? (
        <Alert
          type="error"
          showIcon
          title="No pudimos cargar las radicaciones"
          description={filings.error.message}
          action={
            <Button size="small" onClick={() => void filings.refetch()}>
              Reintentar
            </Button>
          }
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
            />
          ))}
        </section>
      )}

      <EditFilingModal
        applicationId={detail.id}
        filing={editing}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}
