// Fecha y hora para `<input type="datetime-local">`, que trabaja en la hora local del
// navegador y sin zona: "2026-11-17T09:30".

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO de la API → valor del campo, en hora local y sin segundos (`""` si no hay). */
export function toLocalInput(value: string | Date | null | undefined): string {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
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
