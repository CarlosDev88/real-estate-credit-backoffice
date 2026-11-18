import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import { DARK } from "@/stories/globals";

const meta = {
  title: "Componentes/ThemeToggle",
  component: ThemeToggle,
  parameters: {
    docs: {
      description: {
        component:
          "Botón de tema de la barra superior. Muestra el ícono del tema al que cambia (luna en claro, sol en oscuro) y su nombre accesible lo dice. Cambia `data-theme` y el tema de Ant Design juntos, y guarda la elección. En Storybook, también mueve el selector de la barra.",
      },
    },
  },
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Claro: Story = {};
export const Oscuro: Story = { globals: DARK };

/** Al hacer clic, el nombre del botón pasa a "Cambiar a tema claro". */
export const Cambia: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Cambiar a tema oscuro" }));
    await expect(
      await canvas.findByRole("button", { name: "Cambiar a tema claro" }),
    ).toBeInTheDocument();
  },
};
