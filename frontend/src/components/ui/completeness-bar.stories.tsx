import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "@/components/ui/card";
import { CompletenessBar, CompletenessTotal } from "@/components/ui/completeness-bar";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/CompletenessBar",
  component: CompletenessBar,
  parameters: {
    docs: {
      description: {
        component:
          'Completitud del expediente: total, datos y documentos. Siempre en `brand.primary` (el teal es estado, no avance). `layout="split"` y `CompletenessTotal` dan la versión del mockup, con el total en el encabezado de la tarjeta.',
      },
    },
  },
  argTypes: {
    percentage: { control: { type: "range", min: 0, max: 100 }, description: "Total de la API." },
    dataPercentage: { control: { type: "range", min: 0, max: 100 } },
    documentsPercentage: { control: { type: "range", min: 0, max: 100 } },
    variant: { control: "inline-radio", options: ["full", "mini"] },
    layout: { control: "inline-radio", options: ["stacked", "split"] },
    showTotal: { control: "boolean" },
  },
  args: {
    percentage: 81,
    dataPercentage: 100,
    documentsPercentage: 62,
    documentsCompleted: 10,
    documentsRequired: 16,
  },
  decorators: [(Story) => <div className="max-w-xl">{Story()}</div>],
} satisfies Meta<typeof CompletenessBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Apilada: Story = {};

/** Como el mockup `solicitud.html`: el total en el encabezado y las dos partes lado a lado. */
export const EnTarjeta: Story = {
  name: "En tarjeta (mockup)",
  render: (args) => (
    <Card
      title="Completitud del expediente"
      action={<CompletenessTotal percentage={args.percentage} />}
    >
      <CompletenessBar {...args} layout="split" showTotal={false} />
    </Card>
  ),
};

/** Fila del listado: barra corta con el porcentaje. */
export const Mini: Story = { args: { variant: "mini", percentage: 54 } };

export const Vacia: Story = {
  name: "Vacía",
  args: { percentage: 0, dataPercentage: 0, documentsPercentage: 0, documentsCompleted: 0 },
};

export const Completa: Story = {
  args: { percentage: 100, dataPercentage: 100, documentsPercentage: 100, documentsCompleted: 16 },
};

export const Oscuro: Story = { ...EnTarjeta, globals: DARK };
export const Movil: Story = { ...EnTarjeta, name: "Móvil", globals: MOBILE };
