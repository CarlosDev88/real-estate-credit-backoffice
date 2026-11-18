"use client";

import {
  createColumnHelper,
  flexRender,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
  type SortingState,
  type Updater,
} from "@tanstack/react-table";
import { useMemo } from "react";
import type { KeyboardEvent, MouseEvent, ReactNode } from "react";

// Tabla de listado (mockup `solicitudes.html`) y su versión en tarjetas para móvil.
// El servidor ordena y pagina: la tabla solo lleva el estado del orden.

export const dataTableFeatures = tableFeatures({ rowSortingFeature });
export type DataColumn<T extends RowData> = ColumnDef<typeof dataTableFeatures, T, any>; // eslint-disable-line @typescript-eslint/no-explicit-any -- cada columna tiene su propio tipo de valor

/** Columnas tipadas: `const col = dataColumns<Cliente>(); col.columns([col.accessor(...)])`. */
export function dataColumns<T extends RowData>() {
  return createColumnHelper<typeof dataTableFeatures, T>();
}

/** Orden actual: el `id` de la columna es el campo de `ordering` de la API. */
export interface TableSort {
  field: string;
  desc: boolean;
}

/** Un clic o Enter en la fila abre el detalle; los enlaces y botones siguen siendo suyos. */
function fromControl(target: EventTarget): boolean {
  return target instanceof Element && target.closest("a, button, input, label") !== null;
}

/**
 * Otra página en camino: una barra arriba de la lista. No se atenúan las filas, porque la
 * opacidad baja el contraste del texto por debajo de 4,5:1 (WCAG 1.4.3).
 */
function BusyBar() {
  return (
    <div
      aria-hidden="true"
      className="bg-brand-primary absolute inset-x-0 top-0 z-[4] h-0.5 animate-pulse motion-reduce:animate-none"
    />
  );
}

function SortArrow({ sorted }: { sorted: false | "asc" | "desc" }) {
  return (
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
  );
}

interface DataTableProps<T extends RowData> {
  columns: DataColumn<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  /** Nombre de la tabla para el lector de pantalla ("Solicitudes"). */
  ariaLabel: string;
  sorting?: TableSort;
  /** Solo las columnas con `id` en esta lista se pueden ordenar (los campos de la API). */
  sortableFields?: readonly string[];
  onSort?: (sorting: TableSort) => void;
  /** Clic o Enter en la fila. Sin él, las filas no son interactivas. */
  onOpen?: (row: T) => void;
  /** Hay otra página en camino: las filas actuales se atenúan. */
  busy?: boolean;
  /** Columna que queda fija a la izquierda al desplazar (el código). */
  stickyColumn?: string;
  /** Columnas alineadas a la derecha (montos). */
  alignRight?: readonly string[];
  /** Ancho mínimo antes de desplazar en horizontal. */
  minWidth?: number;
}

/**
 * Tabla ordenable: el orden se activa con un botón dentro del encabezado (funciona con
 * teclado) y la flecha solo se ve en la columna ordenada. Encabezados en minúscula inicial,
 * 12 px; filas de 52 px y hover en `brand.subtle` (design/README.md, "Tabla").
 */
export function DataTable<T extends RowData>({
  columns,
  rows,
  getRowId,
  ariaLabel,
  sorting,
  sortableFields = [],
  onSort,
  onOpen,
  busy = false,
  stickyColumn,
  alignRight = [],
  minWidth = 920,
}: DataTableProps<T>) {
  const sortingState = useMemo<SortingState>(
    () => (sorting ? [{ id: sorting.field, desc: sorting.desc }] : []),
    [sorting],
  );

  const sortable = useMemo(() => new Set(sortableFields), [sortableFields]);
  const right = useMemo(() => new Set(alignRight), [alignRight]);

  const table = useTable({
    features: dataTableFeatures,
    columns,
    data: rows,
    getRowId,
    state: { sorting: sortingState },
    onSortingChange: (updater: Updater<SortingState>) => {
      const next = typeof updater === "function" ? updater(sortingState) : updater;
      const first = next[0];
      if (first && sortable.has(first.id)) onSort?.({ field: first.id, desc: first.desc });
    },
    manualSorting: true,
    enableMultiSort: false,
    enableSortingRemoval: false,
    sortDescFirst: true,
  });

  const onRowClick = (event: MouseEvent, row: T) => {
    if (onOpen && !fromControl(event.target)) onOpen(row);
  };
  const onRowKeyDown = (event: KeyboardEvent, row: T) => {
    if (onOpen && event.key === "Enter" && event.target === event.currentTarget) {
      event.preventDefault();
      onOpen(row);
    }
  };

  const stickyCell = "sticky left-0 shadow-[inset_-1px_0_0_var(--um-border-default)]";

  return (
    <div className="relative overflow-x-auto">
      {busy && <BusyBar />}
      <table
        aria-label={ariaLabel}
        aria-busy={busy || undefined}
        className="w-full border-collapse"
        style={{ minWidth }}
      >
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const column = header.column;
                // TanStack solo ordena columnas con `accessor`; el valor no se usa (ordena la API).
                const canSort = sortable.has(column.id) && !!onSort && column.getCanSort();
                const sorted = column.getIsSorted();
                const isRight = right.has(column.id);
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
                      isRight ? "text-right" : "text-left"
                    } ${column.id === stickyColumn ? `${stickyCell} z-[3]` : ""}`}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        onClick={column.getToggleSortingHandler()}
                        className={`group hover:text-text-primary focus-visible:outline-focus-ring inline-flex cursor-pointer items-center gap-1 rounded-sm border-0 bg-transparent p-0 align-middle text-xs font-medium text-inherit focus-visible:outline-2 focus-visible:outline-offset-2 ${
                          isRight ? "flex-row-reverse" : ""
                        }`}
                      >
                        {flexRender(column.columnDef.header, header.getContext())}
                        <SortArrow sorted={sorted} />
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
              tabIndex={onOpen ? 0 : undefined}
              onClick={(event) => onRowClick(event, row.original)}
              onKeyDown={(event) => onRowKeyDown(event, row.original)}
              className={`group/row hover:bg-brand-subtle ${
                onOpen
                  ? "focus-visible:outline-focus-ring cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2"
                  : ""
              }`}
            >
              {row.getAllCells().map((cell) => {
                const id = cell.column.id;
                return (
                  <td
                    key={cell.id}
                    className={`border-border-default h-[52px] border-b px-2 whitespace-nowrap group-last/row:border-b-0 ${
                      right.has(id) ? "text-right" : "text-left"
                    } ${
                      id === stickyColumn
                        ? `bg-bg-surface group-hover/row:bg-brand-subtle z-[1] ${stickyCell}`
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

interface CardListProps<T> {
  rows: T[];
  getRowId: (row: T) => string;
  /** Nombre de la lista ("Solicitudes"). */
  ariaLabel: string;
  /** Contenido de cada tarjeta. El enlace principal va adentro, para el teclado. */
  renderCard: (row: T) => ReactNode;
  onOpen?: (row: T) => void;
  busy?: boolean;
}

/** Listado en móvil (≤ 860 px): una tarjeta por fila. Toda la tarjeta abre el detalle. */
export function CardList<T>({
  rows,
  getRowId,
  ariaLabel,
  renderCard,
  onOpen,
  busy = false,
}: CardListProps<T>) {
  return (
    <div className="relative">
      {busy && <BusyBar />}
      <ul aria-label={ariaLabel} aria-busy={busy || undefined} className="m-0 list-none p-0">
        {rows.map((row) => (
          <li
            key={getRowId(row)}
            onClick={(event) => {
              if (onOpen && !fromControl(event.target)) onOpen(row);
            }}
            className={`border-border-default grid gap-1 border-b px-4 py-3 last:border-b-0 ${
              onOpen ? "hover:bg-brand-subtle cursor-pointer" : ""
            }`}
          >
            {renderCard(row)}
          </li>
        ))}
      </ul>
    </div>
  );
}
