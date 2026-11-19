"use client";

import Link from "next/link";

import { CardList } from "@/components/ui/data-table";
import { DocumentCell } from "@/features/clients/components/client-cells";
import type { Client } from "@/features/clients/queries";
import { formatDate } from "@/lib/format";

function ClientCard({ client, href }: { client: Client; href: string }) {
  const contact = [client.email, client.phone].filter(Boolean).join(" · ");
  return (
    <>
      <div className="flex items-center gap-2">
        <Link href={href} className="text-text-link min-w-0 truncate font-medium no-underline">
          {client.full_name}
        </Link>
        <span className="text-text-tertiary ml-auto text-sm whitespace-nowrap">
          {formatDate(client.created_at)}
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <DocumentCell client={client} />
        {client.origin && (
          <span className="text-text-secondary ml-auto">{client.origin.label}</span>
        )}
      </div>
      {contact && (
        <div className="text-text-secondary truncate text-sm" title={contact}>
          {contact}
        </div>
      )}
      {client.applications_count !== undefined && client.applications_count > 0 && (
        <div className="text-text-secondary text-sm">
          {client.applications_count === 1
            ? "1 solicitud"
            : `${client.applications_count} solicitudes`}
        </div>
      )}
    </>
  );
}

/** Listado en móvil (≤ 860 px): una tarjeta por cliente. */
export function ClientCards({
  rows,
  onOpen,
  hrefOf,
  busy,
}: {
  rows: Client[];
  onOpen: (client: Client) => void;
  hrefOf: (client: Client) => string;
  busy?: boolean;
}) {
  return (
    <CardList
      ariaLabel="Clientes"
      rows={rows}
      getRowId={(client) => client.id}
      onOpen={onOpen}
      busy={busy}
      renderCard={(client) => <ClientCard client={client} href={hrefOf(client)} />}
    />
  );
}
