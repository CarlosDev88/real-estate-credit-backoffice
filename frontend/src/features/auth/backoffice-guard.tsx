"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Button } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { AppShell, AppShellSkeleton } from "@/components/ui/app-shell";
import { useLogout, useMe } from "@/features/auth/queries";
import { hasFirstPaintPrefetch } from "@/features/auth/route-paths";
import { isApiError } from "@/lib/api/errors";
import { redirectTo } from "@/lib/api/navigation";
import {
  audienceOf,
  defaultDestination,
  isForbiddenPath,
  visibleNav,
} from "@/lib/navigation/access";
import { groupNav, NAV_ITEMS } from "@/lib/navigation/nav-config";
import { useApiErrorToast } from "@/providers/api-error-toast";

/**
 * Guarda del grupo `(backoffice)`: pide `/auth/me` y arma el shell con el menú que
 * los permisos dejan ver. Un `401` ya lo maneja el cliente (refresh y, si falla,
 * login); aquí solo se muestra el esqueleto mientras tanto.
 */
export function BackofficeGuard({ children }: { children: ReactNode }) {
  return (
    <>
      <RoutePrefetch />
      <Guarded>{children}</Guarded>
    </>
  );
}

/**
 * Pide, a la vez que `/auth/me`, lo que la ruta de entrada necesita para su primera pintura
 * (por ahora, el expediente: PERF-01). Va aparte para que sus respuestas no vuelvan a pintar
 * el shell. El bootstrap no se adelanta: medido, sumaba TBT en las páginas que no lo usan
 * y no movía el LCP (PERF-05).
 */
function RoutePrefetch() {
  const client = useQueryClient();
  const pathname = usePathname();
  const [entry] = useState(pathname);
  useEffect(() => {
    // Solo con una ruta que lo necesita: las demás no cargan este módulo (ni sus consultas).
    if (!hasFirstPaintPrefetch(entry)) return;
    void import("@/features/auth/route-prefetch").then((m) => m.prefetchRoute(client, entry));
  }, [client, entry]);
  return null;
}

function Guarded({ children }: { children: ReactNode }) {
  const me = useMe();
  const logout = useLogout();
  const showError = useApiErrorToast();
  const pathname = usePathname();
  const router = useRouter();

  const permissions = me.data?.permissions;
  const audience = audienceOf(me.data?.roles ?? []);
  const forbidden = !!permissions && isForbiddenPath(pathname, permissions, NAV_ITEMS, audience);

  useEffect(() => {
    if (forbidden && permissions) {
      router.replace(defaultDestination(permissions, NAV_ITEMS, audience));
    }
  }, [forbidden, permissions, audience, router]);

  const unauthenticated = isApiError(me.error) && me.error.status === 401;
  if (me.isPending || unauthenticated || forbidden) return <AppShellSkeleton />;

  if (me.isError) {
    return (
      <main className="bg-bg-canvas grid min-h-screen place-items-center p-6">
        <div className="max-w-md text-center" role="alert">
          <h1 className="m-0 text-xl font-semibold">No pudimos cargar tu sesión</h1>
          <p className="text-text-secondary mt-2">{me.error.message}</p>
          <Button type="primary" onClick={() => void me.refetch()}>
            Reintentar
          </Button>
        </div>
      </main>
    );
  }

  const handleLogout = () =>
    logout.mutate(undefined, {
      // Carga completa: vacía la caché de Query y el estado de la app.
      onSuccess: () => redirectTo("/login"),
      onError: (error) => showError(error),
    });

  return (
    <AppShell
      nav={groupNav(visibleNav(me.data.permissions, NAV_ITEMS, audience))}
      user={{
        name: me.data.name || me.data.email,
        email: me.data.email,
        role: me.data.role_label,
      }}
      onLogout={handleLogout}
    >
      {children}
    </AppShell>
  );
}
