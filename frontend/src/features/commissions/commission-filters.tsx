"use client";

import { Button, Input, Select } from "antd";
import { useId, useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { FilterChips, type FilterChip } from "@/components/ui/filter-chips";
import { FilterIcon } from "@/components/ui/icons";
import { isApiError } from "@/lib/api/errors";
import { formatDateOnly } from "@/lib/format";

export type FilterDef =
  | { type: "date"; key: string; label: string; min?: string; max?: string }
  | {
      type: "select";
      key: string;
      /** Nombre del filtro ("Banco"). */
      label: string;
      /** Texto de "sin filtro" ("todos"). */
      allLabel: string;
      options: { value: string; label: string }[];
      loading?: boolean;
      /** Ancho en escritorio. */
      width: number;
    };

/** Mensaje de un `400` por filtro (`details[].field`). */
export function filterErrors(
  error: unknown,
  keys: readonly string[],
): Partial<Record<string, string>> {
  if (!isApiError(error) || error.status !== 400) return {};
  const out: Partial<Record<string, string>> = {};
  for (const detail of error.fieldDetails) {
    const key = detail.field ?? "";
    if (keys.includes(key) && !out[key]) out[key] = detail.message;
  }
  return out;
}

function valueLabel(def: FilterDef, value: string): string {
  if (def.type === "date") return formatDateOnly(value) ?? value;
  if (value === "") return def.allLabel;
  return def.options.find((o) => o.value === value)?.label ?? "…";
}

/**
 * Barra de filtros de comisiones (en la URL): fechas de desembolso y listas. En móvil
 * (≤ 860 px), como la del dashboard: un botón "Filtros" abre la hoja inferior y los
 * activos se ven como chips.
 */
export function CommissionFilters({
  defs,
  values,
  errors,
  onChange,
  onClear,
  active,
  mobile,
}: {
  defs: FilterDef[];
  values: Record<string, string>;
  errors: Partial<Record<string, string>>;
  onChange: (patch: Record<string, string>) => void;
  onClear: () => void;
  active: boolean;
  mobile: boolean;
}) {
  const base = useId();
  const [sheetOpen, setSheetOpen] = useState(false);
  const errorId = (key: string) => `${base}-${key}-error`;
  const control = (key: string) => ({
    status: errors[key] ? ("error" as const) : undefined,
    "aria-invalid": errors[key] ? (true as const) : undefined,
    "aria-describedby": errors[key] ? errorId(key) : undefined,
  });
  const entries = Object.entries(errors).filter((e): e is [string, string] => !!e[1]);

  const controls = (block: boolean) =>
    defs.map((def) => {
      const size = block ? "large" : "middle";
      if (def.type === "date") {
        const id = `${base}-${def.key}`;
        return (
          <div key={def.key} className={block ? "grid gap-1.5" : "flex items-center gap-2"}>
            <label
              htmlFor={id}
              className={block ? "text-sm font-medium" : "text-text-secondary text-sm"}
            >
              {def.label}
            </label>
            <Input
              id={id}
              type="date"
              size={size}
              value={values[def.key] ?? ""}
              min={def.min}
              max={def.max}
              onChange={(event) => onChange({ [def.key]: event.target.value })}
              style={block ? undefined : { width: 140 }}
              {...control(def.key)}
            />
          </div>
        );
      }
      const current = values[def.key] ?? "";
      return (
        <Select
          key={def.key}
          aria-label={`Filtrar por ${def.label.toLowerCase()}`}
          value={current}
          onChange={(value: string) => onChange({ [def.key]: value })}
          options={[{ value: "", label: def.allLabel }, ...def.options]}
          loading={def.loading}
          virtual={false}
          popupMatchSelectWidth={false}
          size={size}
          labelRender={() => `${def.label}: ${valueLabel(def, current)}`}
          style={block ? { width: "100%" } : { width: def.width }}
          {...control(def.key)}
        />
      );
    });

  const errorList = entries.length > 0 && (
    <div role="alert">
      <ul className="text-tone-danger-fg m-0 grid list-none gap-1 p-0 text-sm">
        {entries.map(([key, message]) => (
          <li key={key} id={errorId(key)}>
            {defs.find((d) => d.key === key)?.label ?? key}: {message}
          </li>
        ))}
      </ul>
    </div>
  );

  if (mobile) {
    const chips: FilterChip[] = defs
      .filter((def) => values[def.key])
      .map((def) => ({
        key: def.key,
        label: def.label,
        value: valueLabel(def, values[def.key] ?? ""),
      }));
    return (
      <div className="bg-bg-surface border-border-default grid rounded-lg border">
        <div className="flex items-center gap-2 p-3">
          <span className="text-text-secondary min-w-0 flex-1 text-sm">
            {chips.length ? "Con filtros" : "Sin filtros"}
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
          onRemove={(key) => onChange({ [key]: "" })}
          onClearAll={onClear}
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
            {controls(true)}
            {errorList}
          </div>
        </BottomSheet>
      </div>
    );
  }

  return (
    <div className="bg-bg-surface border-border-default grid gap-2 rounded-lg border p-3">
      <div role="group" aria-label="Filtros" className="flex flex-wrap items-center gap-2">
        {controls(false)}
        {active && (
          <Button type="text" onClick={onClear}>
            Limpiar
          </Button>
        )}
      </div>
      {errorList}
    </div>
  );
}
