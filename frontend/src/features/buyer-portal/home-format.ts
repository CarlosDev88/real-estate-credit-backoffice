// Textos derivados del detalle del comprador. Sin listas de negocio: solo formato.
import type { components } from "@/lib/api/schema";

type BankRef = components["schemas"]["BankRef"];

/** Primer nombre para el saludo ("Hola, Sofía"). */
export function firstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0] ?? displayName;
}

/** Nombre corto del banco si lo tiene; si no, el nombre. */
export function bankName(bank: BankRef): string {
  return bank.short_name || bank.name;
}

/** Etiqueta de catálogo dentro de una frase: "Vivienda nueva" → "vivienda nueva". */
export function inSentence(label: string): string {
  return label.charAt(0).toLocaleLowerCase("es-CO") + label.slice(1);
}

/** Plazo: "20 años" si son años completos; si no, "18 meses". */
export function formatTerm(months: number | null | undefined): string | null {
  if (!months || months <= 0) return null;
  if (months % 12 === 0) {
    const years = months / 12;
    return `${years} ${years === 1 ? "año" : "años"}`;
  }
  return `${months} ${months === 1 ? "mes" : "meses"}`;
}

/**
 * Enlace de WhatsApp (`https://wa.me/<dígitos>`). Un celular colombiano de 10 dígitos
 * que empieza por 3 lleva el indicativo 57. Sin dígitos, `null`.
 */
export function whatsappUrl(phone: string | null | undefined): string | null {
  const digits = (phone ?? "").replace(/\D/g, "");
  if (!digits) return null;
  const full = digits.length === 10 && digits.startsWith("3") ? `57${digits}` : digits;
  return `https://wa.me/${full}`;
}

/** "N te tocan a ti · M los está revisando tu asesor", sin las partes en cero. */
export function workloadText(mine: number, inReview: number): string | null {
  const parts: string[] = [];
  if (mine > 0) parts.push(`${mine} ${mine === 1 ? "te toca" : "te tocan"} a ti`);
  if (inReview > 0) {
    parts.push(`${inReview} ${inReview === 1 ? "lo está" : "los está"} revisando tu asesor`);
  }
  return parts.length ? parts.join(" · ") : null;
}
