"use client";

import { Button, ConfigProvider, Input, Select } from "antd";
import { useState } from "react";
import type { ReactNode } from "react";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import type { FieldControlProps } from "@/components/ui/form-field";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { PORTAL_HOME, PortalPage } from "@/features/buyer-portal/portal-shell";
import { useBuyerCatalog } from "@/features/buyer-portal/queries";
import { isApiError, isReadOnlyError, type ErrorDetail } from "@/lib/api/errors";
import { useApiErrorToast } from "@/providers/api-error-toast";

export const REQUIRED = "Este campo es obligatorio.";
export const NOT_NEGATIVE = "No puede ser negativo.";
export const maxText = (max: number) => `Máximo ${max} caracteres.`;

/** Página de formulario del portal: volver al inicio, título y, en solo lectura, todo deshabilitado. */
export function FormScreen({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  const { readOnly } = usePortal();
  return (
    <PortalPage>
      <PageHeader
        variant="portal"
        back={{ href: PORTAL_HOME, label: "Volver al inicio" }}
        title={title}
        description={description}
      />
      <ConfigProvider componentDisabled={readOnly}>{children}</ConfigProvider>
    </PortalPage>
  );
}

/** Una columna en móvil y dos en escritorio. */
export function FieldGrid({ children }: { children: ReactNode }) {
  return <div className="grid items-start gap-4 min-[900px]:grid-cols-2">{children}</div>;
}

/** Dato que el comprador no edita (lo corrige el asesor). */
export function ReadOnlyField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid gap-1">
      <span className="text-text-tertiary text-sm">{label}</span>
      <span className="text-md font-medium">{value || "—"}</span>
    </div>
  );
}

/**
 * "Guardar" del formulario: en móvil queda fijo abajo (sobre la barra de navegación);
 * en escritorio, al final del formulario. En solo lectura no se muestra.
 */
export function FormActions({ saving, label = "Guardar" }: { saving: boolean; label?: string }) {
  const { readOnly } = usePortal();
  if (readOnly) return null;
  return (
    <div className="bg-bg-canvas/95 border-border-default sticky bottom-[calc(76px+env(safe-area-inset-bottom))] z-10 -mx-4 border-t px-4 py-3 min-[900px]:static min-[900px]:mx-0 min-[900px]:border-0 min-[900px]:bg-transparent min-[900px]:p-0">
      <Button type="primary" htmlType="submit" size="large" block loading={saving}>
        {label}
      </Button>
    </div>
  );
}

/** `addresses[0].line1` → `addresses.0.line1` (nombre de campo de React Hook Form). */
export function toFormPath(field: string): string {
  return field.replace(/\[(\d+)\]/g, ".$1");
}

/**
 * Errores de una escritura del portal:
 * - `409` de solo lectura: vuelve a pedir la sesión (franja y formularios bloqueados) y avisa;
 * - `details[].field` de un campo conocido: debajo del campo;
 * - el resto (y `409 STALE_VERSION`, con "Recargar"): al toast global.
 */
export function useSaveErrors<T extends FieldValues>(
  setError: UseFormSetError<T>,
  isField: (name: string) => boolean,
) {
  const showError = useApiErrorToast();
  const { refreshSession } = usePortal();
  return (error: unknown) => {
    if (isReadOnlyError(error)) {
      void refreshSession();
      showError(error);
      return;
    }
    if (!isApiError(error) || error.details.length === 0) {
      showError(error);
      return;
    }
    const leftover: ErrorDetail[] = [];
    for (const detail of error.details) {
      const name = detail.field ? toFormPath(detail.field) : null;
      if (name && isField(name)) {
        setError(name as Path<T>, { type: detail.code, message: detail.message });
      } else {
        leftover.push(detail);
      }
    }
    if (leftover.length) showError(error, leftover);
  };
}

// ---------- controles ----------

type SelectControlProps = FieldControlProps & {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  onBlur?: () => void;
  placeholder?: string;
  /** Campo opcional: se puede vaciar. */
  allowClear?: boolean;
  /** Etiqueta del valor actual (la que trae la API), mientras llegan las opciones. */
  currentLabel?: string | null;
};

/** Select con las opciones de un catálogo del comprador (nunca escritas en el código). */
export function CatalogSelect({
  catalog,
  parentCode,
  disabled,
  value,
  onChange,
  allowClear,
  currentLabel,
  placeholder = "Elige una opción",
  ...control
}: SelectControlProps & { catalog: string; parentCode?: string | null; disabled?: boolean }) {
  const options = useBuyerCatalog(catalog, parentCode ?? null);
  const items = options.items.map((item) => ({ value: item.code, label: item.label }));
  // Sin la opción todavía (cargando), el valor se ve con su etiqueta y no con el código.
  if (value && currentLabel && !items.some((item) => item.value === value)) {
    items.push({ value, label: currentLabel });
  }
  return (
    <Select
      {...control}
      size="large"
      showSearch={{ optionFilterProp: "label" }}
      allowClear={allowClear}
      disabled={disabled}
      placeholder={placeholder}
      loading={options.isPending}
      value={value || undefined}
      onChange={(next) => onChange((next as string | undefined) ?? null)}
      options={items}
    />
  );
}

/**
 * Ciudad: departamento y municipio filtrado por `parent_code`. Solo el municipio se
 * guarda; el departamento de un valor existente se busca en el catálogo de municipios.
 */
export function CitySelect({
  id,
  value,
  onChange,
  onBlur,
  status,
  currentLabel,
  ...aria
}: SelectControlProps) {
  const [chosen, setChosen] = useState<string | null>(null);
  const lookup = useBuyerCatalog("municipality", null, !!value && chosen === null);
  const known = lookup.items.find((item) => item.code === value)?.parent_code ?? null;
  const department = chosen ?? known;

  return (
    <div className="grid gap-2 min-[520px]:grid-cols-2">
      <CatalogSelect
        catalog="department"
        id={`${id}-department`}
        aria-label="Departamento"
        aria-invalid={undefined}
        aria-describedby={undefined}
        status={undefined}
        placeholder="Departamento"
        value={department}
        onChange={(next) => {
          setChosen(next ?? "");
          onChange(null);
        }}
      />
      <CatalogSelect
        catalog="municipality"
        parentCode={department || null}
        disabled={!department && !value}
        id={id}
        currentLabel={currentLabel}
        status={status}
        {...aria}
        placeholder="Municipio"
        value={value}
        onChange={onChange}
        onBlur={onBlur}
      />
    </div>
  );
}

/** Fecha (`YYYY-MM-DD`) con el selector nativo, que en móvil es el del sistema. */
export function DateInput({
  value,
  onChange,
  onBlur,
  ...control
}: FieldControlProps & {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  onBlur?: () => void;
}) {
  return (
    <Input
      {...control}
      type="date"
      size="large"
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value || null)}
      onBlur={onBlur}
    />
  );
}

/** Carga de un formulario del portal: la forma de sus dos primeras tarjetas. */
export function FormLoading() {
  return <LoadingState variant="portal" blocks={[192, 128]} />;
}

/** Error al cargar los datos de un formulario del portal (mismo texto en los cuatro). */
export function FormLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <ErrorState
      variant="page"
      title="No pudimos cargar tus datos"
      message={message}
      onRetry={onRetry}
    />
  );
}
