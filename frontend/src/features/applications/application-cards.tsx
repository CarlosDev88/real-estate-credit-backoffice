"use client";

import Link from "next/link";
import type { MouseEvent } from "react";

import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { applicationHref } from "@/features/applications/applications-table";
import { CompletenessCell, participantsText, StatusCell } from "@/features/applications/list-cells";
import type { Application } from "@/features/applications/queries";

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
  const onClick = (event: MouseEvent, application: Application) => {
    if (event.target instanceof Element && event.target.closest("a, button")) return;
    onOpen(application);
  };

  return (
    <ul
      aria-label="Solicitudes"
      aria-busy={busy || undefined}
      className={`m-0 list-none p-0 transition-opacity ${busy ? "opacity-60" : ""}`}
    >
      {rows.map((application) => {
        const extra = participantsText(application.participants_summary);
        return (
          <li
            key={application.id}
            onClick={(event) => onClick(event, application)}
            className="border-border-default hover:bg-brand-subtle grid cursor-pointer gap-1.5 border-b px-4 py-3 last:border-b-0"
          >
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
              {extra && (
                <span className="text-text-tertiary ml-1 text-xs font-normal">{extra}</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="font-medium">
                <Money value={application.requested_amount_cop} />
              </span>
              <CompletenessCell application={application} fill />
              <RelativeTime value={application.updated_at} className="text-text-tertiary text-sm" />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
