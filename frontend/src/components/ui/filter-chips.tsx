"use client";

import { Button } from "antd";

import { CloseIcon } from "@/components/ui/icons";

export interface FilterChip {
  key: string;
  /** Nombre del filtro ("Actualizada"). */
  label: string;
  /** Valor elegido, con su texto de la API ("últimos 30 días"). */
  value: string;
}

interface FilterChipsProps {
  chips: FilterChip[];
  onRemove: (key: string) => void;
  /** Texto antes de los chips (mockup: 'Desde "Más filtros":'). */
  caption?: string;
  onClearAll?: () => void;
  className?: string;
}

/**
 * Chips de filtros activos (mockup `solicitudes.html`). Solo para filtros que no se ven
 * en la barra: los visibles no se repiten como chips. Sin chips no se pinta nada.
 */
export function FilterChips({
  chips,
  onRemove,
  caption,
  onClearAll,
  className = "",
}: FilterChipsProps) {
  if (chips.length === 0) return null;
  return (
    <div
      className={`bg-bg-subtle border-border-default flex flex-wrap items-center gap-2 border-b px-3 py-2 text-sm ${className}`}
    >
      {caption && <span className="text-text-tertiary text-sm">{caption}</span>}
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="Filtros activos">
        {chips.map((chip) => (
          <li
            key={chip.key}
            className="bg-bg-surface border-border-strong inline-flex h-6 items-center gap-1.5 rounded-full border pr-1 pl-2.5 text-xs"
          >
            <span>
              {chip.label}: <b className="font-semibold">{chip.value}</b>
            </span>
            <button
              type="button"
              aria-label={`Quitar filtro ${chip.label}: ${chip.value}`}
              onClick={() => onRemove(chip.key)}
              className="text-text-tertiary hover:bg-bg-muted hover:text-text-primary grid size-[18px] cursor-pointer place-items-center rounded-full border-0 bg-transparent p-0"
            >
              <CloseIcon width={10} height={10} />
            </button>
          </li>
        ))}
      </ul>
      {onClearAll && (
        <Button type="link" size="small" onClick={onClearAll}>
          Limpiar
        </Button>
      )}
    </div>
  );
}
