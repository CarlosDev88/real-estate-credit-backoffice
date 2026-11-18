"use client";

import { useCallback, useMemo } from "react";

import { useBootstrap } from "@/features/applications/queries";

/** Opciones de un `Select` a partir de valores de catálogo (código y etiqueta de la API). */
export function optionsOf(items: readonly { code: string; label: string }[]) {
  return items.map((item) => ({ value: item.code, label: item.label }));
}

/**
 * Etiqueta de un código según el catálogo del bootstrap, con los valores activos e
 * inactivos (un estado retirado conserva su texto). Mientras carga, o si no está,
 * devuelve el código.
 */
export function useCatalogLabel(code: string): (value: string) => string {
  const bootstrap = useBootstrap();
  const raw = bootstrap.data?.catalogs[code];
  const map = useMemo(() => new Map((raw ?? []).map((item) => [item.code, item.label])), [raw]);
  return useCallback((value: string) => map.get(value) ?? value, [map]);
}
