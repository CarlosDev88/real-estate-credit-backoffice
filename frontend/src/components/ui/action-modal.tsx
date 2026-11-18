"use client";

import { Modal } from "antd";
import type { FormEvent, ReactNode } from "react";

interface ActionModalProps {
  open: boolean;
  title: ReactNode;
  /** Qué pasa al confirmar, en una o dos frases, antes de los campos. */
  description?: ReactNode;
  /** Verbo de la acción: "Exonerar", "Registrar radicación". Nunca "Aceptar". */
  okText: string;
  cancelText?: string;
  /** Acción destructiva (rechazar, revocar, cerrar la solicitud): botón `danger`. */
  danger?: boolean;
  /** La escritura está en curso: el botón principal muestra que trabaja. */
  loading?: boolean;
  /** Falta algo para poder confirmar. Mejor explicar por qué en `description`. */
  okDisabled?: boolean;
  /**
   * Confirma. Recibe el evento del formulario cuando se envía con Enter, así que sirve
   * directo el `handleSubmit(...)` de React Hook Form.
   */
  onSubmit: (event?: FormEvent<HTMLFormElement>) => unknown;
  onCancel: () => void;
  /** Campos del formulario (con `FormField`). Sin campos, es una confirmación simple. */
  children?: ReactNode;
  width?: number;
}

/**
 * Modal de una acción: título, qué va a pasar, los campos y dos botones (cancelar y el
 * verbo de la acción). Se vacía al cerrar. Los errores de los campos van debajo de cada
 * uno (`FormField`); los demás, al toast global.
 */
export function ActionModal({
  open,
  title,
  description,
  okText,
  cancelText = "Cancelar",
  danger = false,
  loading = false,
  okDisabled = false,
  onSubmit,
  onCancel,
  children,
  width,
}: ActionModalProps) {
  return (
    <Modal
      open={open}
      title={title}
      okText={okText}
      cancelText={cancelText}
      okButtonProps={{ danger, disabled: okDisabled }}
      confirmLoading={loading}
      onOk={() => void onSubmit()}
      onCancel={onCancel}
      width={width}
      destroyOnHidden
    >
      <form
        noValidate
        className="grid gap-4 pt-2"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit(event);
        }}
      >
        {description && <p className="text-text-secondary m-0 text-sm">{description}</p>}
        {children}
      </form>
    </Modal>
  );
}
