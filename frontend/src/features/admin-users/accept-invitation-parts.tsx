"use client";

import { Button } from "antd";
import type { ReactNode } from "react";

// Piezas que comparten la pantalla de la invitación y su formulario (que se carga aparte).

const LOGIN_HREF = "/login";
export const ASK_AGAIN = "Pídele una invitación nueva a quien te invitó.";

export function Notice({
  title,
  children,
  role,
}: {
  title: string;
  children?: ReactNode;
  role?: "status" | "alert";
}) {
  return (
    <div role={role} className="grid gap-3">
      <h1 className="m-0 text-3xl font-semibold tracking-tight">{title}</h1>
      {children}
    </div>
  );
}

export function LoginLink() {
  return (
    // Un enlace con forma de botón: la acción es ir a otra página.
    <div>
      <Button type="primary" size="large" href={LOGIN_HREF}>
        Iniciar sesión
      </Button>
    </div>
  );
}
