"use client";

import Link from "next/link";
import type { MouseEvent } from "react";

import { DocumentCell } from "@/features/clients/components/client-cells";
import { clientHref, type Client } from "@/features/clients/queries";
import { formatDate } from "@/lib/format";

/** Listado en móvil (≤ 860 px): una tarjeta por cliente. */
export function ClientCards({
  rows,
  onOpen,
  busy,
}: {
  rows: Client[];
  onOpen: (client: Client) => void;
  busy?: boolean;
}) {
  const onClick = (event: MouseEvent, client: Client) => {
    if (event.target instanceof Element && event.target.closest("a, button")) return;
    onOpen(client);
  };

  return (
    <ul
      aria-label="Clientes"
      aria-busy={busy || undefined}
      className={`m-0 list-none p-0 transition-opacity ${busy ? "opacity-60" : ""}`}
    >
      {rows.map((client) => {
        const contact = [client.email, client.phone].filter(Boolean).join(" · ");
        return (
          <li
            key={client.id}
            onClick={(event) => onClick(event, client)}
            className="border-border-default hover:bg-brand-subtle grid cursor-pointer gap-1 border-b px-4 py-3 last:border-b-0"
          >
            <div className="flex items-center gap-2">
              <Link
                href={clientHref(client.id)}
                className="text-text-link min-w-0 truncate font-medium no-underline"
              >
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
          </li>
        );
      })}
    </ul>
  );
}
