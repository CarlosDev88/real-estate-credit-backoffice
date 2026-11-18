"use client";

import Link from "next/link";
import { useMemo } from "react";

import { DataTable, dataColumns } from "@/components/ui/data-table";
import { DocumentCell, OptionalText, OriginCell } from "@/features/clients/components/client-cells";
import {
  CLIENT_SORT_FIELDS,
  isClientSortField,
  type ClientSorting,
} from "@/features/clients/list-params";
import type { Client } from "@/features/clients/queries";
import { formatDate } from "@/lib/format";

const helper = dataColumns<Client>();

// El id de cada columna ordenable es el campo de `ordering` de la API (el servidor ordena).
const makeColumns = (hrefOf: (client: Client) => string) =>
  helper.columns([
    helper.accessor((row) => row.last_names, {
      id: "last_names",
      header: "Nombre",
      cell: ({ row }) => (
        <Link
          href={hrefOf(row.original)}
          className="text-text-link block max-w-[260px] truncate font-medium no-underline hover:underline"
        >
          {row.original.full_name}
        </Link>
      ),
    }),
    helper.display({
      id: "document",
      header: "Documento",
      cell: ({ row }) => <DocumentCell client={row.original} />,
    }),
    helper.display({
      id: "email",
      header: "Correo",
      cell: ({ row }) => <OptionalText value={row.original.email} />,
    }),
    helper.display({
      id: "phone",
      header: "Teléfono",
      cell: ({ row }) => <OptionalText value={row.original.phone} className="tabular-nums" />,
    }),
    helper.display({
      id: "origin",
      header: "Origen",
      cell: ({ row }) => <OriginCell client={row.original} />,
    }),
    helper.accessor((row) => row.created_at, {
      id: "created_at",
      header: "Creado",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.created_at)}</span>
      ),
    }),
  ]);

interface ClientsTableProps {
  rows: Client[];
  sorting: ClientSorting;
  onSort: (sorting: ClientSorting) => void;
  onOpen: (client: Client) => void;
  /** Enlace del nombre: el detalle del cliente (o su pestaña Oportunidades). */
  hrefOf: (client: Client) => string;
  /** Hay otra página en camino: barra de carga arriba (las filas no se atenúan). */
  busy?: boolean;
}

/** Tabla de clientes (escritorio) sobre `DataTable`. Un clic o Enter en la fila abre el detalle. */
export function ClientsTable({ rows, sorting, onSort, onOpen, hrefOf, busy }: ClientsTableProps) {
  const columns = useMemo(() => makeColumns(hrefOf), [hrefOf]);
  return (
    <DataTable
      ariaLabel="Clientes"
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      sortableFields={CLIENT_SORT_FIELDS}
      onSort={(next) => {
        if (isClientSortField(next.field)) onSort({ field: next.field, desc: next.desc });
      }}
      onOpen={onOpen}
      busy={busy}
      stickyColumn="last_names"
    />
  );
}
