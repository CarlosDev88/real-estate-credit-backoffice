import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { FormField } from "@/components/ui/form-field";
import { Money, MoneyInput } from "@/components/ui/money";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/Money",
  component: Money,
  parameters: {
    docs: {
      description: {
        component:
          'Montos en COP enteros con `Intl.NumberFormat("es-CO")` y cifras tabulares. `MoneyInput` es el campo: prefijo COP, separador de miles, a la derecha y sin negativos.',
      },
    },
  },
  argTypes: {
    value: { control: "number", description: "Monto entero en pesos. `null` muestra `empty`." },
    empty: { control: "text", description: "Texto cuando no hay monto." },
  },
  args: { value: 294_000_000 },
} satisfies Meta<typeof Money>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };
export const Vacio: Story = { name: "Vacío", args: { value: null } };
export const VacioConTexto: Story = {
  name: "Vacío con texto",
  args: { value: null, empty: "Sin monto" },
};

/** Cifras tabulares: los montos se alinean en una columna. */
export const EnColumna: Story = {
  name: "En columna",
  render: () => (
    <div className="grid w-48 justify-items-end gap-1">
      <Money value={1_250_000} />
      <Money value={294_000_000} />
      <Money value={88_100_000} />
    </div>
  ),
};

function MoneyInputDemo({ error, disabled }: { error?: string; disabled?: boolean }) {
  const [value, setValue] = useState<number | null>(294_000_000);
  return (
    <div className="max-w-xs">
      <FormField id="monto" label="Monto solicitado" help="En pesos, sin decimales." error={error}>
        {(ctl) => (
          <MoneyInput {...ctl} value={value} onChange={setValue} disabled={disabled} size="large" />
        )}
      </FormField>
    </div>
  );
}

export const Campo: Story = { render: () => <MoneyInputDemo /> };
export const CampoConError: Story = {
  name: "Campo con error",
  render: () => <MoneyInputDemo error="El monto supera el 70 % del valor del inmueble." />,
};
export const CampoDeshabilitado: Story = {
  name: "Campo deshabilitado",
  render: () => <MoneyInputDemo disabled />,
  parameters: {
    // El prefijo "COP" es parte de un control inactivo, que no tiene mínimo de contraste
    // (WCAG 1.4.3); axe solo exime al `input`, no al prefijo de Ant Design.
    a11y: { config: { rules: [{ id: "color-contrast", enabled: false }] } },
  },
};
export const Oscuro: Story = { render: () => <MoneyInputDemo />, globals: DARK };
export const Movil: Story = { name: "Móvil", render: () => <MoneyInputDemo />, globals: MOBILE };
