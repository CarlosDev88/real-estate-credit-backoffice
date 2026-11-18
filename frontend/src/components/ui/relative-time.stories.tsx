import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { RelativeTime } from "@/components/ui/relative-time";
import { DARK, minutesAgo } from "@/stories/globals";

const meta = {
  title: "Componentes/RelativeTime",
  component: RelativeTime,
  parameters: {
    docs: {
      description: {
        component:
          'Fecha relativa ("Hace 12 min", "Ayer") que se actualiza cada minuto. La fecha y hora completas van en el `title`. En el servidor y en la primera pasada muestra la fecha absoluta, sin diferencias de hidratación.',
      },
    },
  },
  argTypes: { value: { control: "text", description: "Fecha ISO de la API." } },
  args: { value: minutesAgo(12) },
} satisfies Meta<typeof RelativeTime>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };

/** Todos los rangos: momento, minutos, horas, ayer, días y fecha. */
export const Rangos: Story = {
  render: () => (
    <ul className="m-0 grid list-none gap-1 p-0 text-sm">
      {[0, 12, 180, 60 * 26, 60 * 24 * 3, 60 * 24 * 40, 60 * 24 * 400].map((m) => (
        <li key={m}>
          <RelativeTime value={minutesAgo(m)} />
        </li>
      ))}
    </ul>
  ),
};

export const Oscuro: Story = { ...Rangos, globals: DARK };
