"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Button } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { PortalProvider, type PortalContextValue } from "@/features/buyer-portal/portal-context";
import {
  AccessExpiredScreen,
  LoggedOutScreen,
  PortalNotice,
  PortalSkeleton,
} from "@/features/buyer-portal/portal-notice";
import { PortalShell } from "@/features/buyer-portal/portal-shell";
import { useUnreadCount } from "@/features/buyer-notifications/queries";
import {
  buyerKeys,
  useBuyerLogout,
  useBuyerSession,
  useBuyerSlots,
} from "@/features/buyer-portal/queries";
import { isApiError } from "@/lib/api/errors";
import { setBuyerSessionExpiredHandler, setConsentRequiredHandler } from "@/lib/api/session";
import { useApiErrorToast } from "@/providers/api-error-toast";

export const CONSENTS_PATH = "/portal/consentimientos";

type Phase = "active" | "expired" | "logged-out";

/** Mayor demora que acepta `setTimeout` (unos 24 días). */
const MAX_TIMEOUT = 2_147_483_647;

/** `401` y `403` de la sesión son "acceso vencido"; la red y los `5xx` se reintentan. */
function isSessionError(error: unknown): boolean {
  return isApiError(error) && (error.status === 401 || error.status === 403);
}

function PortalFrame({
  value,
  hideNav,
  onLogout,
  children,
}: {
  value: PortalContextValue;
  hideNav: boolean;
  onLogout: () => void;
  children: ReactNode;
}) {
  const slots = useBuyerSlots(value.applicationId, !hideNav);
  const pendingDocuments = slots.data?.filter((slot) => slot.needs_action).length;
  // F5: el número de avisos sin leer en la navegación.
  const unread = useUnreadCount(!hideNav);
  return (
    <PortalProvider value={value}>
      <PortalShell
        buyerName={value.session.buyer.display_name}
        application={value.session.application}
        pendingDocuments={pendingDocuments}
        unreadNotices={unread.data}
        hideNav={hideNav}
        onLogout={onLogout}
      >
        {children}
      </PortalShell>
    </PortalProvider>
  );
}

/**
 * Guarda del grupo `(portal)`: confirma la sesión del comprador (`GET /buyer/session`),
 * manda a los consentimientos mientras falten obligatorios y pinta el marco del portal.
 * Un `401` de cualquier petición del portal lleva a "Tu acceso venció", sin datos.
 */
export function PortalGuard({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("active");
  const session = useBuyerSession(phase === "active");
  const logout = useBuyerLogout();
  const showError = useApiErrorToast();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const router = useRouter();

  const leave = useCallback(
    (next: Phase) => {
      setPhase(next);
      // Nada de la solicitud queda en memoria.
      queryClient.removeQueries({ queryKey: buyerKeys.all });
    },
    [queryClient],
  );

  // Manejadores de F0 para las respuestas de cualquier petición del portal.
  useEffect(() => {
    setBuyerSessionExpiredHandler(() => leave("expired"));
    setConsentRequiredHandler(() => {
      void queryClient.invalidateQueries({ queryKey: buyerKeys.session });
      router.replace(CONSENTS_PATH);
    });
    return () => {
      setBuyerSessionExpiredHandler(null);
      setConsentRequiredHandler(null);
    };
  }, [leave, queryClient, router]);

  const sessionError = session.isError && isSessionError(session.error);
  const expiresAt = session.data?.session.expires_at;

  // Al llegar la hora de vencimiento, sin esperar a la siguiente petición.
  useEffect(() => {
    if (!expiresAt || phase !== "active") return;
    const delay = Date.parse(expiresAt) - Date.now();
    if (!Number.isFinite(delay)) return;
    const timer = window.setTimeout(
      () => leave("expired"),
      Math.max(0, Math.min(delay, MAX_TIMEOUT)),
    );
    return () => window.clearTimeout(timer);
  }, [expiresAt, phase, leave]);

  const pendingConsents = (session.data?.pending_consents.length ?? 0) > 0;
  const mustConsent = pendingConsents && pathname !== CONSENTS_PATH;
  useEffect(() => {
    if (mustConsent) router.replace(CONSENTS_PATH);
  }, [mustConsent, router]);

  const data = session.data;
  const value = useMemo<PortalContextValue | null>(
    () =>
      data
        ? {
            session: data,
            applicationId: data.application.id,
            readOnly: data.application.is_closed || !data.application.is_editable,
            refreshSession: () => queryClient.invalidateQueries({ queryKey: buyerKeys.session }),
          }
        : null,
    [data, queryClient],
  );

  if (phase === "expired") return <AccessExpiredScreen />;
  if (phase === "logged-out") return <LoggedOutScreen />;
  // `401` de la propia sesión (sin cookie, vencida o revocada): no hay datos que borrar.
  if (sessionError) return <AccessExpiredScreen />;

  if (session.isError) {
    return (
      <PortalNotice
        title="No pudimos cargar tu solicitud"
        action={
          <Button type="primary" size="large" onClick={() => void session.refetch()}>
            Reintentar
          </Button>
        }
      >
        <p className="m-0">{session.error.message}</p>
      </PortalNotice>
    );
  }

  if (!value || mustConsent) return <PortalSkeleton />;

  const handleLogout = () =>
    logout.mutate(undefined, {
      onSuccess: () => leave("logged-out"),
      onError: (error) => {
        // Sin sesión ya no hay nada que cerrar.
        if (isApiError(error) && error.status === 401) leave("logged-out");
        else showError(error);
      },
    });

  return (
    <PortalFrame value={value} hideNav={pendingConsents} onLogout={handleLogout}>
      {children}
    </PortalFrame>
  );
}
