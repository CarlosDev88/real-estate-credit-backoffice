"use client";

import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { applicationHref } from "@/features/applications/applications-table";
import { bankText, StatusCell } from "@/features/applications/list-cells";
import { useClientApplications, type ClientApplication } from "@/features/clients/detail-queries";

function ApplicationRow({ application }: { application: ClientApplication }) {
  const bank = bankText(application);
  const detail = [application.purpose?.label, bank].filter(Boolean).join(" · ");
  return (
    <li className="border-border-default grid gap-1 border-b px-4 py-3 last:border-b-0 min-[861px]:grid-cols-[130px_minmax(0,1.2fr)_minmax(0,1.6fr)_150px_110px] min-[861px]:items-center min-[861px]:gap-3">
      <Link
        href={applicationHref(application.id)}
        className="text-text-link w-fit font-mono text-sm font-medium no-underline hover:underline"
      >
        {application.code}
      </Link>
      <span>
        <StatusCell application={application} />
      </span>
      <span className="text-text-secondary min-w-0 truncate text-sm" title={detail || undefined}>
        {detail || <span className="text-text-tertiary">—</span>}
      </span>
      <span className="font-medium min-[861px]:text-right">
        <Money value={application.requested_amount_cop} />
      </span>
      <RelativeTime
        value={application.updated_at}
        className="text-text-tertiary text-sm min-[861px]:text-right"
      />
    </li>
  );
}

/** Pestaña Solicitudes: las del cliente que el usuario puede ver, con enlace al expediente. */
export function ApplicationsTab({ clientId }: { clientId: string }) {
  const query = useClientApplications(clientId, true);
  const items = query.data?.items ?? [];

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando solicitudes" blocks={[40]} className="m-4" />;
  } else if (query.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las solicitudes"
          message={query.error.message}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState
        title="Este cliente no tiene solicitudes"
        description="Se crean desde una de sus oportunidades."
      />
    );
  } else {
    body = (
      <ul aria-label="Solicitudes del cliente" className="m-0 list-none p-0">
        {items.map((application) => (
          <ApplicationRow key={application.id} application={application} />
        ))}
      </ul>
    );
  }

  return (
    <section
      aria-labelledby="client-applications"
      className="bg-bg-surface border-border-default max-w-[1100px] overflow-hidden rounded-lg border"
    >
      <div className="border-border-default border-b px-4 py-3">
        <h2 id="client-applications" className="m-0 text-base font-semibold">
          Solicitudes
        </h2>
      </div>
      {items.length > 0 && (
        <div
          aria-hidden="true"
          className="bg-bg-subtle text-text-secondary border-border-default hidden grid-cols-[130px_minmax(0,1.2fr)_minmax(0,1.6fr)_150px_110px] gap-3 border-b px-4 py-2 text-xs font-medium min-[861px]:grid"
        >
          <span>Código</span>
          <span>Estado</span>
          <span>Finalidad y banco</span>
          <span className="text-right">Monto</span>
          <span className="text-right">Actualizada</span>
        </div>
      )}
      {body}
    </section>
  );
}
