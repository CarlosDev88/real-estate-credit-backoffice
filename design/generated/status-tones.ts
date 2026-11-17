// Generado por design/scripts/build-tokens.mjs desde design/tokens/tokens.json. No editar a mano.
// Tono visual por código de estado. Es presentación: un código desconocido cae en "neutral".

export type Tone = "neutral" | "info" | "accent" | "success" | "warning" | "danger";
export type StatusKind = "application" | "documentSlot" | "fileScan" | "ruleOutcome" | "filing";

const TONES: Record<StatusKind, Readonly<Record<string, Tone>>> = {
  "application": {
    "DRAFT": "neutral",
    "WAITING_BUYER_DATA": "warning",
    "WAITING_DOCUMENTS": "warning",
    "DOCUMENTS_REVIEW": "info",
    "READY_TO_FILE": "accent",
    "FILED": "info",
    "FILING_VALIDATION": "info",
    "CREDIT_ANALYSIS": "info",
    "APPROVED": "success",
    "LEGALIZATION": "success",
    "DISBURSED": "success",
    "BANK_OBSERVATION": "warning",
    "REJECTED": "danger",
    "WITHDRAWN": "neutral",
    "CANCELLED": "neutral",
    "OWN_FUNDS": "neutral",
    "EXTERNAL_CREDIT_APPROVED": "neutral"
  },
  "documentSlot": {
    "PENDING": "neutral",
    "UPLOADED": "info",
    "APPROVED": "success",
    "REJECTED": "danger",
    "WAIVED": "accent"
  },
  "fileScan": {
    "PENDING": "warning",
    "CLEAN": "success",
    "INFECTED": "danger",
    "INVALID": "danger"
  },
  "ruleOutcome": {
    "PASSED": "success",
    "FAILED": "danger",
    "MISSING_DATA": "warning"
  },
  "filing": {
    "FILED": "info",
    "RECEIVED": "info",
    "IN_ANALYSIS": "info",
    "RETURNED": "warning",
    "APPROVED": "success",
    "REJECTED": "danger",
    "DISBURSED": "success",
    "OTHER": "neutral"
  }
};

export function toneFor(kind: StatusKind, code: string | null | undefined): Tone {
  if (!code) return "neutral";
  return TONES[kind][code] ?? "neutral";
}
