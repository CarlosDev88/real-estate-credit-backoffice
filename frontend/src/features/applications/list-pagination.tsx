"use client";

import { Pagination, Select } from "antd";

import { PAGE_SIZES } from "@/features/applications/list-params";

const SIZE_OPTIONS = PAGE_SIZES.map((n) => ({ value: n, label: String(n) }));

/** "Mostrando 1–20 de 48", tamaño de página y páginas (mockup `solicitudes.html`). */
export function rangeText(page: number, pageSize: number, total: number): string {
  if (total === 0) return "Sin resultados";
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `Mostrando ${from}–${to} de ${total}`;
}

export function ListPagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  compact,
}: {
  page: number;
  pageSize: number;
  total: number;
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
          aria-label="Solicitudes por página"
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
