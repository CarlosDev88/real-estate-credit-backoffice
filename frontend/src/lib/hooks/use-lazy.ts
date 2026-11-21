"use client";

import { useEffect, useRef, useState } from "react";

type Loader = () => Promise<unknown>;

/** Espera antes de precargar: después de la primera pintura y de los datos de la página. */
const PRELOAD_DELAY_MS = 1500;

/**
 * Precarga módulos de `next/dynamic` cuando el navegador queda libre. La primera carga
 * no los trae (PERF-01), pero abrir un panel o cambiar de pestaña no espera la red.
 */
export function useIdlePreload(loaders: readonly Loader[], enabled = true): void {
  const pending = useRef(loaders);
  useEffect(() => {
    if (!enabled) return;
    let idle: number | undefined;
    const run = () => {
      for (const load of pending.current) void load().catch(() => {});
    };
    const timer = window.setTimeout(() => {
      if ("requestIdleCallback" in window)
        idle = window.requestIdleCallback(run, { timeout: 3000 });
      else run();
    }, PRELOAD_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      if (idle !== undefined) window.cancelIdleCallback(idle);
    };
  }, [enabled]);
}

/**
 * `true` desde la primera vez que `open` es `true`. Un panel o modal cargado con
 * `next/dynamic` se monta al abrirse por primera vez y queda montado, para que siga
 * cerrándose con su animación.
 */
export function useMountedOnce(open: boolean): boolean {
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);
  return mounted || open;
}
