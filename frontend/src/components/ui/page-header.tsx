import Link from "next/link";
import type { ReactNode } from "react";

import { BackIcon } from "@/components/ui/icons";

interface BackLinkProps {
  href: string;
  children: ReactNode;
  /**
   * `touch`: enlace del portal del comprador, con 44 px de alto para el dedo y el color de
   * enlace. `default`: el del backoffice, discreto, en `text.secondary`.
   */
  size?: "default" | "touch";
  className?: string;
}

/** "Volver a solicitudes": enlace con flecha a la vista de arriba. */
export function BackLink({ href, children, size = "default", className = "" }: BackLinkProps) {
  const look =
    size === "touch"
      ? "text-text-link text-md min-h-11 font-medium"
      : "text-text-secondary hover:text-text-primary text-sm no-underline";
  return (
    <Link href={href} className={`inline-flex w-fit items-center gap-1 ${look} ${className}`}>
      <BackIcon />
      {children}
    </Link>
  );
}

interface PageHeaderProps {
  /** Título de la página (el único `h1`). */
  title: ReactNode;
  /** Una línea debajo del título: qué es la vista o su estado. */
  description?: ReactNode;
  /** Enlace "volver" sobre el título. */
  back?: { href: string; label: string };
  /** Acciones de la vista, a la derecha (abajo en móvil). Una sola principal. */
  actions?: ReactNode;
  /** `portal`: tamaños del portal del comprador (enlace táctil y descripción de 14 px). */
  variant?: "backoffice" | "portal";
  className?: string;
}

/**
 * Encabezado de página: volver, título, descripción y acciones. Las migas del backoffice
 * van en la barra superior del `AppShell` (`useShellTrail`), no aquí.
 */
export function PageHeader({
  title,
  description,
  back,
  actions,
  variant = "backoffice",
  className = "",
}: PageHeaderProps) {
  const portal = variant === "portal";
  return (
    <div className={`grid gap-2 ${className}`}>
      {back && (
        <BackLink href={back.href} size={portal ? "touch" : "default"}>
          {back.label}
        </BackLink>
      )}
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1">
          <h1 className="m-0 text-3xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className={`text-text-secondary mt-1 mb-0 ${portal ? "text-md" : ""}`}>
              {description}
            </p>
          )}
        </div>
        {actions && (
          // El portal pasa a dos columnas en 900 px; el backoffice tiene más ancho útil.
          <div
            className={`flex w-full flex-wrap gap-2 ${portal ? "min-[900px]:w-auto" : "min-[600px]:w-auto"}`}
          >
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
