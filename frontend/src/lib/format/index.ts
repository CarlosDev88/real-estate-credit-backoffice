// Formatos de presentación. Montos: enteros COP (API §2), nunca float.

/** Zona horaria de toda la app. Si algún día hace falta otra, se cambia aquí. */
export const TIME_ZONE = "America/Bogota";
export const LOCALE = "es-CO";

const NBSP = String.fromCharCode(0xa0); // espacio de no separación

const copFormat = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});
const integerFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

/** "$ 294.000.000". `null` devuelve `null` para que la vista decida qué mostrar. */
export function formatCOP(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return copFormat.format(Math.trunc(value));
}

/** "294.000.000" (sin símbolo; para el campo de monto). */
export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  return integerFormat.format(Math.trunc(value));
}

/** Solo los dígitos de un texto: "$ 294.000.000" → 294000000. Vacío → null. */
export function parseInteger(text: string | null | undefined): number | null {
  const digits = (text ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

/** "62 %" (entero, con espacio de no separación como en los mockups). */
export function formatPercent(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${Math.round(value)}${NBSP}%`;
}

const decimalFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });
const oneDecimalFormat = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** "70,2 %": porcentaje con un decimal (financiación sobre el valor del inmueble). */
export function formatPercentDecimal(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${oneDecimalFormat.format(value)}${NBSP}%`;
}

/** "850 KB", "1,2 MB" (base 1024). */
export function formatBytes(bytes: number | null | undefined): string | null {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${decimalFormat.format(bytes / (1024 * 1024))} MB`;
}

// ---------- fechas ----------

type Parts = Record<"year" | "month" | "day" | "hour" | "minute", number>;

const numericParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  hourCycle: "h23",
});

function zoned(date: Date): Parts {
  const out = { year: 0, month: 0, day: 0, hour: 0, minute: 0 };
  for (const p of numericParts.formatToParts(date)) {
    if (p.type in out) out[p.type as keyof Parts] = Number(p.value);
  }
  return out;
}

const monthShort = new Intl.DateTimeFormat(LOCALE, { timeZone: "UTC", month: "short" });

function shortMonth(month: number): string {
  // "nov" (sin punto, como en los mockups), independiente del ICU del navegador.
  return monthShort.format(new Date(Date.UTC(2000, month - 1, 1))).replace(/\.$/, "");
}

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "24 ago 2026" en la zona horaria de la app. */
export function formatDate(value: string | Date | null | undefined): string | null {
  const date = value ? toDate(value) : null;
  if (!date) return null;
  const p = zoned(date);
  return `${p.day} ${shortMonth(p.month)} ${p.year}`;
}

/**
 * "24 ago 2026, 3:45 p. m." (12 h, como es-CO) en la zona horaria de la app. Los espacios
 * de la hora son de no separación, para que "3:45 p. m." no se parta en dos líneas.
 */
export function formatDateTime(value: string | Date | null | undefined): string | null {
  const date = value ? toDate(value) : null;
  if (!date) return null;
  const p = zoned(date);
  const hour = p.hour % 12 || 12;
  const period = p.hour < 12 ? `a.${NBSP}m.` : `p.${NBSP}m.`;
  const time = `${hour}:${String(p.minute).padStart(2, "0")}${NBSP}${period}`;
  return `${p.day} ${shortMonth(p.month)} ${p.year}, ${time}`;
}

/** Fecha sin hora ("2026-08-24"): se muestra tal cual, sin zona horaria. */
export function formatDateOnly(value: string | null | undefined): string | null {
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null;
  if (!match) return null;
  return `${Number(match[3])} ${shortMonth(Number(match[2]))} ${match[1]}`;
}

function dayNumber(p: Parts): number {
  return Date.UTC(p.year, p.month - 1, p.day) / 86_400_000;
}

/**
 * Fecha relativa (mockup `solicitudes.html`), calculada en la zona horaria de la app:
 * "Hace un momento", "Hace N min", "Hace N h", "Ayer", "Hace N días" (hasta 3) y
 * después "8 nov" ("8 nov 2025" si es de otro año).
 */
export function formatRelative(
  value: string | Date | null | undefined,
  now: Date = new Date(),
): string | null {
  const date = value ? toDate(value) : null;
  if (!date) return null;
  const minutes = Math.floor((now.getTime() - date.getTime()) / 60_000);
  const then = zoned(date);
  const today = zoned(now);
  const days = dayNumber(today) - dayNumber(then);

  if (minutes < 1) return "Hace un momento";
  if (minutes < 60) return `Hace ${minutes} min`;
  if (days === 0) return `Hace ${Math.floor(minutes / 60)} h`;
  if (days === 1) return "Ayer";
  if (days <= 3) return `Hace ${days} días`;
  return then.year === today.year
    ? `${then.day} ${shortMonth(then.month)}`
    : `${then.day} ${shortMonth(then.month)} ${then.year}`;
}
