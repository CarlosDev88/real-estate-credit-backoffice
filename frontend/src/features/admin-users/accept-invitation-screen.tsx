"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { LogoMark } from "@/components/ui/icons";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ASK_AGAIN, LoginLink, Notice } from "@/features/admin-users/accept-invitation-parts";
import type { AcceptedUser } from "@/features/admin-users/queries";

// El formulario se pide solo cuando hay token (PERF-08).
const AcceptForm = dynamic(
  () => import("@/features/admin-users/accept-invitation-form").then((m) => m.AcceptForm),
  { loading: () => <Opening /> },
);

/** Ruta del correo de invitación (`INVITATION_ACCEPT_URL` del backend). */
export const ACCEPT_INVITATION_PATH = "/aceptar-invitacion";

/**
 * Lee el token y lo quita de la URL antes de cualquier otra cosa (como `/acceso` del
 * portal): no queda en el historial, ni en el `Referer`, ni en una captura de pantalla.
 */
function takeToken(): string | null {
  const token = new URLSearchParams(window.location.search).get("token");
  window.history.replaceState(window.history.state, "", ACCEPT_INVITATION_PATH);
  return token?.trim() || null;
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="bg-bg-canvas relative grid min-h-screen place-items-center px-4 py-16 max-[600px]:place-items-start max-[600px]:pt-20">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <main className="w-full max-w-[440px]">
        <div className="text-text-primary mb-8 inline-flex items-center gap-2 text-xl font-semibold tracking-tight">
          <LogoMark size={28} />
          Umbral
        </div>
        {children}
      </main>
    </div>
  );
}

function Opening() {
  return (
    <p role="status" className="text-text-tertiary m-0">
      Abriendo tu invitación…
    </p>
  );
}

/**
 * `/aceptar-invitacion?token=…` (pública, sin sesión): el invitado define su nombre y su
 * contraseña (`POST /invitations/accept`). No inicia sesión: al terminar, va al login.
 */
export function AcceptInvitationScreen({ hasToken = true }: { hasToken?: boolean }) {
  // `undefined`: todavía no se leyó la URL (primer render, también en el servidor). Sin
  // token en la URL, el servidor ya pinta el aviso: no espera a hidratar (PERF-08).
  const [token, setToken] = useState<string | null | undefined>(hasToken ? undefined : null);
  const [accepted, setAccepted] = useState<AcceptedUser | null>(null);
  const started = useRef(false);

  useEffect(() => {
    // Una sola vez, también con el doble efecto de desarrollo: el token ya no está en la URL.
    if (started.current) return;
    started.current = true;
    setToken(takeToken());
  }, []);

  let content;
  if (token === undefined) {
    content = <Opening />;
  } else if (token === null) {
    content = (
      <Notice title="Este enlace no es válido" role="alert">
        <p className="text-text-secondary m-0">
          Abre el enlace completo del correo de invitación. {ASK_AGAIN}
        </p>
      </Notice>
    );
  } else if (accepted) {
    content = (
      <Notice title="Tu cuenta está lista" role="status">
        <p className="text-text-secondary m-0">
          Ya puedes iniciar sesión con <b className="text-text-primary">{accepted.email}</b> y la
          contraseña que definiste.
        </p>
        <LoginLink />
      </Notice>
    );
  } else {
    content = <AcceptForm token={token} onAccepted={setAccepted} />;
  }

  return <Frame>{content}</Frame>;
}
