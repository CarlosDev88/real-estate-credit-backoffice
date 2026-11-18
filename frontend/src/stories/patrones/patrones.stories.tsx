import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { DARK, MOBILE } from "@/stories/globals";

import { FormPattern, ListFiltersPattern, StatesPattern } from "./ejemplos";

/**
 * Ejemplos de las páginas de patrones (las MDX de esta carpeta los muestran). No salen en
 * la barra lateral (`!dev`), pero corren en `pnpm test:storybook` con la revisión de a11y.
 */
const meta = {
  title: "Patrones/Ejemplos",
  tags: ["!dev", "!autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Formulario: Story = { render: () => <FormPattern /> };
export const FormularioOscuro: Story = { render: () => <FormPattern />, globals: DARK };
export const ListaConFiltros: Story = { render: () => <ListFiltersPattern /> };
export const ListaConFiltrosMovil: Story = {
  render: () => <ListFiltersPattern />,
  globals: MOBILE,
};
export const Estados: Story = { render: () => <StatesPattern /> };
export const EstadosOscuro: Story = { render: () => <StatesPattern />, globals: DARK };
