import { safeNextPath } from "@/lib/api/session";
import { NAV_ITEMS, type NavItem } from "@/lib/navigation/nav-config";

// El menú y el destino se deciden por permiso (de `/auth/me`), nunca por nombre de rol.

export const NO_MODULES_PATH = "/sin-modulos";

function under(path: string, href: string): boolean {
  const pathname = path.split(/[?#]/)[0] ?? path;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Entradas del menú que los permisos dejan ver, en el orden de la configuración. */
export function visibleNav(
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
): NavItem[] {
  const granted = new Set(permissions);
  return items.filter((item) => granted.has(item.permission));
}

/** Primera entrada permitida del menú; sin ninguna, la pantalla de "sin módulos". */
export function defaultDestination(permissions: readonly string[], items: NavItem[] = NAV_ITEMS) {
  return visibleNav(permissions, items)[0]?.href ?? NO_MODULES_PATH;
}

/**
 * Destino después del login: `next`, si es interno y cae bajo una entrada del menú
 * que el usuario puede ver; si no, el destino por defecto.
 */
export function resolveDestination(
  next: string | null | undefined,
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
): string {
  const safe = safeNextPath(next);
  if (safe && visibleNav(permissions, items).some((item) => under(safe, item.href))) return safe;
  return defaultDestination(permissions, items);
}

/** La ruta pertenece a una entrada del menú que el usuario no tiene permitida. */
export function isForbiddenPath(
  path: string,
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
): boolean {
  const granted = new Set(permissions);
  return items.some((item) => under(path, item.href) && !granted.has(item.permission));
}
