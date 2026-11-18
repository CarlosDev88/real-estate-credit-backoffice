import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { AppShell, AppShellSkeleton, useShellTrail } from "@/components/ui/app-shell";
import { HouseIcon, UsersIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import type { NavGroup } from "@/lib/navigation/nav-config";
import { DARK, MOBILE } from "@/stories/globals";

const NAV: NavGroup[] = [
  {
    label: "Comercial",
    items: [
      {
        href: "/clientes",
        label: "Clientes",
        icon: <UsersIcon />,
        group: "Comercial",
        permission: "clients.read",
      },
      {
        href: "/solicitudes",
        label: "Solicitudes",
        icon: <HouseIcon />,
        group: "Comercial",
        permission: "applications.read",
      },
    ],
  },
];

const USER = { name: "Laura Gómez Restrepo", email: "laura@umbral.co", role: "Asesora" };

function Detail() {
  useShellTrail("SOL-000182");
  return <PageHeader title="SOL-000182" description="Daniel Mejía · Vivienda nueva" />;
}

const meta = {
  title: "Componentes/AppShell",
  component: AppShell,
  parameters: {
    layout: "fullscreen",
    nextjs: { navigation: { pathname: "/solicitudes" } },
    docs: {
      story: { inline: false, iframeHeight: 520 },
      description: {
        component:
          'Shell del backoffice: barra lateral con el menú (solo lo que el usuario puede ver), barra superior con las migas y el botón de tema, y "Saltar al contenido". En 860 px o menos, el menú va en un drawer. `useShellTrail` agrega la última miga.',
      },
    },
  },
  argTypes: {
    nav: { control: false, description: "Grupos del menú, ya filtrados por permiso." },
    user: { control: "object", description: "Nombre, correo y rol (`role_label`)." },
    activeHref: { control: "text", description: "Ruta activa; por defecto, la actual." },
  },
  args: {
    nav: NAV,
    user: USER,
    onLogout: () => {},
    children: <PageHeader title="Solicitudes" description="Créditos de vivienda asignados a ti." />,
  },
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Listado: Story = {};
/** Con `useShellTrail`: "Comercial / Solicitudes / SOL-000182". */
export const ConMiga: Story = { name: "Con miga", args: { children: <Detail /> } };
export const SinRol: Story = { name: "Sin rol", args: { user: { ...USER, role: null } } };
/** Mientras se confirma la sesión (`/auth/me`). */
export const Cargando: Story = { render: () => <AppShellSkeleton /> };
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
