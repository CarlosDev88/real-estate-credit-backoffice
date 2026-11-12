"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Me = components["schemas"]["Me"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type LoginResponse = components["schemas"]["LoginResponse"];

export const meQueryKey = ["auth", "me"] as const;

/** Usuario interno actual: fuente de verdad de permisos y menú (API §7). */
export function useMe(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async () => (await call(api.GET("/api/v1/auth/me"))).data,
    retry: false,
    staleTime: 60_000,
    enabled: options.enabled ?? true,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (body: LoginRequest) =>
      (await call(api.POST("/api/v1/auth/login", { body }))).data,
    onSuccess: () => queryClient.removeQueries({ queryKey: meQueryKey }),
  });
}

export function useLogout() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async () => {
      await call(api.POST("/api/v1/auth/logout"));
    },
  });
}
