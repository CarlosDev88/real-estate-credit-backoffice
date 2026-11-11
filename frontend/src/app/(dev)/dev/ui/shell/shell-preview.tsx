"use client";

import { AppShell } from "@/components/ui/app-shell";
import { groupNav, NAV_ITEMS } from "@/lib/navigation/nav-config";
import { useToast } from "@/providers/toast";

// Usuario de muestra: la demo no llama a la API.
const SAMPLE_USER = { name: "Usuario de Ejemplo", email: "usuario@example.com" };

export function ShellPreview() {
  const toast = useToast();
  return (
    <AppShell
      nav={groupNav(NAV_ITEMS)}
      user={SAMPLE_USER}
      activeHref="/solicitudes"
      onLogout={() => toast.info({ title: "Cerrar sesión", message: "En la demo no hace nada." })}
    >
      <h1 className="m-0 text-3xl font-semibold tracking-tight">Contenido de la página</h1>
      <p className="text-text-secondary mt-1">
        Demo del shell: barra lateral, barra superior, tema y menú de la cuenta.
      </p>
    </AppShell>
  );
}
