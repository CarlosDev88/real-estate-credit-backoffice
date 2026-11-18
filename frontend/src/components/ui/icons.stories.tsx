import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import * as Icons from "@/components/ui/icons";
import { DARK } from "@/stories/globals";

const ICONS = Object.entries(Icons).filter(([name]) => name.endsWith("Icon")) as [
  string,
  (props: { width?: number; height?: number }) => React.ReactNode,
][];

function Gallery() {
  return (
    <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 p-0">
      {ICONS.map(([name, Icon]) => (
        <li
          key={name}
          className="border-border-default bg-bg-surface text-text-primary flex items-center gap-3 rounded-md border p-3"
        >
          <Icon width={20} height={20} />
          <code className="text-text-secondary font-mono text-xs">{name}</code>
        </li>
      ))}
      <li className="bg-bg-sidebar flex items-center gap-3 rounded-md p-3">
        <Icons.LogoMark />
        <code className="text-text-on-sidebar font-mono text-xs">LogoMark</code>
      </li>
    </ul>
  );
}

const meta = {
  title: "Componentes/Íconos",
  component: Gallery,
  parameters: {
    docs: {
      description: {
        component:
          "Íconos de los mockups, de 16 px por defecto y en `currentColor`. Son decorativos (`aria-hidden`): el texto accesible va en el control (`aria-label` o texto visible). Un ícono que comunica algo lleva texto oculto.",
      },
    },
  },
} satisfies Meta<typeof Gallery>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Todos: Story = {};
export const Oscuro: Story = { globals: DARK };
