// Navegación completa del navegador, aparte para poder sustituirla en las pruebas.

export function redirectTo(url: string): void {
  window.location.assign(url);
}

export function currentPath(): string {
  return `${window.location.pathname}${window.location.search}`;
}
