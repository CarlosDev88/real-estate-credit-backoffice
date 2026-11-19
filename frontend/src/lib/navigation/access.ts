import { safeNextPath } from "@/lib/api/session";
import { NAV_ITEMS, type Audience, type NavItem } from "@/lib/navigation/nav-config";

// El menú y el destino se deciden por permiso (de `/auth/me`). La única excepción es el
// broker sin rol interno: la API le responde otras formas (resumen de la solicitud,
// `BrokerClient`), así que las pantallas internas no son para él y tiene las suyas
// (`audience` de cada entrada, ver `nav-config.tsx`).

export const NO_MODULES_PATH = "/sin-modulos";

/** Códigos de rol de la API (`/auth/me`.roles), no textos que se muestren. */
const BROKER_ROLE = "INDEPENDENT_BROKER";
const INTERNAL_ROLES = ["ADMIN", "ADVISOR"];

/**
 * Público del usuario. `broker`: tiene el rol de broker y ninguno interno, la misma regla
 * con la que la API le restringe los datos (`CrmScope.is_restricted`).
 */
export function audienceOf(roles: readonly (string | null | undefined)[]): Audience {
  const set = new Set(roles);
  return set.has(BROKER_ROLE) && !INTERNAL_ROLES.some((r) => set.has(r)) ? "broker" : "internal";
}

function under(path: string, href: string): boolean {
  const pathname = path.split(/[?#]/)[0] ?? path;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** La entrada es para este público (sin `audience`, es para los dos). */
function forAudience(item: NavItem, audience: Audience): boolean {
  return !item.audience || item.audience === audience;
}

/** Entradas del menú que los permisos dejan ver, en el orden de la configuración. */
export function visibleNav(
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
  audience: Audience = "internal",
): NavItem[] {
  const granted = new Set(permissions);
  return items.filter((item) => granted.has(item.permission) && forAudience(item, audience));
}

/** Primera entrada permitida del menú; sin ninguna, la pantalla de "sin módulos". */
export function defaultDestination(
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
  audience: Audience = "internal",
) {
  return visibleNav(permissions, items, audience)[0]?.href ?? NO_MODULES_PATH;
}

/**
 * Destino después del login: `next`, si es interno y cae bajo una entrada del menú
 * que el usuario puede ver; si no, el destino por defecto.
 */
export function resolveDestination(
  next: string | null | undefined,
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
  audience: Audience = "internal",
): string {
  const safe = safeNextPath(next);
  if (safe && visibleNav(permissions, items, audience).some((item) => under(safe, item.href))) {
    return safe;
  }
  return defaultDestination(permissions, items, audience);
}

/** La ruta pertenece a una entrada del menú que el usuario no tiene permitida. */
export function isForbiddenPath(
  path: string,
  permissions: readonly string[],
  items: NavItem[] = NAV_ITEMS,
  audience: Audience = "internal",
): boolean {
  const granted = new Set(permissions);
  return items.some(
    (item) =>
      under(path, item.href) && (!granted.has(item.permission) || !forAudience(item, audience)),
  );
}
