import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  /** Acción que destraba la vista (por ejemplo, "Limpiar filtros"). */
  action?: ReactNode;
  className?: string;
}

/** Estado vacío (mockup `solicitudes.html`: "No hay solicitudes con estos filtros"). */
export function EmptyState({ title, description, icon, action, className = "" }: EmptyStateProps) {
  return (
    <div
      className={`text-text-secondary grid justify-items-center gap-2 px-4 py-12 text-center ${className}`}
    >
      {icon && (
        <div aria-hidden="true" className="text-text-tertiary [&_svg]:size-8">
          {icon}
        </div>
      )}
      <p className="text-text-primary m-0 font-semibold">{title}</p>
      {description && <p className="text-text-tertiary m-0 max-w-md text-sm">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
