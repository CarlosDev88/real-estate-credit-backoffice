// Orden de los valores de un catálogo: se mueve de a un puesto con botones (accesible con
// teclado y lector de pantalla, sin depender de arrastrar) y se guarda todo junto.

/** Mueve el elemento `index` un puesto (`-1` arriba, `+1` abajo). Fuera de rango, igual. */
export function move<T>(items: readonly T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (index < 0 || index >= items.length || target < 0 || target >= items.length) {
    return [...items];
  }
  const next = [...items];
  [next[index], next[target]] = [next[target]!, next[index]!];
  return next;
}

/** El orden cambió respecto del original (por id). */
export function orderChanged(
  original: readonly { id: string }[],
  current: readonly { id: string }[],
) {
  return (
    original.length !== current.length || original.some((item, i) => item.id !== current[i]?.id)
  );
}

/** "Casa: puesto 2 de 5": lo que anuncia el lector de pantalla al mover. */
export function positionText(label: string, index: number, total: number): string {
  return `${label}: puesto ${index + 1} de ${total}.`;
}
