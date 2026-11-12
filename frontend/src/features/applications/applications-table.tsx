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

import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import {
  ApplicantCell,
  BankCell,
  CompletenessCell,
  ProductTypeCell,
  StatusCell,
} from "@/features/applications/list-cells";
import type { SortField, Sorting } from "@/features/applications/list-params";
import { SORTABLE_FIELDS } from "@/features/applications/list-params";
import type { Application } from "@/features/applications/queries";

const features = tableFeatures({ rowSortingFeature });
const helper = createColumnHelper<typeof features, Application>();

export const applicationHref = (id: string) => `/solicitudes/${id}`;

// El id de cada columna ordenable es el campo de `ordering` de la API. TanStack solo ordena
// columnas con `accessor`; el valor no se usa para ordenar (lo hace el servidor).
const columns = helper.columns([
  helper.accessor((row) => row.code, {
    id: "code",
    header: "Código",
    cell: ({ row }) => (
      <Link
        href={applicationHref(row.original.id)}
        className="text-text-link font-mono text-sm font-medium whitespace-nowrap no-underline hover:underline"
      >
        {row.original.code}
      </Link>
    ),
  }),
  helper.accessor((row) => row.applicant.full_name, {
    id: "applicant_name",
    header: "Titular",
    cell: ({ row }) => <ApplicantCell application={row.original} />,
  }),
  helper.display({
    id: "status",
    header: "Estado",
    enableSorting: false,
    cell: ({ row }) => <StatusCell application={row.original} />,
  }),
  helper.accessor((row) => row.requested_amount_cop, {
    id: "requested_amount",
    header: "Monto",
    cell: ({ row }) => <Money value={row.original.requested_amount_cop} />,
  }),
  helper.display({
    id: "completeness",
    header: "Expediente",
    enableSorting: false,
    cell: ({ row }) => <CompletenessCell application={row.original} />,
  }),
  helper.accessor((row) => row.bank_product?.bank.name ?? null, {
    id: "bank_name",
    header: "Banco",
    cell: ({ row }) => <BankCell application={row.original} />,
  }),
  helper.display({
    id: "product_type",
    header: "Tipo de crédito",
    enableSorting: false,
    cell: ({ row }) => <ProductTypeCell application={row.original} />,
  }),
  helper.accessor((row) => row.updated_at, {
    id: "updated_at",
    header: "Actualizada",
    cell: ({ row }) => (
      <RelativeTime value={row.original.updated_at} className="text-text-secondary text-sm" />
    ),
  }),
]);

const RIGHT = new Set(["requested_amount"]);
const STICKY = "code";

function isSortField(id: string): id is SortField {
  return (SORTABLE_FIELDS as readonly string[]).includes(id);
}

/** Un clic o Enter en la fila abre el expediente; los enlaces y botones siguen siendo suyos. */
function fromControl(target: EventTarget): boolean {
  return target instanceof Element && target.closest("a, button") !== null;
}

interface ApplicationsTableProps {
  rows: Application[];
  sorting: Sorting;
  onSort: (sorting: Sorting) => void;
  onOpen: (application: Application) => void;
  /** Hay otra página en camino: las filas actuales se atenúan. */
  busy?: boolean;
}

export function ApplicationsTable({ rows, sorting, onSort, onOpen, busy }: ApplicationsTableProps) {
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
      if (first && isSortField(first.id)) onSort({ field: first.id, desc: first.desc });
    },
    // El servidor ordena; la tabla solo lleva el estado. Desc primero, sin quitar el orden.
    manualSorting: true,
    enableMultiSort: false,
    enableSortingRemoval: false,
    sortDescFirst: true,
  });

  const onRowClick = (event: MouseEvent, application: Application) => {
    if (!fromControl(event.target)) onOpen(application);
  };
  const onRowKeyDown = (event: KeyboardEvent, application: Application) => {
    if (event.key === "Enter" && event.target === event.currentTarget) {
      event.preventDefault();
      onOpen(application);
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
                const right = RIGHT.has(column.id);
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
                    className={`bg-bg-subtle text-text-secondary border-border-default h-10 border-b px-2 text-xs font-medium whitespace-nowrap ${
                      right ? "text-right" : "text-left"
                    } ${sticky ? "sticky left-0 z-[3] shadow-[inset_-1px_0_0_var(--um-border-default)]" : ""}`}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        onClick={column.getToggleSortingHandler()}
                        className={`group hover:text-text-primary focus-visible:outline-focus-ring inline-flex cursor-pointer items-center gap-1 rounded-sm border-0 bg-transparent p-0 align-middle text-xs font-medium text-inherit focus-visible:outline-2 focus-visible:outline-offset-2 ${
                          right ? "flex-row-reverse" : ""
                        }`}
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
              {row.getAllCells().map((cell) => {
                const id = cell.column.id;
                return (
                  <td
                    key={cell.id}
                    className={`border-border-default h-[52px] border-b px-2 whitespace-nowrap group-last/row:border-b-0 ${
                      RIGHT.has(id) ? "text-right" : "text-left"
                    } ${
                      id === STICKY
                        ? "bg-bg-surface group-hover/row:bg-brand-subtle sticky left-0 z-[1] shadow-[inset_-1px_0_0_var(--um-border-default)]"
                        : ""
                    }`}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
