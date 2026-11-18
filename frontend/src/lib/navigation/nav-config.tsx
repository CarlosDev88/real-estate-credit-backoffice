import type { ReactNode } from "react";

import { HouseIcon, UsersIcon } from "@/components/ui/icons";
import { BrokerIcon } from "@/features/broker/broker-icon";
import { CommissionsIcon, MyCommissionsIcon } from "@/features/commissions/commissions-icon";
import { DashboardIcon } from "@/features/dashboard/dashboard-icon";
import { ReportsIcon } from "@/features/reports/reports-icon";
import { MyDayIcon } from "@/features/workday/my-day-icon";

// Navegación del backoffice. Es la estructura de la app, no una lista de negocio:
// cada entrada pide un permiso de `/auth/me` y solo aparece si la ruta existe.

/**
 * Para quién es la entrada. `broker`: solo el broker sin rol interno; `internal`: todos
 * menos él (la API le responde otras formas y esas pantallas no son para él). Sin
 * `audience`, la ven los dos (ver `audienceOf` en `access.ts`).
 */
export type Audience = "broker" | "internal";

export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  group: string | null;
  permission: string;
  audience?: Audience;
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
    audience: "internal",
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
  // F7: el inicio del broker (REQ §6): bandeja de prospectos, alta, enlace y estados.
  {
    href: "/prospectos",
    label: "Mis prospectos",
    icon: <BrokerIcon />,
    group: "Comercial",
    permission: "opportunities.read",
    audience: "broker",
  },
  {
    href: "/solicitudes",
    label: "Solicitudes",
    icon: <HouseIcon />,
    group: "Comercial",
    permission: "applications.read",
    audience: "internal",
  },
  {
    href: "/clientes",
    label: "Clientes",
    icon: <UsersIcon />,
    group: "Comercial",
    permission: "clients.read",
    audience: "internal",
  },
  // F7: liquidaciones y planes (administración de comisiones) y la parte propia del
  // asesor y del broker. Grupo propio, aparte de "Administración".
  {
    href: "/comisiones",
    label: "Comisiones",
    icon: <CommissionsIcon />,
    group: "Finanzas",
    permission: "commissions.read",
  },
  {
    href: "/mis-comisiones",
    label: "Mis comisiones",
    icon: <MyCommissionsIcon />,
    group: "Finanzas",
    permission: "commissions.read_own",
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
