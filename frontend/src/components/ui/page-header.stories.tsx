import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "antd";

import { PlusIcon } from "@/components/ui/icons";
import { BackLink, PageHeader } from "@/components/ui/page-header";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/PageHeader",
  component: PageHeader,
  subcomponents: { BackLink },
  parameters: {
    docs: {
      description: {
        component:
          'Encabezado de página: volver, título (el único `h1`), una línea de descripción y las acciones (una sola principal). Las migas del backoffice van en la barra superior del `AppShell`. En el portal, `variant="portal"` usa el enlace táctil de 44 px.',
      },
    },
  },
  argTypes: {
    title: { control: "text" },
    description: { control: "text" },
    back: { control: "object", description: "`{ href, label }` del enlace volver." },
    actions: { control: false },
    variant: { control: "inline-radio", options: ["backoffice", "portal"] },
  },
  args: {
    title: "Clientes",
    description: "Personas interesadas en un crédito de vivienda.",
    actions: (
      <Button type="primary" icon={<PlusIcon />}>
        Nuevo cliente
      </Button>
    ),
  },
} satisfies Meta<typeof PageHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Listado: Story = {};
export const ConVolver: Story = {
  name: "Con volver",
  args: {
    title: "Daniel Mejía Castaño",
    description: "Cliente desde el 12 de agosto de 2026",
    back: { href: "/clientes", label: "Volver a clientes" },
    actions: (
      <>
        <Button>Editar</Button>
        <Button type="primary">Crear solicitud</Button>
      </>
    ),
  },
};
export const SoloTitulo: Story = {
  name: "Solo título",
  args: { description: undefined, actions: undefined },
};
export const Portal: Story = {
  args: {
    variant: "portal",
    title: "Tus datos",
    description: "Revisa y completa tu información personal.",
    back: { href: "/portal", label: "Volver al inicio" },
    actions: undefined,
  },
};
export const TituloLargo: Story = {
  name: "Título largo",
  args: { title: "Solicitudes de crédito de vivienda con documentos pendientes de revisión" },
};
export const Oscuro: Story = { ...ConVolver, globals: DARK };
export const Movil: Story = { ...ConVolver, name: "Móvil", globals: MOBILE };
