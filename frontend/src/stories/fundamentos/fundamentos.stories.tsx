import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import {
  ControlHeights,
  Palettes,
  RadiusScale,
  SemanticColors,
  ShadowRule,
  ShadowScale,
  SpacingScale,
  ToneLegend,
  ToneMapTable,
  ToneRule,
  TypeFamilies,
  TypeScale,
} from "./blocks";
import {
  DataFormatExample,
  DestructiveExample,
  LabelExample,
  LinkExample,
  PrimaryActionExample,
  SentenceCaseExample,
} from "./redaccion";

/**
 * Bloques de las páginas de fundamentos (las MDX de esta carpeta los muestran con `<Story>`).
 * No salen en la barra lateral (`!dev`), pero sí corren en `pnpm test:storybook`, con la
 * revisión de accesibilidad, como cualquier otro story.
 */
const meta = {
  title: "Fundamentos/Bloques",
  tags: ["!dev", "!autodocs"],
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const ColoresSemanticos: Story = { render: () => <SemanticColors /> };
export const Paletas: Story = { render: () => <Palettes /> };
export const Familias: Story = { render: () => <TypeFamilies /> };
export const EscalaTipografica: Story = { render: () => <TypeScale /> };
export const Espaciado: Story = { render: () => <SpacingScale /> };
export const AlturasDeControl: Story = { render: () => <ControlHeights /> };
export const Radios: Story = { render: () => <RadiusScale /> };
export const Sombras: Story = { render: () => <ShadowScale /> };
export const SombrasRegla: Story = { render: () => <ShadowRule /> };
export const TonosLeyenda: Story = { render: () => <ToneLegend /> };
export const TonosPorCodigo: Story = { render: () => <ToneMapTable /> };
export const TonosRegla: Story = { render: () => <ToneRule /> };
export const RedaccionMayusculas: Story = { render: () => <SentenceCaseExample /> };
export const RedaccionEtiquetas: Story = { render: () => <LabelExample /> };
export const RedaccionEnlaces: Story = {
  render: () => <LinkExample />,
  parameters: {
    // "Así no" muestra a propósito un enlace sin subrayar: es lo que la regla prohíbe.
    a11y: { config: { rules: [{ id: "link-in-text-block", enabled: false }] } },
  },
};
export const RedaccionFormatos: Story = { render: () => <DataFormatExample /> };
export const RedaccionAccionPrincipal: Story = { render: () => <PrimaryActionExample /> };
export const RedaccionDestructivo: Story = { render: () => <DestructiveExample /> };
