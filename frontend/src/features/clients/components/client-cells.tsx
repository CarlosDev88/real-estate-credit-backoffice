"use client";

import type { Client } from "@/features/clients/queries";

// Celdas del listado de clientes, compartidas por la tabla (escritorio) y las tarjetas (móvil).

export const EMPTY = "—";

/** Documento con su tipo: "CC 1032445908". El nombre del tipo (catálogo) va en el `title`. */
export function DocumentCell({
  client,
}: {
  client: Pick<Client, "document_type" | "document_number">;
}) {
  return (
    <span className="whitespace-nowrap">
      <abbr
        title={client.document_type.label}
        className="text-text-tertiary mr-1 text-xs font-medium no-underline"
      >
        {client.document_type.code}
      </abbr>
      <span className="font-mono text-sm tabular-nums">{client.document_number}</span>
    </span>
  );
}

/** Origen del cliente (catálogo `lead_origin`), o "—". */
export function OriginCell({ client }: { client: Pick<Client, "origin"> }) {
  if (!client.origin) return <span className="text-text-tertiary">{EMPTY}</span>;
  return <span>{client.origin.label}</span>;
}

/** Texto con "—" si viene vacío (correo y teléfono son opcionales). */
export function OptionalText({ value, className = "" }: { value: string; className?: string }) {
  if (!value) return <span className="text-text-tertiary">{EMPTY}</span>;
  return (
    <span className={`block max-w-[240px] truncate ${className}`} title={value}>
      {value}
    </span>
  );
}
