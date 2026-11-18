import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  /** Acción que destraba la vista (por ejemplo, "Limpiar filtros"). */
  action?: ReactNode;
  /**
   * `md` (por defecto): una lista o una pestaña vacías, con aire alrededor. `sm`: dentro de
   * una tarjeta o un tablero, con menos alto (24 px arriba y abajo, ícono de 24 px).
   */
  size?: "md" | "sm";
  className?: string;
}

const SIZES = {
  md: { box: "gap-2 px-4 py-12", icon: "[&_svg]:size-8" },
  sm: { box: "gap-1 px-3 py-6", icon: "[&_svg]:size-6" },
} as const;

/** Estado vacío (mockup `solicitudes.html`: "No hay solicitudes con estos filtros"). */
export function EmptyState({
  title,
  description,
  icon,
  action,
  size = "md",
  className = "",
}: EmptyStateProps) {
  const look = SIZES[size];
  return (
    <div
      className={`text-text-secondary grid justify-items-center text-center ${look.box} ${className}`}
    >
      {icon && (
        <div aria-hidden="true" className={`text-text-tertiary ${look.icon}`}>
          {icon}
        </div>
      )}
      <p className="text-text-primary m-0 font-semibold">{title}</p>
      {description && <p className="text-text-tertiary m-0 max-w-md text-sm">{description}</p>}
      {action && <div className={size === "sm" ? "mt-1" : "mt-2"}>{action}</div>}
    </div>
  );
}
