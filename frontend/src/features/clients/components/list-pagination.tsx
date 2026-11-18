"use client";

import { Pagination, Select } from "antd";

import { PAGE_SIZES } from "@/features/applications/list-params";
import { rangeText } from "@/features/applications/list-pagination";

const SIZE_OPTIONS = PAGE_SIZES.map((n) => ({ value: n, label: String(n) }));

/**
 * Pie del listado: "Mostrando 1–20 de 48", tamaño de página y páginas. Igual al de
 * `/solicitudes`, con el nombre de lo que se lista en la etiqueta del tamaño.
 * Candidato a la librería (`ListPagination` con `itemsLabel`).
 */
export function ListPagination({
  page,
  pageSize,
  total,
  itemsLabel,
  onPage,
  onPageSize,
  compact,
}: {
  page: number;
  pageSize: number;
  total: number;
  /** "Clientes": se lee "Clientes por página". */
  itemsLabel: string;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  compact: boolean;
}) {
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
          options={SIZE_OPTIONS}
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
