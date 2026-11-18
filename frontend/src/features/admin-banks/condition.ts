// Condición de una regla bancaria (API §23.3): un JSON que la API valida contra su lista
// blanca de campos. El front no conoce esa lista (no hay endpoint: brecha anotada), así que
// solo revisa que sea JSON y, para leerla, la resume en texto. Gramática:
//
//   comparación  {"operator": "eq"|"gte"|"lte", "left": valor, "right": valor}
//   pertenencia  {"operator": "in", "left": valor, "right": [literal, ...]}
//   lógica       {"operator": "and"|"or", "conditions": [condición, ...]}
//   valor        literal | {"field": "grupo.campo"} | {"operator": "sum", "fields": [...]}
//                | {"operator": "ratio", "numerator_field": "...", "denominator_field": "..."}

type Node = Record<string, unknown>;

const isNode = (value: unknown): value is Node =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const SYMBOLS: Record<string, string> = { eq: "=", gte: "≥", lte: "≤" };
const JOINERS: Record<string, string> = { and: " y ", or: " o " };

function literal(value: unknown): string {
  if (typeof value === "string") return `"${value}"`;
  if (typeof value === "number") return value.toLocaleString("es-CO");
  if (typeof value === "boolean") return value ? "sí" : "no";
  return JSON.stringify(value);
}

function describeValue(value: unknown): string {
  if (!isNode(value)) return literal(value);
  if (typeof value.field === "string") return value.field;
  if (value.operator === "sum" && Array.isArray(value.fields)) {
    return `(${value.fields.map(String).join(" + ")})`;
  }
  if (value.operator === "ratio") {
    return `(${String(value.numerator_field)} / ${String(value.denominator_field)})`;
  }
  return JSON.stringify(value);
}

/**
 * Resumen legible ("financing.term_months ≤ 360 y applicant.employment_months ≥ 12"). Lo que
 * no entiende lo deja como JSON: es solo para leer, la API es la que valida.
 */
export function describeCondition(node: unknown, depth = 0): string {
  if (!isNode(node)) return JSON.stringify(node);
  const operator = String(node.operator ?? "");
  if (operator in JOINERS && Array.isArray(node.conditions)) {
    const parts = node.conditions.map((child) => describeCondition(child, depth + 1));
    const text = parts.join(JOINERS[operator]);
    return depth > 0 && parts.length > 1 ? `(${text})` : text;
  }
  if (operator in SYMBOLS) {
    return `${describeValue(node.left)} ${SYMBOLS[operator]} ${describeValue(node.right)}`;
  }
  if (operator === "in" && Array.isArray(node.right)) {
    return `${describeValue(node.left)} en [${node.right.map(literal).join(", ")}]`;
  }
  return JSON.stringify(node);
}

/** Campos que usa la condición (`grupo.campo`), sin repetir y en orden de aparición. */
export function fieldsOf(node: unknown, out: string[] = []): string[] {
  const add = (name: unknown) => {
    if (typeof name === "string" && !out.includes(name)) out.push(name);
  };
  if (Array.isArray(node)) {
    node.forEach((child) => fieldsOf(child, out));
  } else if (isNode(node)) {
    add(node.field);
    if (Array.isArray(node.fields)) node.fields.forEach(add);
    add(node.numerator_field);
    add(node.denominator_field);
    for (const key of ["left", "right", "conditions"]) {
      if (key in node) fieldsOf(node[key], out);
    }
  }
  return out;
}

/**
 * Contexto de ejemplo para probar la regla: los campos que usa, en `null`
 * (`{"financing": {"term_months": null}}`). Así el caso arranca con la forma correcta.
 */
export function contextSkeleton(condition: unknown): Record<string, Record<string, null>> {
  const context: Record<string, Record<string, null>> = {};
  for (const name of fieldsOf(condition)) {
    const [group, field] = name.split(".", 2);
    if (!group || !field) continue;
    (context[group] ??= {})[field] = null;
  }
  return context;
}

export type JsonResult = { ok: true; value: unknown } | { ok: false };

export function parseJson(text: string): JsonResult {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

export const pretty = (value: unknown) => JSON.stringify(value, null, 2);
