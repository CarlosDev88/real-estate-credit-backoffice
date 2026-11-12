"use client";

import type { ReactNode } from "react";

/** Props que el control recibe para quedar enlazado con su etiqueta, ayuda y error. */
export interface FieldControlProps {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
  status: "error" | undefined;
}

/**
 * Campo con etiqueta, ayuda y error debajo, enlazados por `aria-describedby`
 * (design/README.md, accesibilidad). `children` recibe las props del control.
 */
export function FormField({
  id,
  label,
  optional,
  help,
  error,
  children,
}: {
  id: string;
  label: string;
  /** Texto entre paréntesis después de la etiqueta ("opcional"). */
  optional?: string;
  help?: string;
  error?: string | undefined;
  children: (control: FieldControlProps) => ReactNode;
}) {
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional && <span className="text-text-tertiary font-normal"> ({optional})</span>}
      </label>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy,
        status: error ? "error" : undefined,
      })}
      {error && (
        <p id={errorId} className="text-tone-danger-fg m-0 text-sm">
          {error}
        </p>
      )}
      {help && (
        <p id={helpId} className="text-text-tertiary m-0 text-xs">
          {help}
        </p>
      )}
    </div>
  );
}
