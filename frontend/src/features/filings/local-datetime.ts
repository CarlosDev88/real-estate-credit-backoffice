// Fecha y hora para `<input type="datetime-local">`, que trabaja en la hora local del
// navegador y sin zona: "2026-11-17T09:30".

const pad = (n: number) => String(n).padStart(2, "0");

/** `Date` → valor del campo, en hora local y sin segundos. */
export function toLocalInput(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** Valor del campo → ISO 8601 en UTC, o `null` si está vacío o no es una fecha. */
export function fromLocalInput(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** El valor es posterior a `now` (con un minuto de margen por los segundos que no se ven). */
export function isFutureInput(value: string, now: number = Date.now()): boolean {
  const iso = fromLocalInput(value);
  return iso !== null && Date.parse(iso) > now + 60_000;
}
