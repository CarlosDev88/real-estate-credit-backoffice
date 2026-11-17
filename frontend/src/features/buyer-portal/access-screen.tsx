"use client";

import { Button } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { PortalNotice } from "@/features/buyer-portal/portal-notice";
import { useConsumeLink } from "@/features/buyer-portal/queries";
import { isApiError } from "@/lib/api/errors";

export const ACCESS_PATH = "/acceso";
const ASK_ADVISOR = "Pídele un enlace nuevo a tu asesor.";

// Título de cada error del enlace (API §8). El detalle es el `message` de la API.
const INVALID_TITLE = "Este enlace no es válido";
const LINK_ERROR_TITLES: Record<string, string> = {
  MAGIC_LINK_EXPIRED: "Este enlace venció",
  MAGIC_LINK_CONSUMED: "Este enlace ya se usó",
  MAGIC_LINK_REVOKED: "Este enlace ya no sirve",
  MAGIC_LINK_INVALID: INVALID_TITLE,
};
const FALLBACK_TITLE = "No pudimos abrir tu acceso";

/** "Demasiados intentos, espera N minutos", con N desde `Retry-After`. */
export function tooManyAttemptsMessage(seconds: number | null): string {
  if (seconds === null) return "Demasiados intentos, espera unos minutos.";
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `Demasiados intentos, espera ${minutes} ${minutes === 1 ? "minuto" : "minutos"}.`;
}

/**
 * Lee el token, lo quita de la URL antes de cualquier otra cosa y lo cambia por la
 * sesión (`POST /buyer-access/consume`). El token queda solo en memoria.
 */
function takeToken(): string | null {
  const token = new URLSearchParams(window.location.search).get("token");
  window.history.replaceState(window.history.state, "", ACCESS_PATH);
  return token?.trim() || null;
}

export function AccessScreen() {
  const router = useRouter();
  const consume = useConsumeLink();
  const token = useRef<string | null>(null);
  const started = useRef(false);
  const [missing, setMissing] = useState(false);

  const send = consume.mutate;
  useEffect(() => {
    // Una sola vez, también con el doble efecto de desarrollo: el token ya no está en la URL.
    if (started.current) return;
    started.current = true;
    token.current = takeToken();
    if (!token.current) {
      setMissing(true);
      return;
    }
    send(token.current, { onSuccess: () => router.replace("/portal") });
  }, [send, router]);

  if (missing) {
    return (
      <PortalNotice title={INVALID_TITLE}>
        <p className="m-0">{ASK_ADVISOR}</p>
      </PortalNotice>
    );
  }

  if (consume.isError) {
    const error = consume.error;
    if (isApiError(error) && error.status === 429) {
      return (
        <PortalNotice title={tooManyAttemptsMessage(error.retryAfter)}>
          <p className="m-0">{error.message}</p>
        </PortalNotice>
      );
    }
    // Sin respuesta o error del servidor: el enlace sigue sin usar y se puede reintentar.
    const retryable = !isApiError(error) || error.isNetworkError || error.status >= 500;
    if (retryable) {
      return (
        <PortalNotice
          title={FALLBACK_TITLE}
          action={
            <Button
              type="primary"
              size="large"
              loading={consume.isPending}
              onClick={() =>
                token.current && send(token.current, { onSuccess: () => router.replace("/portal") })
              }
            >
              Reintentar
            </Button>
          }
        >
          <p className="m-0">{error.message}</p>
        </PortalNotice>
      );
    }
    return (
      <PortalNotice title={LINK_ERROR_TITLES[error.code] ?? FALLBACK_TITLE}>
        <p className="m-0">{error.message}</p>
        <p className="m-0">{ASK_ADVISOR}</p>
      </PortalNotice>
    );
  }

  return (
    <PortalNotice title="Abriendo tu solicitud…" role="status">
      <p className="m-0">Un momento, estamos verificando tu enlace.</p>
    </PortalNotice>
  );
}
