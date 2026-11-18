import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { StatusBadge } from "@/components/ui/status-badge";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/StatusBadge",
  component: StatusBadge,
  parameters: {
    docs: {
      description: {
        component:
          "Estado con punto de color y la etiqueta de la API. El color sale de `status-tones.ts` (`toneFor`); un código desconocido es `neutral`. Es la única píldora con color.",
      },
    },
  },
  argTypes: {
    kind: {
      control: "select",
      options: ["application", "documentSlot", "fileScan", "ruleOutcome", "filing", "opportunity"],
      description: "Tipo de estado: decide en qué mapa se busca el código.",
    },
    code: { control: "text", description: "Código del estado (solo decide el color)." },
    label: { control: "text", description: "Texto del estado: siempre viene de la API." },
  },
  args: { kind: "application", code: "READY_TO_FILE", label: "Lista para radicar" },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };

const SAMPLES = [
  { code: "DRAFT", label: "Borrador" },
  { code: "DOCUMENTS_REVIEW", label: "Revisión documental" },
  { code: "READY_TO_FILE", label: "Lista para radicar" },
  { code: "APPROVED", label: "Aprobada" },
  { code: "WAITING_DOCUMENTS", label: "Esperando documentos" },
  { code: "REJECTED", label: "Rechazada" },
];

/** Los seis tonos con estados reales de la solicitud. */
export const Tonos: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {SAMPLES.map((s) => (
        <StatusBadge key={s.code} kind="application" code={s.code} label={s.label} />
      ))}
    </div>
  ),
};

export const Oportunidad: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusBadge kind="opportunity" code="NEW" label="Nueva" />
      <StatusBadge kind="opportunity" code="CONTACTED" label="Contactada" />
      <StatusBadge kind="opportunity" code="CONVERTED" label="Convertida" />
      <StatusBadge kind="opportunity" code="LOST" label="Perdida" />
    </div>
  ),
};

/** Un código que el frontend no conoce cae en `neutral`: un estado nuevo no rompe nada. */
export const CodigoDesconocido: Story = {
  name: "Código desconocido",
  args: { code: "ESTADO_NUEVO", label: "Estado nuevo del backend" },
};

/** Sin código (`null`): neutral. */
export const SinCodigo: Story = { name: "Sin código", args: { code: null, label: "Sin estado" } };

export const TextoLargo: Story = {
  name: "Texto largo",
  args: {
    code: "EXTERNAL_CREDIT_APPROVED",
    label: "Aprobado con crédito externo de otra entidad financiera",
  },
};

export const Oscuro: Story = { ...Tonos, globals: DARK };
export const Movil: Story = { ...Tonos, name: "Móvil", globals: MOBILE };
