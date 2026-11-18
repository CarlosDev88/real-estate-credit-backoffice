/**
 * Guarda un archivo que llegó en la respuesta (el CSV directo). Va aparte para poder
 * reemplazarlo en las pruebas: jsdom no descarga.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // El navegador ya tomó el archivo; se libera en el siguiente ciclo.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** `attachment; filename="solicitudes_2026-11-01_2026-11-18.csv"` → el nombre. */
export function filenameFrom(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(disposition);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      // nombre mal codificado: se usa el simple
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain?.[1]?.trim() || fallback;
}
