"use client";

import { ExpiryNotice } from "@/features/buyer-portal/expiry";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { PortalPage } from "@/features/buyer-portal/portal-shell";

/** Primer nombre para el saludo ("Hola, Sofía"). */
export function firstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0] ?? displayName;
}

/** Inicio del portal (`/portal`, mockup `portal.html`). */
export function PortalHome() {
  const { session } = usePortal();
  const { application } = session;
  return (
    <PortalPage>
      <div>
        <h1 className="m-0 text-3xl font-semibold tracking-tight">
          Hola, {firstName(session.buyer.display_name)}
        </h1>
        <p className="text-text-secondary text-md mt-1 mb-0">
          <span className="text-text-tertiary font-mono whitespace-nowrap">{application.code}</span>
        </p>
      </div>
      <section
        aria-labelledby="status-title"
        className="bg-bg-sidebar text-text-on-sidebar rounded-xl px-4 py-5"
      >
        <h2 id="status-title" className="text-text-on-sidebar-strong m-0 text-xl font-semibold">
          {application.public_status_label}
        </h2>
        <ExpiryNotice className="border-sidebar-divider mt-4 border-t pt-3" />
      </section>
    </PortalPage>
  );
}
