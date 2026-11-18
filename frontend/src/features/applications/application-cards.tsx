"use client";

import Link from "next/link";

import { CardList } from "@/components/ui/data-table";
import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { applicationHref } from "@/features/applications/applications-table";
import { CompletenessCell, participantsText, StatusCell } from "@/features/applications/list-cells";
import type { Application } from "@/features/applications/queries";

function ApplicationCard({ application }: { application: Application }) {
  const extra = participantsText(application.participants_summary);
  return (
    <>
      <div className="flex items-center gap-2">
        <Link
          href={applicationHref(application.id)}
          className="text-text-link font-mono text-sm font-medium no-underline"
        >
          {application.code}
        </Link>
        <span className="ml-auto">
          <StatusCell application={application} />
        </span>
      </div>
      <div className="font-medium">
        {application.applicant.full_name}
        {extra && <span className="text-text-tertiary ml-1 text-xs font-normal">{extra}</span>}
      </div>
      <div className="flex items-center gap-3">
        <span className="font-medium">
          <Money value={application.requested_amount_cop} />
        </span>
        <CompletenessCell application={application} fill />
        <RelativeTime value={application.updated_at} className="text-text-tertiary text-sm" />
      </div>
    </>
  );
}

/** Listado en móvil (≤ 860 px): una tarjeta por solicitud (mockup `solicitudes.html`). */
export function ApplicationCards({
  rows,
  onOpen,
  busy,
}: {
  rows: Application[];
  onOpen: (application: Application) => void;
  busy?: boolean;
}) {
  return (
    <CardList
      ariaLabel="Solicitudes"
      rows={rows}
      getRowId={(application) => application.id}
      onOpen={onOpen}
      busy={busy}
      renderCard={(application) => <ApplicationCard application={application} />}
    />
  );
}
