"use client";

import { useCallback, useRef } from "react";

/**
 * `Idempotency-Key` de un intento del usuario (API §5): la misma clave en los reintentos
 * de ese intento y una nueva cuando el intento termina bien (`reset`) o cambia lo que se
 * pide (otro `scope`, por ejemplo otros filtros).
 */
export function useIdempotencyKey(scope: string) {
  const ref = useRef<{ scope: string; key: string } | null>(null);

  const current = useCallback(() => {
    if (!ref.current || ref.current.scope !== scope) {
      ref.current = { scope, key: crypto.randomUUID() };
    }
    return ref.current.key;
  }, [scope]);

  const reset = useCallback(() => {
    ref.current = null;
  }, []);

  return { current, reset };
}
