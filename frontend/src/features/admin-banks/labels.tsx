import { StatusBadge, ToneBadge } from "@/components/ui/status-badge";

// Textos de las reglas bancarias que la API no manda: estado de la versión
// (`BankPolicyRuleStatusEnum`), severidad (`SeverityEnum`) y resultado de una prueba
// (`RuleOutcomeEnum`). Copian los `TextChoices` y `OUTCOME_LABELS` del backend.
// Brecha anotada: exponer `status_label`, `severity_label` y `outcome_label`.

export const RULE_STATUS_CODES = ["DRAFT", "ACTIVE", "INACTIVE"] as const;
export const RULE_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Borrador",
  ACTIVE: "Activa",
  INACTIVE: "Inactiva",
};

export const SEVERITY_CODES = ["BLOCKING", "WARNING"] as const;
export type Severity = (typeof SEVERITY_CODES)[number];
export const SEVERITY_LABELS: Record<string, string> = {
  BLOCKING: "Bloqueante",
  WARNING: "Advertencia",
};

export const OUTCOME_CODES = ["PASSED", "FAILED", "MISSING_DATA"] as const;
export type Outcome = (typeof OUTCOME_CODES)[number];
export const OUTCOME_LABELS: Record<string, string> = {
  PASSED: "Cumple",
  FAILED: "No cumple",
  MISSING_DATA: "Faltan datos",
};

const labelIn = (labels: Record<string, string>, code: string) => labels[code] ?? code;

/** Estado de la versión de la regla. No está en `status-tones`: tono neutro (spec F6). */
export function RuleStatusBadge({ status }: { status: string }) {
  return <ToneBadge tone="neutral">{labelIn(RULE_STATUS_LABELS, status)}</ToneBadge>;
}

/** Severidad: tampoco está en `status-tones`, tono neutro. */
export function SeverityBadge({ severity }: { severity: string }) {
  return <ToneBadge tone="neutral">{labelIn(SEVERITY_LABELS, severity)}</ToneBadge>;
}

/** Resultado de una evaluación: `ruleOutcome` sí está en `status-tones`. */
export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <StatusBadge kind="ruleOutcome" code={outcome} label={labelIn(OUTCOME_LABELS, outcome)} />;
}

export const ruleStatusLabel = (code: string) => labelIn(RULE_STATUS_LABELS, code);
export const severityLabel = (code: string) => labelIn(SEVERITY_LABELS, code);
export const outcomeLabel = (code: string) => labelIn(OUTCOME_LABELS, code);
