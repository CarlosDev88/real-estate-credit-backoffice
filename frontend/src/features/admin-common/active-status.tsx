import { ToneBadge } from "@/components/ui/status-badge";

// Estado activo/inactivo de constructoras, membresías, bancos y productos (el contrato usa
// el mismo `enum` `PartnerStatusEnum`: ACTIVE, INACTIVE). La API no manda etiqueta ni hay
// catálogo: el texto copia el `TextChoices` del backend. No está en `status-tones`:
// `ToneBadge` con tono neutro (spec F6). Brecha anotada: exponer `status_label`.

export const ACTIVE_STATUS_CODES = ["ACTIVE", "INACTIVE"] as const;
export type ActiveStatusCode = (typeof ACTIVE_STATUS_CODES)[number];

export const ACTIVE_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Activo",
  INACTIVE: "Inactivo",
};

export function activeStatusLabel(code: string): string {
  return ACTIVE_STATUS_LABELS[code] ?? code;
}

export function ActiveStatusBadge({ status }: { status: string }) {
  return <ToneBadge tone="neutral">{activeStatusLabel(status)}</ToneBadge>;
}
