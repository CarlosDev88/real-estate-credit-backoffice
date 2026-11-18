import type { MetadataItem } from "@/features/applications/queries";

// Qué campos pide el formulario de respuesta según el tipo (API §20.2). Salen del
// `metadata` de cada valor del catálogo `filing_response_type` (`fields`, `required` y
// `reason_catalog`, que la API arma con sus reglas): ya no hay una tabla en el front. La
// API sigue validando y sus errores de campo van al campo.

/** Campos que dependen del tipo. `received_at` y `external_reference` van siempre. */
export const RESPONSE_FIELDS = [
  "reason_code",
  "public_message",
  "internal_comment",
  "observations",
  "approved_amount_cop",
  "approved_term_months",
  "valid_until",
  "disbursed_amount_cop",
] as const;
export type ResponseField = (typeof RESPONSE_FIELDS)[number];

export interface ResponseForm {
  /** En el orden en que se muestran (el de la API). */
  fields: readonly ResponseField[];
  required: readonly ResponseField[];
  /** Catálogo de `reason_code`, si el tipo lleva motivo. */
  reasonCatalog?: string;
}

/** Tipo sin `metadata` (o sin elegir): solo los campos comunes. */
const FALLBACK: ResponseForm = { fields: ["public_message", "internal_comment"], required: [] };

const isField = (value: unknown): value is ResponseField =>
  typeof value === "string" && (RESPONSE_FIELDS as readonly string[]).includes(value);

/** Lista de campos conocidos de un valor de `metadata`; lo que no se conoce se ignora. */
function fieldList(value: unknown): ResponseField[] {
  return Array.isArray(value) ? value.filter(isField) : [];
}

/** Formulario de un tipo a partir del `metadata` de su valor del catálogo. */
export function responseForm(
  type: string | null | undefined,
  catalog: readonly Pick<MetadataItem, "code" | "metadata">[],
): ResponseForm {
  const metadata = type ? catalog.find((item) => item.code === type)?.metadata : undefined;
  const fields = fieldList(metadata?.fields);
  if (!metadata || fields.length === 0) return FALLBACK;
  const reason = metadata.reason_catalog;
  return {
    fields,
    // Un obligatorio va siempre en `fields`; si no, no hay control donde pedirlo.
    required: fieldList(metadata.required).filter((f) => fields.includes(f)),
    ...(typeof reason === "string" && reason ? { reasonCatalog: reason } : {}),
  };
}
