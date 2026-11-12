"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { HouseIcon, LogoMark } from "@/components/ui/icons";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { LoginForm } from "@/features/auth/login-form";
import { useMe } from "@/features/auth/queries";
import { resolveDestination } from "@/lib/navigation/access";

/** Arcos decorativos del panel de marca (mockup `login.html`). */
function Arches() {
  return (
    <svg
      viewBox="0 0 400 400"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="var(--um-text-on-sidebar-strong)"
      strokeWidth="2"
      className="pointer-events-none absolute top-10 -right-20 size-[420px] opacity-[0.18] max-[900px]:hidden"
    >
      <path d="M80 380V200a120 120 0 0 1 240 0v180" />
      <path d="M120 380V210a80 80 0 0 1 160 0v170" />
      <path d="M160 380V220a40 40 0 0 1 80 0v160" />
      <path d="M40 382h320" />
    </svg>
  );
}

export function LoginScreen({ next }: { next: string | null }) {
  const router = useRouter();
  // Con una sesión válida, el login lleva directo al destino.
  const me = useMe();

  useEffect(() => {
    if (me.data) router.replace(resolveDestination(next, me.data.permissions));
  }, [me.data, next, router]);

  return (
    <div className="relative grid min-h-screen grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] max-[900px]:grid-cols-1 max-[900px]:grid-rows-[auto_1fr]">
      <div className="absolute top-4 right-4 z-10 max-[900px]:right-3">
        <ThemeToggle className="max-[900px]:text-text-on-sidebar! max-[900px]:hover:bg-sidebar-item-hover!" />
      </div>

      <section
        aria-label="Umbral"
        className="bg-bg-sidebar text-text-on-sidebar relative flex flex-col overflow-hidden px-12 py-10 max-[900px]:p-4"
      >
        <div className="text-text-on-sidebar-strong inline-flex items-center gap-2 text-xl font-semibold tracking-tight">
          <LogoMark size={30} />
          Umbral
        </div>
        <Arches />
        <div className="relative z-[1] mt-auto max-w-[440px] max-[900px]:hidden">
          <p className="text-text-on-sidebar-strong m-0 mb-4 text-4xl font-semibold tracking-tight">
            Del primer contacto a la llave de la casa.
          </p>
          <p className="m-0 text-lg">
            Gestiona clientes, solicitudes de crédito, documentos y radicaciones en un solo lugar.
          </p>
        </div>
      </section>

      <main className="bg-bg-canvas grid place-items-center px-4 pt-16 pb-8 max-[900px]:place-items-start max-[900px]:justify-center max-[900px]:pt-6">
        <div className="w-full max-w-[400px]">
          <h1 className="m-0 mb-2 text-3xl font-semibold tracking-tight">Iniciar sesión</h1>
          <p className="text-text-secondary m-0 mb-8">
            Acceso para asesores, brokers y constructoras aliadas.
          </p>

          <LoginForm
            onSuccess={(data) => router.replace(resolveDestination(next, data.permissions))}
          />

          <div className="bg-border-default mt-8 mb-6 h-px" />

          <div className="bg-bg-surface border-border-default text-text-secondary flex gap-3 rounded-lg border p-4 text-sm">
            <HouseIcon className="text-accent-default mt-px size-5 flex-none" />
            <div>
              <b className="text-text-primary mb-0.5 block">¿Estás comprando vivienda?</b>
              No necesitas cuenta. Entra con el enlace que te envió tu asesor o broker por correo o
              WhatsApp.
            </div>
          </div>

          <p className="text-text-tertiary mt-6 text-center text-xs">
            Al ingresar aceptas el tratamiento de datos según la política de privacidad.
          </p>
        </div>
      </main>
    </div>
  );
}
