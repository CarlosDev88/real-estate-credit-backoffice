"use client";

import { App, Button } from "antd";
import { useMemo } from "react";
import type { ReactNode } from "react";

export type ToastTone = "success" | "info" | "warning" | "danger";

export interface ToastOptions {
  tone?: ToastTone;
  title: ReactNode;
  message?: ReactNode;
  action?: { label: string; onClick: () => void };
  /** Segundos; `false` lo deja hasta que se cierre. Por defecto: 5 s, y los errores se quedan. */
  duration?: number | false;
}

export interface Toast {
  show: (options: ToastOptions) => void;
  success: (options: Omit<ToastOptions, "tone">) => void;
  info: (options: Omit<ToastOptions, "tone">) => void;
  warning: (options: Omit<ToastOptions, "tone">) => void;
  error: (options: Omit<ToastOptions, "tone">) => void;
}

const METHOD = { success: "success", info: "info", warning: "warning", danger: "error" } as const;

let sequence = 0;

/**
 * Toasts con las reglas del design system: éxito, información y advertencia se
 * cierran a los 5 s (con pausa al pasar el mouse); los errores se quedan hasta
 * cerrarlos. Máximo 3 a la vez (configurado en `AntdProvider`).
 */
export function useToast(): Toast {
  const { notification } = App.useApp();

  return useMemo(() => {
    const show = ({ tone = "info", title, message, action, duration }: ToastOptions) => {
      const key = `um-toast-${++sequence}`;
      const resolved = duration ?? (tone === "danger" ? false : 5);
      notification[METHOD[tone]]({
        key,
        title,
        description: message,
        duration: resolved,
        showProgress: resolved !== false,
        pauseOnHover: true,
        role: tone === "danger" ? "alert" : "status",
        className: `um-toast um-toast--${tone}`,
        closable: { "aria-label": "Cerrar aviso" },
        actions: action ? (
          <Button
            size="small"
            onClick={() => {
              action.onClick();
              notification.destroy(key);
            }}
          >
            {action.label}
          </Button>
        ) : undefined,
      });
    };
    return {
      show,
      success: (o) => show({ ...o, tone: "success" }),
      info: (o) => show({ ...o, tone: "info" }),
      warning: (o) => show({ ...o, tone: "warning" }),
      error: (o) => show({ ...o, tone: "danger" }),
    };
  }, [notification]);
}
