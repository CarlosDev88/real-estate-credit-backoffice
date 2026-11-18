"use client";

import Link from "next/link";

import { DataTable, dataColumns } from "@/components/ui/data-table";
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

const helper = dataColumns<Application>();

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

const RIGHT = ["requested_amount"];

interface ApplicationsTableProps {
  rows: Application[];
  sorting: Sorting;
  onSort: (sorting: Sorting) => void;
  onOpen: (application: Application) => void;
  /** Hay otra página en camino: barra de carga arriba (las filas no se atenúan). */
  busy?: boolean;
}

/** Tabla de `/solicitudes` (mockup `solicitudes.html`) sobre `DataTable`. */
export function ApplicationsTable({ rows, sorting, onSort, onOpen, busy }: ApplicationsTableProps) {
  return (
    <DataTable
      ariaLabel="Solicitudes"
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      sortableFields={SORTABLE_FIELDS}
      // Solo llegan los `id` de `sortableFields`, que son `SortField`.
      onSort={(next) => onSort({ field: next.field as SortField, desc: next.desc })}
      onOpen={onOpen}
      busy={busy}
      stickyColumn="code"
      alignRight={RIGHT}
    />
  );
}
