/** Solo los campos que cambiaron respecto de los valores iniciales (para un `PATCH`). */
export function changedFields<T extends Record<string, unknown>, K extends keyof T>(
  values: T,
  initial: T,
  keys: readonly K[],
): Partial<Pick<T, K>> {
  const out: Partial<Pick<T, K>> = {};
  for (const key of keys) {
    if (JSON.stringify(values[key]) !== JSON.stringify(initial[key])) out[key] = values[key];
  }
  return out;
}
