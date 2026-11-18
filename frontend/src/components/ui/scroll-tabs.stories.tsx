import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { ScrollTabs, type ScrollTabItem } from "@/components/ui/scroll-tabs";
import { DARK, MOBILE } from "@/stories/globals";

const STATES: ScrollTabItem[] = [
  { key: "all", label: "Todas", count: 48 },
  { key: "draft", label: "Borrador", count: 6 },
  { key: "data", label: "Esperando datos", count: 9 },
  { key: "docs", label: "Esperando documentos", count: 12 },
  { key: "review", label: "Revisión documental", count: 7 },
  { key: "ready", label: "Lista para radicar", count: 3 },
  { key: "filed", label: "Radicada", count: 5 },
  { key: "analysis", label: "Análisis de crédito", count: 4 },
  { key: "approved", label: "Aprobada", count: 2 },
];

function Tabs({ items, initial }: { items: ScrollTabItem[]; initial?: string }) {
  const [value, setValue] = useState(initial ?? items[0]?.key ?? "");
  return <ScrollTabs items={items} value={value} onChange={setValue} ariaLabel="Filtro rápido" />;
}

const meta = {
  title: "Componentes/ScrollTabs",
  component: ScrollTabs,
  parameters: {
    docs: {
      description: {
        component:
          "Pestañas que se desplazan sin barra visible, con desvanecido y flechas cuando no caben. Teclado: flechas, Inicio y Fin mueven el foco; Enter o Espacio eligen. Los textos vienen de la API.",
      },
    },
  },
  argTypes: {
    items: { description: "Pestañas: `label`, `count` y, opcional, `countLabel` y `countTone`." },
    ariaLabel: { description: "Nombre accesible del grupo." },
  },
  args: { items: STATES, value: "all", onChange: () => {}, ariaLabel: "Filtro rápido" },
  render: (args) => <Tabs items={args.items} initial={args.value} />,
} satisfies Meta<typeof ScrollTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Más pestañas de las que caben: aparecen las flechas y el desvanecido. */
export const Desplazables: Story = {
  decorators: [(Story) => <div className="max-w-xl">{Story()}</div>],
};

/** Pestañas del expediente: el conteo de documentos pendientes pide atención. */
export const ConteoDeAdvertencia: Story = {
  name: "Conteo de advertencia",
  args: {
    value: "resumen",
    items: [
      { key: "resumen", label: "Resumen" },
      {
        key: "documentos",
        label: "Documentos",
        count: 6,
        countLabel: "6 pendientes",
        countTone: "warning",
      },
      { key: "radicacion", label: "Radicación", count: 1 },
      { key: "historial", label: "Historial" },
    ],
  },
};

export const SinConteos: Story = {
  name: "Sin conteos",
  args: {
    items: [
      { key: "a", label: "Resumen" },
      { key: "b", label: "Documentos" },
      { key: "c", label: "Historial" },
    ],
    value: "a",
  },
};

export const Oscuro: Story = { ...ConteoDeAdvertencia, globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
