import { ToneBadge } from "@/components/ui/status-badge";

// Estado de constructoras y membresías (`PartnerStatusEnum`: ACTIVE, INACTIVE). La API no
// manda etiqueta ni hay catálogo: el texto copia el `TextChoices` del backend
// (`PartnerStatus`). No están en `status-tones`: `ToneBadge` con tono neutro (spec F6).
// Brecha anotada: exponer `status_label`.

export const PARTNER_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Activo",
  INACTIVE: "Inactivo",
};

export function partnerStatusLabel(code: string): string {
  return PARTNER_STATUS_LABELS[code] ?? code;
}

export function PartnerStatusBadge({ status }: { status: string }) {
  return <ToneBadge tone="neutral">{partnerStatusLabel(status)}</ToneBadge>;
}
