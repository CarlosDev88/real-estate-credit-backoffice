import type { ReactNode } from "react";

import { HouseIcon, UsersIcon } from "@/components/ui/icons";
import { BuildingIcon, ProjectIcon, UserShieldIcon } from "@/features/admin-common/icons";

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
  // F4: el ícono vive en `features/clients` hasta que el front 1 lo pase a `components/ui`.
  {
    href: "/clientes",
    label: "Clientes",
    icon: <UsersIcon />,
    group: "Comercial",
    permission: "clients.read",
  },
  // F6 (front-admin): grupo "Administración". Cada entrada pide su permiso de `/auth/me`;
  // el ícono vive en `features/admin-common` hasta que pase a `components/ui`.
  {
    href: "/admin/usuarios",
    label: "Usuarios",
    icon: <UserShieldIcon />,
    group: "Administración",
    permission: "users.read",
  },
  // `partners.read` también lo tienen asesor y constructora: la entrada pide
  // `partners.create` (solo administrador), como pide la spec F6.
  {
    href: "/admin/constructoras",
    label: "Constructoras",
    icon: <BuildingIcon />,
    group: "Administración",
    permission: "partners.create",
  },
  {
    href: "/proyectos",
    label: "Proyectos",
    icon: <ProjectIcon />,
    group: "Administración",
    permission: "projects.read",
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
