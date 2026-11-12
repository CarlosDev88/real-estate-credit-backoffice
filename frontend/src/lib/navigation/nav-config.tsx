import type { ReactNode } from "react";

import { HouseIcon } from "@/components/ui/icons";

// Navegación del backoffice. Es la estructura de la app, no una lista de negocio:
// cada entrada pide un permiso de `/auth/me` y solo aparece si la ruta existe.
export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  group: string | null;
  permission: string;
}

export interface NavGroup {
  label: string | null;
  items: NavItem[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "applications.read",
  },
];

/** Agrupa en el orden de aparición. Los grupos sin entradas no se devuelven. */
export function groupNav(items: NavItem[]): NavGroup[] {
  const groups: NavGroup[] = [];
  for (const item of items) {
    let group = groups.find((g) => g.label === item.group);
    if (!group) {
      group = { label: item.group, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  }
  return groups;
}
