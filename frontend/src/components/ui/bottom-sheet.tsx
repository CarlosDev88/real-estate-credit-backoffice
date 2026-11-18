"use client";

import { Drawer } from "antd";
import type { ReactNode } from "react";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Nombre del botón de cerrar ("Cerrar filtros"). */
  closeLabel?: string;
  /** Botones de abajo (por ejemplo, "Limpiar" y "Ver resultados"), grandes y a todo el ancho. */
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * Hoja inferior para móvil: filtros, carga de un archivo, una acción corta. Mantiene el
 * foco adentro y lo devuelve al cerrar (drawer de Ant Design), respeta la zona segura de
 * abajo y se vacía al cerrar.
 */
export function BottomSheet({
  open,
  onClose,
  title,
  closeLabel = "Cerrar",
  footer,
  children,
}: BottomSheetProps) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="bottom"
      size="auto"
      title={title}
      closable={{ "aria-label": closeLabel }}
      footer={footer}
      destroyOnHidden
      styles={{
        body: { paddingTop: 8, paddingBottom: "calc(24px + env(safe-area-inset-bottom))" },
      }}
    >
      {children}
    </Drawer>
  );
}
