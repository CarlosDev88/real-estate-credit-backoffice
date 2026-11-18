"use client";

import { Button, Input, Select } from "antd";
import { useEffect, useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips } from "@/components/ui/filter-chips";
import { FilterIcon, SearchIcon } from "@/components/ui/icons";
import { SEARCH_DEBOUNCE_MS } from "@/features/admin-common/list-params";

export interface FilterOption {
  value: string;
  label: string;
}

export interface SelectFilter {
  key: string;
  /** Nombre del filtro ("Rol"): se ve en el control ("Rol: Asesor") y en el chip. */
  label: string;
  value: string;
  options: FilterOption[];
  loading?: boolean;
}

export interface SearchFilter {
  value: string;
  placeholder: string;
  /** Nombre accesible del campo ("Buscar usuarios por nombre o correo"). */
  ariaLabel: string;
}

const ALL_LABEL = "todos";

/** Texto del valor elegido; mientras llegan las opciones (o si ya no está), "…". */
export function optionLabel(options: FilterOption[], value: string): string {
  if (value === "") return ALL_LABEL;
  return options.find((o) => o.value === value)?.label ?? "…";
}

function SearchInput({
  search,
  onChange,
}: {
  search: SearchFilter;
  onChange: (value: string) => void;
}) {
  const { value } = search;
  const [text, setText] = useState(value);
  // Si la URL cambia desde afuera ("Limpiar", atrás/adelante), el campo la sigue.
  const [synced, setSynced] = useState(value);
  if (value !== synced) {
    setSynced(value);
    if (value !== text.trim()) setText(value);
  }

  useEffect(() => {
    const term = text.trim();
    if (term === value) return;
    const id = setTimeout(() => onChange(term), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text, value, onChange]);

  return (
    <Input
      type="search"
      allowClear
      value={text}
      onChange={(event) => setText(event.target.value)}
      placeholder={search.placeholder}
      aria-label={search.ariaLabel}
      prefix={<SearchIcon className="text-text-tertiary" />}
      className="min-w-0 flex-[1_1_200px]"
    />
  );
}

interface AdminListFiltersProps {
  search?: SearchFilter;
  onSearch?: (value: string) => void;
  selects: SelectFilter[];
  onSelect: (key: string, value: string) => void;
  onClear: () => void;
  /** ≤ 860 px: los filtros van en una hoja inferior y los activos se ven como chips. */
  mobile: boolean;
}

/**
 * Barra de un listado de administración: búsqueda y filtros de selección. Mismo
 * comportamiento que la de `/clientes` (design/README.md, "Lista con filtros").
 */
export function AdminListFilters({
  search,
  onSearch,
  selects,
  onSelect,
  onClear,
  mobile,
}: AdminListFiltersProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const activeSelects = selects.filter((s) => s.value !== "");
  const anyActive = activeSelects.length > 0 || (search?.value ?? "") !== "";

  const control = (filter: SelectFilter, block: boolean) => (
    <Select
      key={filter.key}
      aria-label={`Filtrar por ${filter.label.toLowerCase()}`}
      value={filter.value}
      onChange={(value: string) => onSelect(filter.key, value)}
      options={[{ value: "", label: ALL_LABEL }, ...filter.options]}
      loading={filter.loading}
      virtual={false}
      popupMatchSelectWidth={false}
      size={block ? "large" : "middle"}
      // En el control se ve "Rol: Asesor"; en la lista, solo el valor.
      labelRender={() => `${filter.label}: ${optionLabel(filter.options, filter.value)}`}
      style={block ? { width: "100%" } : { minWidth: 180 }}
    />
  );

  return (
    <>
      <div
        className={`border-border-default flex items-center gap-2 border-b p-3 ${mobile ? "flex-nowrap" : "flex-wrap"}`}
      >
        {search && onSearch && <SearchInput search={search} onChange={onSearch} />}
        {mobile ? (
          <Button
            aria-expanded={sheetOpen}
            onClick={() => setSheetOpen(true)}
            icon={<FilterIcon />}
            className={search ? "" : "ml-auto"}
          >
            {activeSelects.length ? `Filtros (${activeSelects.length})` : "Filtros"}
          </Button>
        ) : (
          <div role="group" aria-label="Filtros" className="contents">
            {selects.map((filter) => control(filter, false))}
            {anyActive && (
              <Button type="text" onClick={onClear}>
                Limpiar
              </Button>
            )}
          </div>
        )}
      </div>

      {mobile && (
        <>
          <FilterChips
            chips={activeSelects.map((filter) => ({
              key: filter.key,
              label: filter.label,
              value: optionLabel(filter.options, filter.value),
            }))}
            onRemove={(key) => onSelect(key, "")}
            onClearAll={onClear}
          />
          <BottomSheet
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            title="Filtros"
            closeLabel="Cerrar filtros"
            footer={
              <div className="flex gap-2">
                <Button size="large" className="flex-1" onClick={onClear}>
                  Limpiar
                </Button>
                <Button
                  size="large"
                  type="primary"
                  className="flex-1"
                  onClick={() => setSheetOpen(false)}
                >
                  Ver resultados
                </Button>
              </div>
            }
          >
            <div role="group" aria-label="Filtros" className="grid gap-3">
              {selects.map((filter) => control(filter, true))}
            </div>
          </BottomSheet>
        </>
      )}
    </>
  );
}
