"use client";

import { useMemo } from "react";

import { useBootstrap } from "@/features/applications/queries";
import { SCAN_CLEAN, SCAN_PENDING, type DocumentSlot } from "@/features/document-review/queries";
import { formatDateOnly } from "@/lib/format";

/**
 * Etiqueta del estado de un slot, del catálogo `document_status` del bootstrap. Cuando
 * la API traiga `status_label` en el slot (tarea de brechas), se usa ese.
 */
export function useSlotStatusLabel(): (code: string) => string {
  const bootstrap = useBootstrap();
  const items = bootstrap.data?.catalogs.document_status;
  return useMemo(() => {
    const map = new Map((items ?? []).map((item) => [item.code, item.label]));
    return (code: string) => map.get(code) ?? code;
  }, [items]);
}

export const SCAN_PENDING_TEXT = "Analizando el archivo…";
export const SCAN_FAILED_TEXT = "El archivo no pasó el análisis de seguridad";

/** Aviso del análisis antivirus: `null` si el archivo está limpio. */
export function scanMessage(scanStatus: string | null | undefined): string | null {
  if (!scanStatus || scanStatus === SCAN_CLEAN) return null;
  return scanStatus === SCAN_PENDING ? SCAN_PENDING_TEXT : SCAN_FAILED_TEXT;
}

/** El visor muestra imágenes directo; lo demás va por PDF.js. */
export function viewerKind(mimeType: string | null | undefined): "pdf" | "image" {
  return mimeType?.startsWith("image/") ? "image" : "pdf";
}

/** "vigencia de 30 días · vence 2 dic 2026", o `null` si el documento no vence. */
export function validityText(slot: DocumentSlot): string | null {
  const parts: string[] = [];
  if (slot.validity_days) {
    parts.push(
      slot.validity_days === 1 ? "vigencia de 1 día" : `vigencia de ${slot.validity_days} días`,
    );
  }
  const expires = formatDateOnly(slot.current_file?.expires_at);
  if (expires) parts.push(`vence ${expires}`);
  return parts.length ? parts.join(" · ") : null;
}

export interface SlotPermissions {
  review: boolean;
  waive: boolean;
  download: boolean;
}

/**
 * Qué se puede hacer con un slot (API §19.1):
 * - **Revisar** (aprobar o rechazar): sobre la versión vigente, con análisis limpio; también
 *   en un aprobado o rechazado, porque corregir es decidir otra vez. Exonerado, no.
 * - **Exonerar** (`documents.waive`): si `is_waivable`, salvo aprobado o ya exonerado.
 * - **Reabrir** (`documents.waive`): solo un exonerado (deshace la exoneración).
 * - **Ver**: con `documents.download` y análisis limpio.
 */
export function slotActions(slot: DocumentSlot, can: SlotPermissions) {
  const clean = slot.current_file?.scan_status === SCAN_CLEAN;
  const waived = slot.status === "WAIVED";
  return {
    view: can.download && clean,
    review: can.review && clean && !waived,
    waive: can.waive && slot.is_waivable && !waived && slot.status !== "APPROVED",
    reopen: can.waive && waived,
  };
}

/** Pendientes de decisión: cargados, con análisis limpio. */
export function isAwaitingReview(slot: DocumentSlot): boolean {
  return slot.status === "UPLOADED" && slot.current_file?.scan_status === SCAN_CLEAN;
}
