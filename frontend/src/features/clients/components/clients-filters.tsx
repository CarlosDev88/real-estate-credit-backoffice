"use client";

import { Button, Input, Select } from "antd";
import { useEffect, useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips } from "@/components/ui/filter-chips";
import { SEARCH_DEBOUNCE_MS } from "@/features/applications/list-filters";
import { FilterIcon, SearchIcon } from "@/components/ui/icons";
import type { ClientListParams } from "@/features/clients/list-params";

export interface OriginOption {
  value: string;
  label: string;
}

const ORIGIN_LABEL = "Origen";
const ALL_LABEL = "todos";

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
      placeholder="Nombre, documento o correo"
      aria-label="Buscar clientes por nombre, documento o correo"
      prefix={<SearchIcon className="text-text-tertiary" />}
      className="min-w-0 flex-[1_1_200px]"
    />
  );
}

/** Texto del origen elegido; mientras llegan las opciones (o si ya no está), "…". */
export function originOptionLabel(options: OriginOption[], value: string): string {
  if (value === "") return ALL_LABEL;
  return options.find((o) => o.value === value)?.label ?? "…";
}

interface ClientsFiltersProps {
  params: ClientListParams;
  origins: OriginOption[];
  originsLoading: boolean;
  onChange: (patch: Partial<ClientListParams>) => void;
  onClear: () => void;
  /** ≤ 860 px: el filtro va en una hoja inferior y, si está activo, se ve como chip. */
  mobile: boolean;
}

/**
 * Barra del listado de clientes: búsqueda y origen (catálogo `lead_origin`). Mismo
 * comportamiento que la de `/solicitudes` (design/README.md, "Tabla").
 */
export function ClientsFilters({
  params,
  origins,
  originsLoading,
  onChange,
  onClear,
  mobile,
}: ClientsFiltersProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const anyActive = params.origin !== "" || params.search !== "";
  const originText = originOptionLabel(origins, params.origin);

  const select = (block: boolean) => (
    <Select
      aria-label="Filtrar por origen"
      value={params.origin}
      onChange={(origin: string) => onChange({ origin })}
      options={[{ value: "", label: ALL_LABEL }, ...origins]}
      loading={originsLoading}
      virtual={false}
      popupMatchSelectWidth={false}
      size={block ? "large" : "middle"}
      // En el control se ve "Origen: Broker"; en la lista, solo el valor.
      labelRender={() => `${ORIGIN_LABEL}: ${originText}`}
      style={block ? { width: "100%" } : { width: 196 }}
    />
  );

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
            {params.origin ? "Filtros (1)" : "Filtros"}
          </Button>
        ) : (
          <div role="group" aria-label="Filtros" className="contents">
            {select(false)}
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
            chips={params.origin ? [{ key: "origin", label: ORIGIN_LABEL, value: originText }] : []}
            onRemove={() => onChange({ origin: "" })}
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
              {select(true)}
            </div>
          </BottomSheet>
        </>
      )}
    </>
  );
}
