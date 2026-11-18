import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Stepper, type ProgressStage } from "@/components/ui/stepper";
import { DARK, MOBILE } from "@/stories/globals";

const STAGES = [
  { code: "DATA", label: "Datos", state: "done", state_label: "Completa" },
  { code: "DOCUMENTS", label: "Documentos", state: "done", state_label: "Completa" },
  { code: "FILING", label: "Radicación", state: "current", state_label: "En curso" },
  { code: "ANALYSIS", label: "Análisis del banco", state: "pending", state_label: "Pendiente" },
  { code: "APPROVAL", label: "Aprobación", state: "pending", state_label: "Pendiente" },
  { code: "DISBURSEMENT", label: "Desembolso", state: "pending", state_label: "Pendiente" },
] as ProgressStage[];

const meta = {
  title: "Componentes/Stepper",
  component: Stepper,
  parameters: {
    docs: {
      description: {
        component:
          'Etapas de una solicitud (`progress_stages` o `stages` de la API). El estado va también en texto (`state_label`) y la actual lleva `aria-current="step"`. Horizontal en el expediente (se desplaza en pantallas angostas); vertical en la tarjeta de estado del portal, sobre fondo oscuro.',
      },
    },
  },
  argTypes: {
    stages: { control: "object" },
    orientation: { control: "inline-radio", options: ["horizontal", "vertical"] },
    ariaLabel: { control: "text" },
  },
  args: { stages: STAGES, ariaLabel: "Etapas de la solicitud" },
} satisfies Meta<typeof Stepper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Horizontal: Story = {};
/** En la tarjeta de estado del portal (`bg.sidebar`). */
export const Vertical: Story = {
  args: { orientation: "vertical", ariaLabel: "Etapas" },
  decorators: [
    (Story) => (
      <div className="bg-bg-sidebar text-text-on-sidebar max-w-sm rounded-xl p-5">{Story()}</div>
    ),
  ],
};
export const Inicio: Story = {
  args: {
    stages: STAGES.map((s, i) => ({
      ...s,
      state: i === 0 ? "current" : "pending",
      state_label: i === 0 ? "En curso" : "Pendiente",
    })) as ProgressStage[],
  },
};
export const Vacio: Story = { name: "Vacío (no se pinta)", args: { stages: [] } };
export const Oscuro: Story = { globals: DARK };
/** En móvil, la línea se desplaza en horizontal y se recorre con el teclado. */
export const Movil: Story = { name: "Móvil", globals: MOBILE };
