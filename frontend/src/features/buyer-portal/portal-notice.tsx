import type { ReactNode } from "react";

/** Marca de Umbral sobre fondo claro (mockup `portal.html`): arco y umbral sobre el azul de marca. */
export function PortalLogo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--um-brand-primary)" />
      <path
        d="M10 25V15a6 6 0 0 1 12 0v10"
        fill="none"
        stroke="var(--um-brand-on-primary)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M7 25.5h18"
        stroke="var(--um-accent-default)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface PortalNoticeProps {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  /** `alert` para errores; `status` para avisos neutros (salida del portal). */
  role?: "alert" | "status";
}

/**
 * Pantalla de aviso del portal, sin datos de la solicitud: enlace inválido, acceso
 * vencido, salida del portal o error al cargar.
 */
export function PortalNotice({ title, children, action, role = "alert" }: PortalNoticeProps) {
  return (
    <main className="bg-bg-canvas grid min-h-screen place-items-center px-4 py-10">
      <div className="bg-bg-surface border-border-default grid w-full max-w-md gap-4 rounded-xl border px-5 py-8 text-center">
        <span className="text-text-primary inline-flex items-center justify-center gap-2 text-lg font-semibold">
          <PortalLogo />
          Umbral
        </span>
        <div role={role} className="grid gap-2">
          <h1 className="m-0 text-2xl font-semibold">{title}</h1>
          {children && <div className="text-text-secondary grid gap-1 text-md">{children}</div>}
        </div>
        {action && <div className="grid">{action}</div>}
      </div>
    </main>
  );
}

/** `401` en el portal: no se muestra nada de la solicitud. */
export function AccessExpiredScreen() {
  return (
    <PortalNotice title="Tu acceso venció">
      <p className="m-0">Pídele un enlace nuevo a tu asesor.</p>
    </PortalNotice>
  );
}

export function LoggedOutScreen() {
  return (
    <PortalNotice title="Saliste del portal" role="status">
      <p className="m-0">Para volver a entrar, pídele un enlace nuevo a tu asesor.</p>
    </PortalNotice>
  );
}

/** Esqueleto del portal mientras se confirma la sesión. */
export function PortalSkeleton() {
  return (
    <div className="bg-bg-canvas min-h-screen" aria-busy="true">
      <div className="bg-bg-surface border-border-default h-[58px] border-b" />
      <div className="mx-auto grid max-w-[720px] gap-4 px-4 py-5">
        <span className="sr-only" role="status">
          Cargando…
        </span>
        <div className="bg-bg-muted h-8 w-48 animate-pulse rounded-md motion-reduce:animate-none" />
        <div className="bg-bg-muted h-4 w-72 max-w-full animate-pulse rounded-md motion-reduce:animate-none" />
        <div className="bg-bg-muted h-40 animate-pulse rounded-xl motion-reduce:animate-none" />
      </div>
    </div>
  );
}
