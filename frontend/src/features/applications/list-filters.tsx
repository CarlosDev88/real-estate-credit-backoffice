"use client";

import { Button, Input, Select } from "antd";
import { useEffect, useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips, type FilterChip } from "@/components/ui/filter-chips";
import { FilterIcon, SearchIcon } from "@/components/ui/icons";
import type { FilterKey, ListParams } from "@/features/applications/list-params";
import { FILTER_KEYS } from "@/features/applications/list-params";

export const SEARCH_DEBOUNCE_MS = 300;

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDef {
  key: FilterKey;
  /** Nombre del filtro ("Banco"). */
  label: string;
  /** Texto de "sin filtro" ("todos", "todas"). */
  allLabel: string;
  ariaLabel: string;
  options: FilterOption[];
  loading?: boolean;
  /** Ancho en escritorio (mockup). */
  width: number;
}

function SearchInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
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
      placeholder="Código, nombre o cédula"
      aria-label="Buscar en solicitudes por código, nombre o cédula"
      prefix={<SearchIcon className="text-text-tertiary" />}
      className="min-w-0 flex-[1_1_200px]"
    />
  );
}

function FilterSelect({
  def,
  value,
  onChange,
  block = false,
}: {
  def: FilterDef;
  value: string;
  onChange: (value: string) => void;
  block?: boolean;
}) {
  const options = [{ value: "", label: def.allLabel }, ...def.options];
  return (
    <Select
      aria-label={def.ariaLabel}
      value={value}
      onChange={onChange}
      options={options}
      loading={def.loading}
      virtual={false}
      popupMatchSelectWidth={false}
      size={block ? "large" : "middle"}
      // En el control se ve "Banco: FNA"; en la lista, solo el valor.
      labelRender={() => `${def.label}: ${optionLabel(def, value)}`}
      style={block ? { width: "100%" } : { width: def.width }}
    />
  );
}

/** Texto del valor elegido; mientras llegan las opciones (o si ya no está), "…". */
export function optionLabel(def: FilterDef, value: string): string {
  if (value === "") return def.allLabel;
  return def.options.find((o) => o.value === value)?.label ?? "…";
}

interface ListFiltersProps {
  params: ListParams;
  filters: FilterDef[];
  onChange: (patch: Partial<ListParams>) => void;
  onClear: () => void;
  /** ≤ 860 px: los filtros van en una hoja inferior y los activos se ven como chips. */
  mobile: boolean;
  /**
   * Filtros que llegan en la URL y no tienen control en la barra (el estado, desde el
   * tablero): se ven como chips en todos los tamaños, para poder quitarlos.
   */
  hiddenChips?: FilterChip[];
}

export function ListFilters({
  params,
  filters,
  onChange,
  onClear,
  mobile,
  hiddenChips = [],
}: ListFiltersProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const active = filters.filter((def) => params[def.key] !== "");
  const anyActive = active.length > 0 || params.search !== "" || hiddenChips.length > 0;

  const chips: FilterChip[] = [
    ...hiddenChips,
    ...(mobile
      ? active.map((def) => ({
          key: def.key,
          label: def.label,
          value: optionLabel(def, params[def.key]),
        }))
      : []),
  ];

  const selects = (block: boolean) =>
    filters.map((def) => (
      <FilterSelect
        key={def.key}
        def={def}
        block={block}
        value={params[def.key]}
        onChange={(value) => onChange({ [def.key]: value })}
      />
    ));

  return (
    <>
      <div
        className={`border-border-default flex items-center gap-2 border-b p-3 ${mobile ? "flex-nowrap" : "flex-wrap"}`}
      >
        <SearchInput value={params.search} onChange={(search) => onChange({ search })} />
        {mobile ? (
          <Button
            aria-expanded={sheetOpen}
            onClick={() => setSheetOpen(true)}
            icon={<FilterIcon />}
          >
            {active.length ? `Filtros (${active.length})` : "Filtros"}
          </Button>
        ) : (
          <div role="group" aria-label="Filtros" className="contents">
            {selects(false)}
            {anyActive && (
              <Button type="text" onClick={onClear}>
                Limpiar
              </Button>
            )}
          </div>
        )}
      </div>

      <FilterChips
        chips={chips}
        onRemove={(key) => {
          if ((FILTER_KEYS as string[]).includes(key) || key === "status") onChange({ [key]: "" });
        }}
        onClearAll={onClear}
      />
      {mobile && (
        <>
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
              {selects(true)}
            </div>
          </BottomSheet>
        </>
      )}
    </>
  );
}
