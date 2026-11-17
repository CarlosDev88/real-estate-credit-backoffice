"use client";

import {
  createColumnHelper,
  flexRender,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type SortingState,
  type Updater,
} from "@tanstack/react-table";
import Link from "next/link";
import { useMemo } from "react";
import type { KeyboardEvent, MouseEvent } from "react";

import { DocumentCell, OptionalText, OriginCell } from "@/features/clients/components/client-cells";
import { isClientSortField, type ClientSorting } from "@/features/clients/list-params";
import { clientHref, type Client } from "@/features/clients/queries";
import { formatDate } from "@/lib/format";

const features = tableFeatures({ rowSortingFeature });
const helper = createColumnHelper<typeof features, Client>();

// El id de cada columna ordenable es el campo de `ordering` de la API (el servidor ordena).
const columns = helper.columns([
  helper.accessor((row) => row.last_names, {
    id: "last_names",
    header: "Nombre",
    cell: ({ row }) => (
      <Link
        href={clientHref(row.original.id)}
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

const STICKY = "last_names";

function fromControl(target: EventTarget): boolean {
  return target instanceof Element && target.closest("a, button") !== null;
}

interface ClientsTableProps {
  rows: Client[];
  sorting: ClientSorting;
  onSort: (sorting: ClientSorting) => void;
  onOpen: (client: Client) => void;
  /** Hay otra página en camino: las filas actuales se atenúan. */
  busy?: boolean;
}

/** Tabla de clientes (escritorio). Un clic o Enter en la fila abre el detalle. */
export function ClientsTable({ rows, sorting, onSort, onOpen, busy }: ClientsTableProps) {
  const sortingState = useMemo<SortingState>(
    () => [{ id: sorting.field, desc: sorting.desc }],
    [sorting.field, sorting.desc],
  );

  const table = useTable({
    features,
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { sorting: sortingState },
    onSortingChange: (updater: Updater<SortingState>) => {
      const next = typeof updater === "function" ? updater(sortingState) : updater;
      const first = next[0];
      if (first && isClientSortField(first.id)) onSort({ field: first.id, desc: first.desc });
    },
    // El servidor ordena; la tabla solo lleva el estado. Desc primero, sin quitar el orden.
    manualSorting: true,
    enableMultiSort: false,
    enableSortingRemoval: false,
    sortDescFirst: true,
  });

  const onRowClick = (event: MouseEvent, client: Client) => {
    if (!fromControl(event.target)) onOpen(client);
  };
  const onRowKeyDown = (event: KeyboardEvent, client: Client) => {
    if (event.key === "Enter" && event.target === event.currentTarget) {
      event.preventDefault();
      onOpen(client);
    }
  };

  return (
    <div className="overflow-x-auto">
      <table
        className={`w-full min-w-[920px] border-collapse transition-opacity ${busy ? "opacity-60" : ""}`}
        aria-busy={busy || undefined}
      >
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const column = header.column;
                const canSort = column.getCanSort();
                const sorted = column.getIsSorted();
                const sticky = column.id === STICKY;
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      canSort
                        ? sorted === "asc"
                          ? "ascending"
                          : sorted === "desc"
                            ? "descending"
                            : "none"
                        : undefined
                    }
                    className={`bg-bg-subtle text-text-secondary border-border-default h-10 border-b px-2 text-left text-xs font-medium whitespace-nowrap ${
                      sticky
                        ? "sticky left-0 z-[3] shadow-[inset_-1px_0_0_var(--um-border-default)]"
                        : ""
                    }`}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        onClick={column.getToggleSortingHandler()}
                        className="group hover:text-text-primary focus-visible:outline-focus-ring inline-flex cursor-pointer items-center gap-1 rounded-sm border-0 bg-transparent p-0 align-middle text-xs font-medium text-inherit focus-visible:outline-2 focus-visible:outline-offset-2"
                      >
                        {flexRender(column.columnDef.header, header.getContext())}
                        <span aria-hidden="true" className="inline-block w-2.5">
                          {sorted === "asc" ? (
                            <span className="text-text-link">↑</span>
                          ) : sorted === "desc" ? (
                            <span className="text-text-link">↓</span>
                          ) : (
                            <span className="text-text-tertiary hidden group-hover:inline group-focus-visible:inline">
                              ↕
                            </span>
                          )}
                        </span>
                      </button>
                    ) : (
                      flexRender(column.columnDef.header, header.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              tabIndex={0}
              onClick={(event) => onRowClick(event, row.original)}
              onKeyDown={(event) => onRowKeyDown(event, row.original)}
              className="group/row hover:bg-brand-subtle focus-visible:outline-focus-ring cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2"
            >
              {row.getAllCells().map((cell) => (
                <td
                  key={cell.id}
                  className={`border-border-default h-11 border-b px-2 text-left whitespace-nowrap group-last/row:border-b-0 ${
                    cell.column.id === STICKY
                      ? "bg-bg-surface group-hover/row:bg-brand-subtle sticky left-0 z-[1] shadow-[inset_-1px_0_0_var(--um-border-default)]"
                      : ""
                  }`}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
