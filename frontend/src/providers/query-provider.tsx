"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { isApiError } from "@/lib/api/errors";
import { useApiErrorToast } from "@/providers/api-error-toast";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: {
      /** La escritura maneja su propio error (por ejemplo, un formulario): sin toast global. */
      handlesErrors?: boolean;
    };
  }
}

type ErrorListener = (error: unknown) => void;
const mutationErrorListeners = new Set<ErrorListener>();

/** Suscribe a los errores de escritura que no maneja su propia mutación. */
export function onMutationError(listener: ErrorListener): () => void {
  mutationErrorListeners.add(listener);
  return () => mutationErrorListeners.delete(listener);
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.handlesErrors) return;
        mutationErrorListeners.forEach((listener) => listener(error));
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Los 4xx no mejoran reintentando; los 5xx y la red, una vez.
        retry: (count, error) =>
          count < 1 && !(isApiError(error) && error.status >= 400 && error.status < 500),
      },
      mutations: { retry: false },
    },
  });
}

/** Muestra en un toast los errores de escritura (reglas de la spec, parte 3). */
function MutationErrorToaster() {
  const show = useApiErrorToast();
  useEffect(() => onMutationError(show), [show]);
  return null;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // Un cliente por sesión del navegador (no compartido entre peticiones del servidor).
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <MutationErrorToaster />
      {children}
    </QueryClientProvider>
  );
}
