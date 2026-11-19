import { ToneBadge } from "@/components/ui/status-badge";

// Textos de tipos y requisitos documentales que la API no manda como etiqueta. Son los
// `enum` del contrato y copian sus `TextChoices` (brecha anotada: exponer `*_label`).
// Ninguno está en `status-tones`: `ToneBadge` neutro (spec F6).

/** `AllowedMimeTypesEnum`: el texto es el formato que reconoce cualquier persona. */
export const MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"] as const;
export type MimeType = (typeof MIME_TYPES)[number];
export const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "image/jpeg": "JPG",
  "image/png": "PNG",
};

export const HOLDER_SCOPES = ["PARTICIPANT", "APPLICATION"] as const;
export type HolderScope = (typeof HOLDER_SCOPES)[number];
export const HOLDER_SCOPE_LABELS: Record<string, string> = {
  PARTICIPANT: "Por participante",
  APPLICATION: "Una vez por solicitud",
};

export const PARTICIPANT_ROLES = ["PRIMARY", "CO_APPLICANT", "SOLIDARY_DEBTOR"] as const;
export type ParticipantRole = (typeof PARTICIPANT_ROLES)[number];
export const PARTICIPANT_ROLE_LABELS: Record<string, string> = {
  PRIMARY: "Titular",
  CO_APPLICANT: "Co-solicitante",
  SOLIDARY_DEBTOR: "Deudor solidario",
};

export const REQUIREMENT_STATUSES = ["DRAFT", "ACTIVE", "INACTIVE"] as const;
export const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Borrador",
  ACTIVE: "Activo",
  INACTIVE: "Inactivo",
};

export const labelIn = (labels: Record<string, string>, code: string | null | undefined) =>
  code ? (labels[code] ?? code) : "";

export function RequirementStatusBadge({ status }: { status: string }) {
  return <ToneBadge tone="neutral">{labelIn(REQUIREMENT_STATUS_LABELS, status)}</ToneBadge>;
}

/** "PDF, JPG" a partir de los tipos MIME. */
export const mimeText = (types: readonly string[]) =>
  types.map((type) => labelIn(MIME_LABELS, type)).join(", ");

export const MB = 1024 * 1024;
/** Tamaño máximo del contrato (`max_size_bytes` ≤ 10485760). */
export const MAX_SIZE_MB = 10;
