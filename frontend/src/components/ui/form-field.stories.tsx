import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Input, Select } from "antd";

import { FormField } from "@/components/ui/form-field";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/FormField",
  component: FormField,
  parameters: {
    docs: {
      description: {
        component:
          "Campo con etiqueta, ayuda y error debajo, enlazados con `aria-describedby`. `children` recibe las props del control (`id`, `aria-invalid`, `aria-describedby` y `status`). Con `useFormErrorHandler`, los `details[].field` de la API van a su campo y el resto al toast.",
      },
    },
  },
  argTypes: {
    label: { control: "text" },
    optional: { control: "text", description: "Texto entre paréntesis después de la etiqueta." },
    help: { control: "text", description: "Ayuda debajo del campo." },
    error: { control: "text", description: "Error del campo (del cliente o de la API)." },
    children: { control: false },
  },
  args: {
    id: "correo",
    label: "Correo",
    help: "Le enviamos el enlace de acceso a este correo.",
    children: (ctl) => <Input {...ctl} defaultValue="ana@correo.co" />,
  },
  decorators: [(Story) => <div className="max-w-sm">{Story()}</div>],
} satisfies Meta<typeof FormField>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };
export const Opcional: Story = {
  args: {
    id: "tel",
    label: "Teléfono",
    optional: "opcional",
    help: undefined,
    children: (ctl) => <Input {...ctl} />,
  },
};
export const ConError: Story = {
  name: "Con error",
  args: { error: "Escribe un correo válido, por ejemplo nombre@dominio.co." },
};
export const ErrorDeLaApi: Story = {
  name: "Error de la API",
  args: {
    id: "documento",
    label: "Número de documento",
    help: undefined,
    error: "Ya existe un cliente con este documento.",
    children: (ctl) => <Input {...ctl} defaultValue="1032445908" />,
  },
};
export const Deshabilitado: Story = {
  args: { children: (ctl) => <Input {...ctl} defaultValue="ana@correo.co" disabled /> },
};
export const ConSelect: Story = {
  name: "Con select",
  args: {
    id: "motivo",
    label: "Motivo",
    help: "Los motivos vienen del catálogo.",
    children: (ctl) => (
      <Select
        {...ctl}
        className="w-full"
        placeholder="Elige un motivo"
        options={[
          { value: "ILLEGIBLE", label: "Ilegible" },
          { value: "OUTDATED", label: "Desactualizado" },
        ]}
      />
    ),
  },
};
export const EtiquetaLarga: Story = {
  name: "Etiqueta larga",
  args: {
    label: "Valor del inmueble según la promesa de compraventa firmada por las partes",
    optional: "opcional si ya está en el avalúo",
  },
};
export const Oscuro: Story = { ...ConError, globals: DARK };
export const Movil: Story = { ...ConError, name: "Móvil", globals: MOBILE };
