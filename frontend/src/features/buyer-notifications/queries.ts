"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type BuyerNotification = components["schemas"]["BuyerNotification"];

/** Cuelgan de `["buyer"]`: al salir o vencer la sesión se borran con todo lo del portal. */
export const notificationKeys = {
  all: ["buyer", "notifications"] as const,
  list: ["buyer", "notifications", "list"] as const,
  unread: ["buyer", "notifications", "unread-count"] as const,
};

export const NOTIFICATIONS_PAGE_SIZE = 50;

/** Número de avisos sin leer, para la navegación del portal. */
export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: notificationKeys.unread,
    queryFn: async () =>
      (await call(api.GET("/api/v1/buyer/notifications/unread-count"))).data.count,
    enabled,
    staleTime: 60_000,
  });
}

/** Avisos de la solicitud (de la más nueva a la más vieja), de a 50, con "Ver más". */
export function useNotifications() {
  return useInfiniteQuery({
    queryKey: notificationKeys.list,
    initialPageParam: 1,
    queryFn: async ({ pageParam }) =>
      (
        await call(
          api.GET("/api/v1/buyer/notifications", {
            params: { query: { page: pageParam, page_size: NOTIFICATIONS_PAGE_SIZE } },
          }),
        )
      ).data,
    getNextPageParam: (last) => (last.next ? last.page + 1 : undefined),
  });
}

/**
 * Los no leídos primero y, dentro de cada grupo, del más nuevo al más viejo. Ordena lo que
 * ya llegó (las páginas de la API van por fecha). `unread` dice cuáles cuentan como no
 * leídos: la vista pasa los que lo eran al llegar, para que uno no salte al abrirlo.
 */
export function sortNotifications(
  items: BuyerNotification[],
  unread: (n: BuyerNotification) => boolean = (n) => !n.read_at,
): BuyerNotification[] {
  return [...items].sort((a, b) => {
    const ua = unread(a);
    const ub = unread(b);
    if (ua !== ub) return ua ? -1 : 1;
    return b.created_at.localeCompare(a.created_at);
  });
}

function useRefreshNotifications() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: notificationKeys.all });
}

/** Marca un aviso como leído (idempotente en la API). */
export function useMarkRead() {
  const refresh = useRefreshNotifications();
  return useMutation({
    mutationFn: async (id: string) =>
      (
        await call(
          api.PATCH("/api/v1/buyer/notifications/{notification_id}/read", {
            params: { path: { notification_id: id } },
          }),
        )
      ).data,
    onSuccess: () => refresh(),
  });
}

export function useMarkAllRead() {
  const refresh = useRefreshNotifications();
  return useMutation({
    mutationFn: async () =>
      (await call(api.POST("/api/v1/buyer/notifications/read-all"))).data.count,
    onSuccess: () => refresh(),
  });
}
