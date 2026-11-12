"use client";

import { Button } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { AppShell, AppShellSkeleton } from "@/components/ui/app-shell";
import { useLogout, useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { redirectTo } from "@/lib/api/navigation";
import { defaultDestination, isForbiddenPath, visibleNav } from "@/lib/navigation/access";
import { groupNav } from "@/lib/navigation/nav-config";
import { useApiErrorToast } from "@/providers/api-error-toast";

/**
 * Guarda del grupo `(backoffice)`: pide `/auth/me` y arma el shell con el menú que
 * los permisos dejan ver. Un `401` ya lo maneja el cliente (refresh y, si falla,
 * login); aquí solo se muestra el esqueleto mientras tanto.
 */
export function BackofficeGuard({ children }: { children: ReactNode }) {
  const me = useMe();
  const logout = useLogout();
  const showError = useApiErrorToast();
  const pathname = usePathname();
  const router = useRouter();

  const permissions = me.data?.permissions;
  const forbidden = !!permissions && isForbiddenPath(pathname, permissions);

  useEffect(() => {
    if (forbidden && permissions) router.replace(defaultDestination(permissions));
  }, [forbidden, permissions, router]);

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
      nav={groupNav(visibleNav(me.data.permissions))}
      user={{ name: me.data.name || me.data.email, email: me.data.email }}
      onLogout={handleLogout}
    >
      {children}
    </AppShell>
  );
}
