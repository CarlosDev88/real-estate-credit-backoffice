"use client";

import { Pagination, Select } from "antd";

/** Tamaños de página por defecto de los listados. */
export const DEFAULT_PAGE_SIZES = [10, 20, 50] as const;

/** "Mostrando 1–20 de 48" (mockup `solicitudes.html`); sin resultados, "Sin resultados". */
export function rangeText(page: number, pageSize: number, total: number): string {
  if (total === 0) return "Sin resultados";
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `Mostrando ${from}–${to} de ${total}`;
}

interface ListPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  /** Lo que se lista, en plural y con mayúscula: "Clientes" se lee "Clientes por página". */
  itemsLabel: string;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  /** Móvil: paginación simple ("3 / 8"). */
  compact?: boolean;
  pageSizes?: readonly number[];
}

/**
 * Pie de un listado: rango, tamaño de página y páginas. El rango se anuncia al cambiar
 * (`aria-live`). Con una sola página no se muestran los números.
 */
export function ListPagination({
  page,
  pageSize,
  total,
  itemsLabel,
  onPage,
  onPageSize,
  compact = false,
  pageSizes = DEFAULT_PAGE_SIZES,
}: ListPaginationProps) {
  return (
    <div className="border-border-default text-text-secondary flex flex-wrap items-center gap-3 border-t px-3 py-2 text-sm">
      <span aria-live="polite">{rangeText(page, pageSize, total)}</span>
      <div className="flex-1" />
      <label className="text-text-tertiary flex items-center gap-2">
        Por página
        <Select
          size="small"
          value={pageSize}
          onChange={onPageSize}
          options={pageSizes.map((n) => ({ value: n, label: String(n) }))}
          aria-label={`${itemsLabel} por página`}
          popupMatchSelectWidth={false}
        />
      </label>
      {total > pageSize && (
        <Pagination
          size="small"
          current={page}
          pageSize={pageSize}
          total={total}
          onChange={onPage}
          showSizeChanger={false}
          simple={compact}
          showLessItems={compact}
        />
      )}
    </div>
  );
}
