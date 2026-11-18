"use client";

import { Button, Input, Select } from "antd";
import { useEffect, useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips, type FilterChip } from "@/components/ui/filter-chips";
import { FilterIcon, SearchIcon } from "@/components/ui/icons";

// Barra de filtros de un listado con el estado en la URL (patrón "Lista con filtros en la
// URL" del Storybook): búsqueda con espera, selects que dicen qué filtran y, en móvil, una
// hoja inferior con los activos como chips. Candidata a la librería.

export const SEARCH_DEBOUNCE_MS = 300;

export interface ToolbarSelect {
  key: string;
  /** Nombre del filtro ("Etapa"). */
  label: string;
  /** Texto del valor por defecto ("todas"). */
  allLabel: string;
  options: { value: string; label: string }[];
  value: string;
  /** Valor que no filtra (por defecto `""`). No se cuenta como activo ni se ve como chip. */
  defaultValue?: string;
  loading?: boolean;
  /** Ancho en escritorio. */
  width: number;
}

function SearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
}) {
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
      placeholder={placeholder}
      aria-label={ariaLabel}
      prefix={<SearchIcon className="text-text-tertiary" />}
      className="min-w-0 flex-[1_1_200px]"
    />
  );
}

function optionLabel(def: ToolbarSelect): string {
  if (def.value === (def.defaultValue ?? "")) return def.allLabel;
  return def.options.find((o) => o.value === def.value)?.label ?? "…";
}

interface FilterToolbarProps {
  search?: {
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
    ariaLabel: string;
  };
  selects: ToolbarSelect[];
  onSelect: (key: string, value: string) => void;
  onClear: () => void;
  /** ≤ 860 px: hoja inferior y chips. */
  mobile: boolean;
}

export function FilterToolbar({ search, selects, onSelect, onClear, mobile }: FilterToolbarProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const isActive = (def: ToolbarSelect) => def.value !== (def.defaultValue ?? "");
  const active = selects.filter(isActive);
  const anyActive = active.length > 0 || !!search?.value;

  const select = (def: ToolbarSelect, block: boolean) => (
    <Select
      key={def.key}
      aria-label={`Filtrar por ${def.label.toLowerCase()}`}
      value={def.value}
      onChange={(value: string) => onSelect(def.key, value)}
      options={[
        ...(def.options.some((o) => o.value === (def.defaultValue ?? ""))
          ? []
          : [{ value: def.defaultValue ?? "", label: def.allLabel }]),
        ...def.options,
      ]}
      loading={def.loading}
      virtual={false}
      popupMatchSelectWidth={false}
      size={block ? "large" : "middle"}
      labelRender={() => `${def.label}: ${optionLabel(def)}`}
      style={block ? { width: "100%" } : { width: def.width }}
    />
  );

  const searchInput = search && <SearchInput {...search} />;

  if (!mobile) {
    return (
      <div className="border-border-default flex flex-wrap items-center gap-2 border-b p-3">
        {searchInput}
        <div role="group" aria-label="Filtros" className="contents">
          {selects.map((def) => select(def, false))}
          {anyActive && (
            <Button type="text" onClick={onClear}>
              Limpiar
            </Button>
          )}
        </div>
      </div>
    );
  }

  const chips: FilterChip[] = active.map((def) => ({
    key: def.key,
    label: def.label,
    value: optionLabel(def),
  }));

  return (
    <>
      <div className="border-border-default flex items-center gap-2 border-b p-3">
        {searchInput ?? <div className="flex-1" />}
        <Button aria-expanded={sheetOpen} onClick={() => setSheetOpen(true)} icon={<FilterIcon />}>
          {active.length ? `Filtros (${active.length})` : "Filtros"}
        </Button>
      </div>
      <FilterChips
        chips={chips}
        onRemove={(key) => {
          const def = selects.find((s) => s.key === key);
          if (def) onSelect(key, def.defaultValue ?? "");
        }}
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
          {selects.map((def) => select(def, true))}
        </div>
      </BottomSheet>
    </>
  );
}
