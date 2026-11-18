import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { FilterChips, type FilterChip } from "@/components/ui/filter-chips";
import { DARK, MOBILE } from "@/stories/globals";

const CHIPS: FilterChip[] = [
  { key: "updated", label: "Actualizada", value: "últimos 30 días" },
  { key: "advisor", label: "Asesor", value: "Laura Gómez" },
  { key: "purpose", label: "Finalidad", value: "Vivienda nueva" },
];

function Chips({ chips: initial, caption }: { chips: FilterChip[]; caption?: string }) {
  const [chips, setChips] = useState(initial);
  return (
    <FilterChips
      chips={chips}
      caption={caption}
      onRemove={(key) => setChips((c) => c.filter((chip) => chip.key !== key))}
      onClearAll={() => setChips([])}
    />
  );
}

const meta = {
  title: "Componentes/FilterChips",
  component: FilterChips,
  parameters: {
    docs: {
      description: {
        component:
          "Filtros activos que no se ven en la barra (los visibles no se repiten como chips). Cada chip se quita con su botón, que dice qué filtro quita. Sin chips no se pinta nada.",
      },
    },
  },
  argTypes: {
    chips: { description: "Filtros con su nombre y el valor elegido (texto de la API)." },
    caption: { control: "text", description: "Texto antes de los chips." },
  },
  args: { chips: CHIPS, onRemove: () => {}, caption: 'Desde "Más filtros":' },
  render: (args) => <Chips chips={args.chips} caption={args.caption} />,
} satisfies Meta<typeof FilterChips>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };
export const Vacio: Story = { name: "Vacío (no se pinta)", args: { chips: [] } };
export const ValoresLargos: Story = {
  name: "Valores largos",
  args: {
    chips: [
      { key: "bank", label: "Banco", value: "Banco Agrario de Colombia S. A." },
      { key: "product", label: "Tipo de crédito", value: "Leasing habitacional con subsidio" },
    ],
  },
};
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
