/**
 * Abre la URL firmada de un archivo para descargarlo. La API responde con
 * `Content-Disposition: attachment`, así que el navegador no sale de la página.
 * Va aparte para poder reemplazarlo en las pruebas (jsdom no navega).
 */
export function startDownload(url: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.rel = "noopener";
  link.click();
}
