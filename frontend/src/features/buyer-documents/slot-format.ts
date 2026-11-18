// Presentación de los documentos del comprador. Sin estados escritos: todo sale de la API.
import type { BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { formatBytes } from "@/lib/format";

/** Nombre corto de un tipo MIME ("application/pdf" → "PDF", "image/jpeg" → "JPG"). */
export function typeLabel(mime: string): string {
  const sub = mime.split("/")[1] ?? mime;
  return (sub === "jpeg" ? "jpg" : sub).toUpperCase();
}

/** "PDF, JPG o PNG". */
export function listLabels(labels: string[]): string {
  return labels.length <= 1
    ? (labels[0] ?? "")
    : `${labels.slice(0, -1).join(", ")} o ${labels[labels.length - 1]}`;
}

/** "PDF, JPG o PNG, de hasta 10 MB.", desde `allowed_mime_types` y `max_size_bytes`. */
export function requirementsText(
  slot: Pick<BuyerDocumentSlot, "allowed_mime_types" | "max_size_bytes">,
) {
  const types = [...new Set(slot.allowed_mime_types.map(typeLabel))];
  const size = formatBytes(slot.max_size_bytes);
  if (types.length && size) return `${listLabels(types)}, de hasta ${size}.`;
  if (types.length) return `${listLabels(types)}.`;
  return size ? `De hasta ${size}.` : null;
}

/** Cómo abre el visor un archivo: las imágenes directo y lo demás con PDF.js. */
export function viewerKind(mime: string | null | undefined): "pdf" | "image" {
  return mime?.startsWith("image/") ? "image" : "pdf";
}

/** Los que necesitan acción primero; el resto en el orden de la API (orden estable). */
export function sortSlots(slots: BuyerDocumentSlot[]): BuyerDocumentSlot[] {
  return [...slots].sort((a, b) => Number(b.needs_action) - Number(a.needs_action));
}

export interface StatusTab {
  key: string;
  label: string;
  count: number;
}

/**
 * Una pestaña por `public_status` presente, con su etiqueta y su número, en el orden en
 * que aparece en la lista ordenada (con `needs_action` primero).
 */
export function statusTabs(sorted: BuyerDocumentSlot[]): StatusTab[] {
  const tabs = new Map<string, StatusTab>();
  for (const slot of sorted) {
    const tab = tabs.get(slot.public_status);
    if (tab) tab.count += 1;
    else {
      tabs.set(slot.public_status, {
        key: slot.public_status,
        label: slot.public_status_label,
        count: 1,
      });
    }
  }
  return [...tabs.values()];
}

export interface SlotGroup {
  key: string;
  /** Nombre del participante; `null` para los documentos de la solicitud. */
  name: string | null;
  roleLabel: string | null;
  slots: BuyerDocumentSlot[];
}

/** Agrupa por participante en el orden de aparición. */
export function groupByParticipant(slots: BuyerDocumentSlot[]): SlotGroup[] {
  const groups = new Map<string, SlotGroup>();
  for (const slot of slots) {
    const key = slot.participant?.id ?? "application";
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        name: slot.participant?.full_name ?? null,
        roleLabel: slot.participant?.role_label ?? null,
        slots: [],
      };
      groups.set(key, group);
    }
    group.slots.push(slot);
  }
  return [...groups.values()];
}

/** "Te faltan N documentos. Tu asesor revisa los demás." */
export function summaryText(pending: number): string {
  if (pending === 0) return "No te falta ningún documento. Tu asesor revisa los demás.";
  return `Te ${pending === 1 ? "falta 1 documento" : `faltan ${pending} documentos`}. Tu asesor revisa los demás.`;
}
