"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { describeMutationError } from "@/lib/api/error-feedback";
import type { ErrorDetail } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

/**
 * Muestra el toast de un error de la API con las reglas de la spec. Lo usa el
 * manejador global de escrituras y, para los detalles que no caben en ningún
 * campo, los formularios que manejan su propio error.
 */
export function useApiErrorToast(): (error: unknown, details?: ErrorDetail[]) => void {
  const toast = useToast();
  const queryClient = useQueryClient();

  return useCallback(
    (error: unknown, details?: ErrorDetail[]) => {
      const spec = describeMutationError(error, details);
      toast.show({
        tone: spec.tone,
        title: spec.title,
        duration: spec.reload ? false : undefined,
        message:
          spec.detail || spec.requestId ? (
            <>
              {spec.detail && <span className="block">{spec.detail}</span>}
              {spec.requestId && (
                <span className="text-text-tertiary mt-1 block font-mono text-xs">
                  Código: {spec.requestId}
                </span>
              )}
            </>
          ) : undefined,
        action: spec.reload
          ? { label: "Recargar", onClick: () => void queryClient.invalidateQueries() }
          : undefined,
      });
    },
    [toast, queryClient],
  );
}
