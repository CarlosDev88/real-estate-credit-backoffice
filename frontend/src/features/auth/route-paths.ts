// Rutas con consultas adelantadas para su primera pintura (`route-prefetch.ts`). Aparte, y sin
// dependencias, para que la guarda decida sin cargar ese módulo en todas las rutas.

export const DOSSIER = /^\/solicitudes\/([^/]+)$/;

export function hasFirstPaintPrefetch(pathname: string): boolean {
  return DOSSIER.test(pathname);
}
