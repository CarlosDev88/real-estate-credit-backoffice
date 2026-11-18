"use client";

import { Drawer } from "antd";
import type { ReactNode, Ref } from "react";

import { useMediaQuery } from "@/lib/hooks/use-media-query";

// Mismo corte que el shell: en 860 px o menos el panel ocupa toda la pantalla.
const MOBILE_QUERY = "(max-width: 860px)";

interface SidePanelProps {
  open: boolean;
  onClose: () => void;
  /** Encima del título, en gris: de quién o de qué es ("Daniel Mejía · Titular"). */
  eyebrow?: ReactNode;
  /** Título (`h2`): el documento o la oportunidad que se revisa. */
  title: ReactNode;
  /**
   * Para enfocar el título al abrir o al pasar al siguiente (se anuncia y el foco queda
   * dentro del panel). Recibe un ref de callback.
   */
  titleRef?: Ref<HTMLHeadingElement>;
  /** Botones de abajo: cancelar, siguiente y la acción principal a la derecha. */
  footer?: ReactNode;
  /** Ancho en escritorio, en px. */
  width?: number;
  children: ReactNode;
}

/**
 * Panel lateral de revisión o de detalle (mockup `solicitud.html`, drawer de revisión):
 * se abre a la derecha sin dejar la vista; en móvil, a pantalla completa. Mantiene el foco
 * adentro, lo devuelve al cerrar y se vacía al cerrarse.
 */
export function SidePanel({
  open,
  onClose,
  eyebrow,
  title,
  titleRef,
  footer,
  width = 520,
  children,
}: SidePanelProps) {
  const mobile = useMediaQuery(MOBILE_QUERY);
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      size={mobile ? "100%" : width}
      closable={{ "aria-label": "Cerrar" }}
      destroyOnHidden
      title={
        // Mientras se cierra, el contenido puede quedar vacío: sin título, no hay `h2`.
        title ? (
          <div>
            {eyebrow && <div className="text-text-tertiary text-sm font-normal">{eyebrow}</div>}
            <h2 ref={titleRef} tabIndex={-1} className="m-0 text-lg font-semibold outline-none">
              {title}
            </h2>
          </div>
        ) : undefined
      }
      footer={footer}
    >
      {children}
    </Drawer>
  );
}
