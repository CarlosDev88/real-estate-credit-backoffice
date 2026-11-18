import { createContext, useContext, useId } from "react";
import type { ReactNode } from "react";

interface CardProps {
  /** Título de la tarjeta (`h2`); también le da el nombre accesible a la sección. */
  title?: ReactNode;
  /** A la derecha del título: un total, un botón de texto o un enlace. */
  action?: ReactNode;
  children: ReactNode;
  /** `portal`: tarjeta del portal del comprador (radio `xl` y título de 20 px). */
  variant?: "backoffice" | "portal";
  /** `id` de la sección, por ejemplo para enlazarla con `#`. */
  id?: string;
  className?: string;
}

/**
 * Tarjeta en el flujo de la página (mockup `solicitud.html`, `.card`): borde y fondo, sin
 * sombra. Es una `section` con nombre (el título), así que se encuentra por su rol.
 */
export function Card({
  title,
  action,
  children,
  variant = "backoffice",
  id,
  className = "",
}: CardProps) {
  const generated = useId();
  const titleId = `${id ?? generated}-title`;
  const portal = variant === "portal";
  return (
    <section
      id={id}
      aria-labelledby={title ? titleId : undefined}
      className={`bg-bg-surface border-border-default scroll-mt-20 border ${
        portal ? "grid gap-4 rounded-xl px-4 py-5" : "rounded-lg"
      } ${className}`}
    >
      {(title || action) && (
        <div
          className={`flex flex-wrap gap-2 ${portal ? "items-baseline" : "items-center px-5 pt-4"}`}
        >
          {title && (
            <h2
              id={titleId}
              className={`m-0 flex-1 font-semibold ${portal ? "text-xl" : "text-lg leading-snug"}`}
            >
              {title}
            </h2>
          )}
          {action && <div className="ml-auto flex items-center gap-2">{action}</div>}
        </div>
      )}
      {/* En el portal, los bloques del contenido van directo en la grilla (con su espacio). */}
      {portal ? (
        children
      ) : (
        <div className={title || action ? "px-5 pt-4 pb-5" : "p-5"}>{children}</div>
      )}
    </section>
  );
}

type DataListLayout = "grid" | "inline";
const LayoutContext = createContext<DataListLayout>("grid");

interface DataListProps {
  children: ReactNode;
  /**
   * `grid`: etiqueta arriba y valor abajo, en columnas (fichas de cliente y de radicación).
   * `inline`: etiqueta a la izquierda y valor a la derecha (mockup `.dl` del expediente).
   */
  layout?: DataListLayout;
  /** Columnas del `grid` en pantallas anchas (una sola en móvil). */
  columns?: 1 | 2 | 3;
  className?: string;
}

const GRID_COLUMNS = {
  1: "",
  2: "min-[600px]:grid-cols-2",
  3: "min-[600px]:grid-cols-2 min-[1100px]:grid-cols-3",
} as const;

/** Lista de datos (`dl`) de una ficha. Cada dato es un `Datum`. */
export function DataList({
  children,
  layout = "grid",
  columns = 2,
  className = "",
}: DataListProps) {
  const look =
    layout === "inline"
      ? "grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-x-4 gap-y-2 text-sm min-[861px]:grid-cols-[minmax(140px,220px)_1fr]"
      : `gap-4 ${GRID_COLUMNS[columns]}`;
  return (
    <LayoutContext.Provider value={layout}>
      <dl className={`m-0 grid ${look} ${className}`}>{children}</dl>
    </LayoutContext.Provider>
  );
}

const DASH = <span className="text-text-tertiary font-normal">—</span>;

/** Un dato: etiqueta y valor. Sin valor (`null`, `undefined` o texto vacío) muestra "—". */
export function Datum({ label, children }: { label: ReactNode; children?: ReactNode }) {
  const layout = useContext(LayoutContext);
  const empty = children === null || children === undefined || children === "";
  const value = empty ? DASH : children;
  if (layout === "inline") {
    return (
      <div className="contents">
        <dt className="text-text-tertiary">{label}</dt>
        <dd className="m-0 font-medium break-words">{value}</dd>
      </div>
    );
  }
  return (
    <div className="grid min-w-0 gap-0.5">
      <dt className="text-text-tertiary text-xs font-medium">{label}</dt>
      <dd className="m-0 break-words">{value}</dd>
    </div>
  );
}
