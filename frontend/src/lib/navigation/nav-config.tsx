import type { ReactNode } from "react";

import { DashboardIcon } from "@/features/dashboard/dashboard-icon";
import { HouseIcon } from "@/components/ui/icons";
import { UsersIcon } from "@/features/clients/components/icons";

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
  // F5: el inicio después del login para quien tenga `dashboard.read` (es la primera
  // entrada permitida, ver `defaultDestination`).
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: <DashboardIcon />,
    group: "Operación",
    permission: "dashboard.read",
  },
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "applications.read",
  },
  // F4: el ícono vive en `features/clients` hasta que el front 1 lo pase a `components/ui`.
  {
    href: "/clientes",
    label: "Clientes",
    icon: <UsersIcon />,
    group: "Comercial",
    permission: "clients.read",
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
