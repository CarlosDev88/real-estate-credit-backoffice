import type { Tone } from "@design/status-tones";

// Estados de usuarios e invitaciones. Son los `enum` cerrados del contrato
// (`GET /users?status=` y `GET /invitations?status=`); la API no manda su etiqueta
// (`status_label`) ni hay catálogo, así que el texto copia el de los `TextChoices` del
// backend (`UserStatus`, `InvitationStatus`). Brecha anotada en la spec (F6): cuando la API
// mande `status_label`, este archivo se queda solo con el orden.
// Tampoco están en `status-tones`: el tono va directo con `ToneBadge` (anotado).

export interface StatusOption {
  value: string;
  label: string;
  tone: Tone;
}

export const USER_STATUSES: readonly StatusOption[] = [
  { value: "ACTIVE", label: "Activo", tone: "success" },
  { value: "PENDING", label: "Pendiente de definir contraseña", tone: "warning" },
  { value: "INACTIVE", label: "Inactivo", tone: "neutral" },
];

export const INVITATION_STATUSES: readonly StatusOption[] = [
  { value: "PENDING", label: "Pendiente", tone: "warning" },
  { value: "ACCEPTED", label: "Aceptada", tone: "success" },
  { value: "EXPIRED", label: "Vencida", tone: "neutral" },
  { value: "REVOKED", label: "Revocada", tone: "neutral" },
];

/** Etiqueta y tono de un código; uno desconocido se muestra tal cual y en neutro. */
export function statusOf(options: readonly StatusOption[], code: string): StatusOption {
  return options.find((o) => o.value === code) ?? { value: code, label: code, tone: "neutral" };
}

/**
 * Rol de constructora: el contrato lo nombra (`POST /invitations`, `PUT /users/{id}/roles`)
 * porque exige `partner_id` y no se combina con otros roles.
 */
export const PARTNER_ROLE = "CONSTRUCTION_PARTNER";
