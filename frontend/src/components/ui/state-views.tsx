"use client";

import { Alert, Button } from "antd";
import type { ReactNode } from "react";

// Estados de una vista que depende de la API: cargando y error con "Reintentar". El vacío
// es `EmptyState`. Los tres, en el patrón "Estados vacío, cargando y error".

interface LoadingStateProps {
  /** Lo que se anuncia al lector de pantalla ("Cargando documentos"). */
  label?: string;
  /**
   * Altura de cada bloque del esqueleto, en px (uno por tarjeta que viene en camino).
   * Sin bloques (`[]`), se muestra el `label` como texto: para una sección pequeña.
   */
  blocks?: number[];
  /** `portal`: bloques con el radio de las tarjetas del portal (`xl`). */
  variant?: "backoffice" | "portal";
  className?: string;
}

/** Cargando: esqueleto con la forma de lo que viene, o una línea de texto. */
export function LoadingState({
  label = "Cargando…",
  blocks = [96],
  variant = "backoffice",
  className = "",
}: LoadingStateProps) {
  if (blocks.length === 0) {
    return (
      <p role="status" className={`text-text-tertiary m-0 text-sm ${className}`}>
        {label}
      </p>
    );
  }
  const radius = variant === "portal" ? "rounded-xl" : "rounded-lg";
  return (
    <div aria-busy="true" className={`grid gap-3 ${className}`}>
      <span className="sr-only" role="status">
        {label}
      </span>
      {blocks.map((height, index) => (
        <div
          key={index}
          className={`bg-bg-muted animate-pulse motion-reduce:animate-none ${radius}`}
          style={{ height }}
        />
      ))}
    </div>
  );
}

interface ErrorStateProps {
  /** Qué no se pudo cargar: "No pudimos cargar los documentos". */
  title: string;
  /** Detalle (el mensaje de la API). */
  message?: ReactNode;
  onRetry: () => void;
  /** Mientras se reintenta, el botón muestra que está trabajando. */
  retrying?: boolean;
  /**
   * - `inline`: una línea con un botón pequeño, dentro de una tarjeta o una sección.
   * - `banner`: alerta de error a todo el ancho del contenido (una pestaña, una lista).
   * - `page`: título, detalle y botón, cuando falla la vista entera (portal y pantallas).
   */
  variant?: "inline" | "banner" | "page";
  /** En `page`, el título puede ser el `h1` de la pantalla. */
  titleAs?: "p" | "h1" | "h2";
  className?: string;
}

/** Error al cargar, siempre con "Reintentar" y con `role="alert"`. */
export function ErrorState({
  title,
  message,
  onRetry,
  retrying = false,
  variant = "banner",
  titleAs = "p",
  className = "",
}: ErrorStateProps) {
  const retry = (size: "small" | "middle") => (
    <Button size={size} loading={retrying} onClick={onRetry}>
      Reintentar
    </Button>
  );

  if (variant === "inline") {
    return (
      <div role="alert" className={`flex flex-wrap items-center gap-2 text-sm ${className}`}>
        <span className="text-text-tertiary">{title}</span>
        {retry("small")}
      </div>
    );
  }

  if (variant === "banner") {
    return (
      <Alert
        type="error"
        showIcon
        title={title}
        description={message}
        action={retry("small")}
        className={className}
      />
    );
  }

  const Title = titleAs;
  return (
    <div role="alert" className={`grid justify-items-start gap-2 ${className}`}>
      <Title className={`m-0 font-semibold ${titleAs === "h1" ? "text-xl" : ""}`}>{title}</Title>
      {message && <p className="text-text-secondary m-0">{message}</p>}
      {retry("middle")}
    </div>
  );
}
