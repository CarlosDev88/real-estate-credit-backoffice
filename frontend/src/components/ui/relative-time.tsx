"use client";

import { useSyncExternalStore } from "react";

import { formatDate, formatDateTime, formatRelative } from "@/lib/format";

// Reloj compartido que avanza cada minuto mientras haya alguien suscrito.
let now = Date.now();
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (!timer) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((l) => l());
    }, 60_000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/**
 * Fecha relativa ("Hace 12 min") que se actualiza cada minuto. El HTML del servidor y
 * la primera pasada del cliente muestran la fecha absoluta (igual en los dos, por la
 * zona horaria fija), así que no hay diferencias de hidratación; luego pasa a relativa.
 */
export function RelativeTime({ value, className = "" }: { value: string; className?: string }) {
  const current = useSyncExternalStore(
    subscribe,
    () => now,
    () => null,
  );
  const text = current === null ? formatDate(value) : formatRelative(value, new Date(current));
  if (!text) return null;
  return (
    <time dateTime={value} title={formatDateTime(value) ?? undefined} className={className}>
      {text}
    </time>
  );
}
