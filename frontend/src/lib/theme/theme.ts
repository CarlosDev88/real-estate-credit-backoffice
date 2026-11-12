// Tema claro (por defecto) u oscuro. No se sigue el tema del sistema operativo.
// `localStorage` es la fuente; la cookie es una copia para que el servidor pinte
// el tema correcto y Ant Design no parpadee.

export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "um-theme";
export const THEME_COOKIE = "um-theme";
const THEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

/** Cualquier valor que no sea `dark` o `light` se trata como `light`. */
export function parseTheme(value: string | null | undefined): ThemeMode {
  return value === "dark" ? "dark" : "light";
}

/** Valor guardado en `localStorage`, o `null` si no hay o no se puede leer. */
export function readStoredTheme(): ThemeMode | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null;
  }
}

/** Guarda la elección en `localStorage` y en la cookie. Si algo falla, sigue. */
export function persistTheme(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // Sin almacenamiento (modo privado, bloqueado): el tema vale solo para esta visita.
  }
  try {
    document.cookie = `${THEME_COOKIE}=${mode}; Path=/; Max-Age=${THEME_COOKIE_MAX_AGE}; SameSite=Lax`;
  } catch {
    // Sin cookies: el script de <head> aplica el tema desde localStorage.
  }
}

export function applyThemeAttribute(mode: ThemeMode): void {
  document.documentElement.setAttribute("data-theme", mode);
}

/**
 * Respaldo para cuando el servidor no recibió la cookie: aplica el tema guardado
 * en `localStorage` antes de pintar. Va en <head> como script en línea.
 */
export const THEME_FALLBACK_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="dark"||t==="light"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;
