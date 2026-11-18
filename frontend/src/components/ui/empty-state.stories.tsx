import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "antd";

import { EmptyState } from "@/components/ui/empty-state";
import { SearchIcon, UsersIcon } from "@/components/ui/icons";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/EmptyState",
  component: EmptyState,
  parameters: {
    docs: {
      description: {
        component:
          'Estado vacío: qué pasa y, si se puede, la acción que lo destraba. Con filtros, "Limpiar filtros"; sin datos todavía, la acción para crear el primero.',
      },
    },
  },
  argTypes: {
    title: { control: "text", description: "Qué pasa, en una frase." },
    description: { control: "text", description: "Por qué o qué hacer." },
    icon: { control: false, description: "Ícono decorativo (se oculta al lector)." },
    action: { control: false, description: "Botón que destraba la vista." },
  },
  args: {
    title: "No hay solicitudes con estos filtros",
    description: "Prueba con otros filtros o límpialos para ver todas.",
    icon: <SearchIcon />,
    action: <Button>Limpiar filtros</Button>,
  },
  decorators: [
    (Story) => (
      <div className="bg-bg-surface border-border-default rounded-lg border">{Story()}</div>
    ),
  ],
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ConFiltros: Story = { name: "Con filtros" };
export const SinDatosTodavia: Story = {
  name: "Sin datos todavía",
  args: {
    title: "Todavía no hay clientes",
    description: "Registra el primero para empezar una oportunidad.",
    icon: <UsersIcon />,
    action: <Button type="primary">Nuevo cliente</Button>,
  },
};
export const SoloTitulo: Story = {
  name: "Solo título",
  args: {
    title: "Todavía no hay radicaciones",
    description: undefined,
    icon: undefined,
    action: undefined,
  },
};
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
