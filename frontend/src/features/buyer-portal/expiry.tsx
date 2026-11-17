"use client";

import { useEffect, useState } from "react";

import { usePortal } from "@/features/buyer-portal/portal-context";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/** "N horas" (o "N minutos" en la última hora) hasta `expiresAt`; `null` si ya venció. */
export function remainingText(expiresAt: string, now: number): string | null {
  const left = Date.parse(expiresAt) - now;
  if (!Number.isFinite(left) || left <= 0) return null;
  if (left < HOUR) {
    const minutes = Math.max(1, Math.ceil(left / MINUTE));
    return `${minutes} ${minutes === 1 ? "minuto" : "minutos"}`;
  }
  const hours = Math.floor(left / HOUR);
  return `${hours} ${hours === 1 ? "hora" : "horas"}`;
}

/** La hora actual, actualizada cada minuto. */
export function useMinuteClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), MINUTE);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function ClockIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      width={16}
      height={16}
      aria-hidden="true"
      className="mt-0.5 flex-none"
    >
      <path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm1 4v5.4l3.3 2-1 1.7L9 11.5V5h2Z" />
    </svg>
  );
}

/** "Tu acceso vence en N horas…", desde `session.expires_at` (mockup `portal.html`). */
export function ExpiryNotice({ className = "" }: { className?: string }) {
  const { session } = usePortal();
  const now = useMinuteClock();
  const left = remainingText(session.session.expires_at, now);
  if (!left) return null;
  return (
    <p className={`m-0 flex items-start gap-2 text-sm ${className}`}>
      <ClockIcon />
      <span>
        Tu acceso vence en <b>{left}</b>. Si se vence, pide un enlace nuevo a tu asesor.
      </span>
    </p>
  );
}
