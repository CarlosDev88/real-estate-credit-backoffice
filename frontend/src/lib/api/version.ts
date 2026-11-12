// Concurrencia del expediente (API §6): la versión llega en `ETag` y vuelve en `If-Match`.

/** Lee la versión de un `ETag`: acepta `"7"`, `7` y `W/"7"`. */
export function parseVersion(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isInteger(value) && value >= 0 ? value : null;
  const match = /^\s*(?:W\/)?(?:"(\d+)"|(\d+))\s*$/.exec(value);
  return match ? Number(match[1] ?? match[2]) : null;
}

/** Valor para `If-Match` en el formato canónico `"7"`. */
export function ifMatch(version: string | number): string {
  const parsed = parseVersion(version);
  if (parsed === null) throw new Error(`Versión inválida para If-Match: ${String(version)}`);
  return `"${parsed}"`;
}

/** Versión de una respuesta (también de un `204`), o `null` si no trae `ETag`. */
export function versionOf(response: Response): number | null {
  return parseVersion(response.headers.get("ETag"));
}
