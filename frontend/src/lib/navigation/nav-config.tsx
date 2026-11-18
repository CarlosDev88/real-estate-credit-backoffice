import type { ReactNode } from "react";

import { HouseIcon, UsersIcon } from "@/components/ui/icons";
import {
  BankIcon,
  BuildingIcon,
  CatalogIcon,
  DocumentsIcon,
  FlowIcon,
  ProjectIcon,
  UserShieldIcon,
} from "@/features/admin-common/icons";
import { DashboardIcon } from "@/features/dashboard/dashboard-icon";
import { ReportsIcon } from "@/features/reports/reports-icon";
import { MyDayIcon } from "@/features/workday/my-day-icon";

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
  // F5: bandeja de atención y tareas; el permiso es el de `GET /workday/applications`.
  {
    href: "/mi-dia",
    label: "Mi día",
    icon: <MyDayIcon />,
    group: "Operación",
    permission: "workday.read",
  },
  // F5: embudo y listado de solicitudes, con exportación (`reports.export`).
  {
    href: "/reportes",
    label: "Reportes",
    icon: <ReportsIcon />,
    group: "Operación",
    permission: "reports.read",
  },
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "applications.read",
  },
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
  // `banks.read` también lo tiene el asesor (lo usa en solicitudes): pide `banks.create`.
  {
    href: "/admin/bancos",
    label: "Bancos",
    icon: <BankIcon />,
    group: "Administración",
    permission: "banks.create",
  },
  // `document_requirements.read` también lo tiene el asesor: pide `.create` (administrador).
  {
    href: "/admin/documentos",
    label: "Documentos",
    icon: <DocumentsIcon />,
    group: "Administración",
    permission: "document_requirements.create",
  },
  {
    href: "/admin/catalogos",
    label: "Catálogos",
    icon: <CatalogIcon />,
    group: "Administración",
    permission: "catalogs.read",
  },
  {
    href: "/admin/flujos",
    label: "Flujos",
    icon: <FlowIcon />,
    group: "Administración",
    permission: "workflow.read",
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
