"use client";

import { Button, Input, Select } from "antd";
import { useId, useState } from "react";
import type { ReactNode } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips, type FilterChip } from "@/components/ui/filter-chips";
import { FilterIcon } from "@/components/ui/icons";
import {
  EMPTY_FILTERS,
  hasActiveFilters,
  type DashboardFilterKey,
  type DashboardFilters,
} from "@/features/dashboard/dashboard-params";
import type { Period } from "@/features/dashboard/queries";
import { formatDateOnly } from "@/lib/format";

export interface SelectFilterDef {
  key: Exclude<DashboardFilterKey, "date_from" | "date_to">;
  /** Nombre del filtro ("Banco"). */
  label: string;
  /** Texto de "sin filtro" ("todos", "todas"). */
  allLabel: string;
  options: { value: string; label: string }[];
  loading?: boolean;
  /** Ancho en escritorio. */
  width: number;
}

/** Mensaje de la API por campo (los filtros comunes y los extra de la vista). */
type FilterErrors = Partial<Record<string, string>>;

/**
 * Filtros propios de otra vista (por ejemplo, el estado y "Agrupar por" de `/reportes`):
 * se pintan después de los comunes, en la barra y en la hoja, y suman sus chips.
 */
export interface ExtraFilters {
  render: (block: boolean, control: (key: string) => FilterControlProps) => ReactNode;
  chips: FilterChip[];
  onRemoveChip: (key: string) => void;
  /** Hay algún filtro extra activo ("Limpiar" se muestra). */
  active: boolean;
  /** Nombre de cada filtro extra, para los mensajes de error. */
  labels: Record<string, string>;
}

export interface FilterControlProps {
  status: "error" | undefined;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
}

interface DashboardFiltersBarProps {
  filters: DashboardFilters;
  /** Rango efectivo que devolvió la API (el mes en curso si la URL no trae fechas). */
  period: Period | undefined;
  selects: SelectFilterDef[];
  /** Mensaje de la API por filtro (`400` o `403 FILTER_OUT_OF_SCOPE`). */
  errors: FilterErrors;
  onChange: (patch: Partial<DashboardFilters>) => void;
  /** "Limpiar": por defecto, vacía los filtros comunes. */
  onClear?: () => void;
  extra?: ExtraFilters;
  /** ≤ 860 px: los filtros van en una hoja inferior y los activos se ven como chips. */
  mobile: boolean;
}

function optionLabel(def: SelectFilterDef, value: string): string {
  if (value === "") return def.allLabel;
  return def.options.find((o) => o.value === value)?.label ?? "…";
}

/** "1 nov 2026 – 18 nov 2026". */
export function periodLabel(period: Period | undefined): string | null {
  if (!period) return null;
  const from = formatDateOnly(period.date_from);
  const to = formatDateOnly(period.date_to);
  return from && to ? `${from} – ${to}` : null;
}

function errorId(base: string, key: string) {
  return `${base}-${key}-error`;
}

/** Barra de filtros del dashboard: fechas, asesor, banco y finalidad, en la URL. */
export function DashboardFiltersBar({
  filters,
  period,
  selects,
  errors,
  onChange,
  onClear,
  extra,
  mobile,
}: DashboardFiltersBarProps) {
  const base = useId();
  const [sheetOpen, setSheetOpen] = useState(false);
  const active = hasActiveFilters(filters) || !!extra?.active;
  const errorEntries = Object.entries(errors).filter(
    (entry): entry is [string, string] => !!entry[1],
  );
  const labelOf = (key: string) =>
    key === "date_from"
      ? "Desde"
      : key === "date_to"
        ? "Hasta"
        : (selects.find((s) => s.key === key)?.label ?? extra?.labels[key] ?? key);

  const control = (key: string): FilterControlProps => ({
    status: errors[key] ? ("error" as const) : undefined,
    "aria-invalid": errors[key] ? true : undefined,
    "aria-describedby": errors[key] ? errorId(base, key) : undefined,
  });

  const dateInput = (key: "date_from" | "date_to", label: string, block: boolean) => {
    const id = `${base}-${key}`;
    return (
      <div className={block ? "grid gap-1.5" : "flex items-center gap-2"}>
        <label
          htmlFor={id}
          className={block ? "text-sm font-medium" : "text-text-secondary text-sm"}
        >
          {label}
        </label>
        <Input
          id={id}
          type="date"
          size={block ? "large" : "middle"}
          value={filters[key] || period?.[key] || ""}
          max={key === "date_from" ? filters.date_to || period?.date_to : undefined}
          min={key === "date_to" ? filters.date_from || period?.date_from : undefined}
          onChange={(event) => onChange({ [key]: event.target.value })}
          style={block ? undefined : { width: 140 }}
          {...control(key)}
        />
      </div>
    );
  };

  const select = (def: SelectFilterDef, block: boolean) => (
    <Select
      key={def.key}
      aria-label={`Filtrar por ${def.label.toLowerCase()}`}
      value={filters[def.key]}
      onChange={(value: string) => onChange({ [def.key]: value })}
      options={[{ value: "", label: def.allLabel }, ...def.options]}
      loading={def.loading}
      virtual={false}
      popupMatchSelectWidth={false}
      size={block ? "large" : "middle"}
      labelRender={() => `${def.label}: ${optionLabel(def, filters[def.key])}`}
      style={block ? { width: "100%" } : { width: def.width }}
      {...control(def.key)}
    />
  );

  const errorList = errorEntries.length > 0 && (
    <div role="alert">
      <ul className="text-tone-danger-fg m-0 grid list-none gap-1 p-0 text-sm">
        {errorEntries.map(([key, message]) => (
          <li key={key} id={errorId(base, key)}>
            {labelOf(key)}: {message}
          </li>
        ))}
      </ul>
    </div>
  );

  const clear = onClear ?? (() => onChange(EMPTY_FILTERS));

  if (mobile) {
    const chips: FilterChip[] = [];
    if (filters.date_from || filters.date_to) {
      chips.push({ key: "dates", label: "Periodo", value: periodLabel(period) ?? "…" });
    }
    for (const def of selects) {
      if (filters[def.key]) {
        chips.push({ key: def.key, label: def.label, value: optionLabel(def, filters[def.key]) });
      }
    }
    chips.push(...(extra?.chips ?? []));
    return (
      <div className="bg-bg-surface border-border-default grid rounded-lg border">
        <div className="flex items-center gap-2 p-3">
          <span className="text-text-secondary min-w-0 flex-1 text-sm">
            {periodLabel(period) ?? "Mes en curso"}
          </span>
          <Button
            aria-expanded={sheetOpen}
            onClick={() => setSheetOpen(true)}
            icon={<FilterIcon />}
          >
            {chips.length ? `Filtros (${chips.length})` : "Filtros"}
          </Button>
        </div>
        <FilterChips
          chips={chips}
          className="rounded-b-lg border-t border-b-0"
          onRemove={(key) => {
            if (key === "dates") onChange({ date_from: "", date_to: "" });
            else if (extra?.chips.some((c) => c.key === key)) extra.onRemoveChip(key);
            else onChange({ [key]: "" });
          }}
          onClearAll={clear}
        />
        {/* Con la hoja abierta, los errores se ven dentro de ella (una sola vez por id). */}
        {errorList && !sheetOpen && (
          <div className="border-border-default border-t p-3">{errorList}</div>
        )}
        <BottomSheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title="Filtros"
          closeLabel="Cerrar filtros"
          footer={
            <div className="flex gap-2">
              <Button size="large" className="flex-1" onClick={clear}>
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
            {dateInput("date_from", "Desde", true)}
            {dateInput("date_to", "Hasta", true)}
            {selects.map((def) => select(def, true))}
            {extra?.render(true, control)}
            {errorList}
          </div>
        </BottomSheet>
      </div>
    );
  }

  return (
    <div className="bg-bg-surface border-border-default grid gap-2 rounded-lg border p-3">
      <div role="group" aria-label="Filtros" className="flex flex-wrap items-center gap-2">
        {dateInput("date_from", "Desde", false)}
        {dateInput("date_to", "Hasta", false)}
        {selects.map((def) => select(def, false))}
        {extra?.render(false, control)}
        {active && (
          <Button type="text" onClick={clear}>
            Limpiar
          </Button>
        )}
      </div>
      {errorList}
    </div>
  );
}
