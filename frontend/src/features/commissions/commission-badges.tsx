import type { Tone } from "@design/status-tones";

import { ToneBadge } from "@/components/ui/status-badge";
import { formatDateOnly, LOCALE } from "@/lib/format";

// Presentación de comisiones. Los textos de estado vienen de la API (`status_label`); aquí
// solo se decide el tono. `design/status-tones` no tiene comisiones todavía (candidato a
// sumarlas a `design/tokens`): un código desconocido cae en "neutral", como allá.

const SETTLEMENT_TONES: Record<string, Tone> = { ACTIVE: "success", VOIDED: "neutral" };
const SHARE_TONES: Record<string, Tone> = {
  PENDING: "warning",
  PAID: "success",
  VOIDED: "neutral",
};

/**
 * Nombres de los estados para los filtros. El contrato los trae en la descripción del
 * enum (`CommissionSettlementStatusEnum`, `CommissionShareStatusEnum`) y no hay catálogo
 * en `/metadata/bootstrap`; en las filas se usa siempre el `status_label` de la API.
 */
export const SETTLEMENT_STATUS_OPTIONS = [
  { value: "ACTIVE", label: "Vigente" },
  { value: "VOIDED", label: "Anulada" },
];
export const SHARE_STATUS_OPTIONS = [
  { value: "PENDING", label: "Pendiente de pago" },
  { value: "PAID", label: "Pagada" },
  { value: "VOIDED", label: "Anulada" },
];

export function SettlementStatusBadge({ code, label }: { code: string; label: string }) {
  return <ToneBadge tone={SETTLEMENT_TONES[code] ?? "neutral"}>{label}</ToneBadge>;
}

export function ShareStatusBadge({ code, label }: { code: string; label: string }) {
  return <ToneBadge tone={SHARE_TONES[code] ?? "neutral"}>{label}</ToneBadge>;
}

/** Marca de `needs_review`: la liquidación tiene algo que revisar a mano. */
export function ReviewBadge() {
  return <ToneBadge tone="warning">Revisión pendiente</ToneBadge>;
}

const NBSP = String.fromCharCode(0xa0);
const pctFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 4 });

/** Decimal de la API ("1.0000", "0.75", "70.0000") → "1 %", "0,75 %", "70 %". */
export function formatPct(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? `${pctFormat.format(n)}${NBSP}%` : null;
}

/** "1 ene 2026 – sin fin" o "1 ene 2026 – 1 jul 2026 (sin incluir)". */
export function validityLabel(from: string, until: string | null): string {
  const start = formatDateOnly(from) ?? from;
  if (!until) return `${start} – sin fin`;
  return `${start} – ${formatDateOnly(until) ?? until}`;
}
