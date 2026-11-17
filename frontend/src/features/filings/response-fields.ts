// Qué campos pide el formulario de respuesta según el tipo (API §20.2). Es una regla de
// pantalla, no de negocio: la API sigue validando y sus errores de campo van al campo. Un
// tipo nuevo del catálogo que no esté aquí muestra los campos comunes y deja validar a la API.

/** Campos que dependen del tipo. `received_at` y `external_reference` van siempre. */
export type ResponseField =
  | "reason_code"
  | "public_message"
  | "internal_comment"
  | "observations"
  | "approved_amount_cop"
  | "approved_term_months"
  | "valid_until"
  | "disbursed_amount_cop";

export interface ResponseForm {
  /** En el orden en que se muestran. */
  fields: readonly ResponseField[];
  required: readonly ResponseField[];
  /** Catálogo de `reason_code`, si el tipo lleva motivo. */
  reasonCatalog?: string;
}

const NOTES: readonly ResponseField[] = ["public_message", "internal_comment"];

export const RESPONSE_FORMS: Readonly<Record<string, ResponseForm>> = {
  RECEIVED: { fields: NOTES, required: [] },
  IN_ANALYSIS: { fields: NOTES, required: [] },
  RETURNED: {
    fields: ["reason_code", "public_message", "observations", "internal_comment"],
    required: ["reason_code", "public_message", "observations"],
    reasonCatalog: "filing_return_reason",
  },
  APPROVED: {
    fields: [
      "approved_amount_cop",
      "approved_term_months",
      "valid_until",
      "public_message",
      "internal_comment",
    ],
    required: ["approved_amount_cop", "approved_term_months", "public_message"],
  },
  REJECTED: {
    fields: ["reason_code", "public_message", "internal_comment"],
    required: ["reason_code", "public_message"],
    reasonCatalog: "filing_rejection_reason",
  },
  DISBURSED: {
    fields: ["disbursed_amount_cop", "public_message", "internal_comment"],
    required: ["disbursed_amount_cop"],
  },
  OTHER: { fields: ["internal_comment", "public_message"], required: ["internal_comment"] },
};

/** Tipo sin regla conocida (o sin elegir): solo los campos comunes. */
const FALLBACK: ResponseForm = { fields: NOTES, required: [] };

export function responseForm(type: string | null | undefined): ResponseForm {
  return (type && RESPONSE_FORMS[type]) || FALLBACK;
}
