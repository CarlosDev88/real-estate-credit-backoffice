"use client";

import { Alert, Button, Select } from "antd";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import type { FieldValues, Path } from "react-hook-form";

import type { FieldControlProps } from "@/components/ui/form-field";
import { SidePanel } from "@/components/ui/side-panel";
import { useCatalog } from "@/features/applications/queries";
import { useMunicipalities } from "@/features/clients/detail-queries";
import { applyFieldErrors, isApiError, isReadOnlyError } from "@/lib/api/errors";
import { useApiErrorToast } from "@/providers/api-error-toast";

// Piezas comunes de la edición del expediente (Parte 3 de la F7).

export const REQUIRED = "Este campo es obligatorio.";
export const NOT_NEGATIVE = "No puede ser negativo.";
export const maxText = (max: number) => `Máximo ${max} caracteres.`;

/**
 * Errores de una escritura del expediente:
 * - bloqueo (`409 APPLICATION_NOT_EDITABLE` o `APPLICATION_CLOSED`, después de `FILED`):
 *   el mensaje de la API queda en el panel, arriba del formulario;
 * - `details[].field` de un campo del formulario: debajo del campo;
 * - el resto (también `409 STALE_VERSION`, con "Recargar"): al toast global.
 */
export function useEditErrors<T extends FieldValues>(
  setError: (name: Path<T>, error: { type: string; message: string }) => void,
  fields: readonly Path<T>[],
) {
  const showError = useApiErrorToast();
  const [locked, setLocked] = useState<string | null>(null);
  const onError = (error: unknown) => {
    if (isReadOnlyError(error) && isApiError(error)) {
      setLocked(error.message);
      return;
    }
    if (!isApiError(error) || error.details.length === 0) return showError(error);
    const leftover = applyFieldErrors(error, setError, fields);
    if (leftover.length) showError(error, leftover);
  };
  return { onError, locked, clearLocked: () => setLocked(null) };
}

/** Aviso del bloqueo con el mensaje de la API. */
export function LockedAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Alert
      type="warning"
      showIcon
      title="La solicitud ya no admite cambios"
      description={message}
    />
  );
}

/**
 * Panel lateral de edición: el formulario adentro y abajo "Cancelar" y "Guardar" (que
 * envía el formulario por su `id`). Se vacía al cerrar.
 */
export function EditPanel({
  open,
  onClose,
  eyebrow,
  title,
  formId,
  onSubmit,
  saving,
  saveLabel = "Guardar",
  extraFooter,
  children,
  width = 560,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: ReactNode;
  title: ReactNode;
  formId: string;
  onSubmit: (event?: FormEvent<HTMLFormElement>) => unknown;
  saving: boolean;
  saveLabel?: string;
  /** A la izquierda de los botones (por ejemplo, "Quitar participante"). */
  extraFooter?: ReactNode;
  children: ReactNode;
  width?: number;
}) {
  return (
    <SidePanel
      open={open}
      onClose={onClose}
      eyebrow={eyebrow}
      title={title}
      width={width}
      footer={
        <div className="flex flex-wrap items-center gap-2">
          {extraFooter}
          <div className="ml-auto flex gap-2">
            <Button onClick={onClose}>Cancelar</Button>
            <Button type="primary" htmlType="submit" form={formId} loading={saving}>
              {saveLabel}
            </Button>
          </div>
        </div>
      }
    >
      <form
        id={formId}
        noValidate
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit(event);
        }}
      >
        {children}
      </form>
    </SidePanel>
  );
}

type SelectProps = FieldControlProps & {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  onBlur?: () => void;
  placeholder?: string;
  allowClear?: boolean;
  /** Etiqueta del valor guardado, por si ya no está activo en el catálogo. */
  currentLabel?: string | null;
};

/** Select con los valores activos de un catálogo del bootstrap (nunca escritos aquí). */
export function CatalogSelect({
  catalog,
  value,
  onChange,
  onBlur,
  placeholder = "Elige una opción",
  allowClear,
  currentLabel,
  ...control
}: SelectProps & { catalog: string }) {
  const options = useCatalog(catalog);
  const items = options.items.map((item) => ({ value: item.code, label: item.label }));
  if (value && currentLabel && !items.some((item) => item.value === value)) {
    items.push({ value, label: currentLabel });
  }
  return (
    <Select
      {...control}
      showSearch={{ optionFilterProp: "label" }}
      allowClear={allowClear}
      placeholder={placeholder}
      loading={options.isPending}
      value={value || undefined}
      onChange={(next) => onChange((next as string | undefined) ?? null)}
      onBlur={onBlur}
      options={items}
      virtual={false}
    />
  );
}

/** Municipio (catálogo bajo demanda), con búsqueda por nombre. */
export function MunicipalitySelect({
  value,
  onChange,
  onBlur,
  currentLabel,
  ...control
}: SelectProps) {
  const municipalities = useMunicipalities(true);
  const items = municipalities.items.map((item) => ({ value: item.code, label: item.label }));
  if (value && currentLabel && !items.some((item) => item.value === value)) {
    items.push({ value, label: currentLabel });
  }
  return (
    <Select
      {...control}
      showSearch={{ optionFilterProp: "label" }}
      placeholder="Busca el municipio"
      loading={municipalities.isPending}
      value={value || undefined}
      onChange={(next) => onChange((next as string | undefined) ?? null)}
      onBlur={onBlur}
      options={items}
    />
  );
}
