import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button, Input, Select } from "antd";
import { useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField } from "@/components/ui/form-field";
import { DARK, MOBILE } from "@/stories/globals";

type Props = Partial<React.ComponentProps<typeof ActionModal>> & {
  withFields?: boolean;
  error?: string;
};

function Demo({ withFields = true, error, ...props }: Props) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Abrir</Button>
      <ActionModal
        title="Exonerar · Certificado laboral"
        okText="Exonerar"
        {...props}
        open={open}
        onSubmit={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      >
        {withFields && (
          <>
            <FormField id="motivo" label="Motivo" error={error}>
              {(ctl) => (
                <Select
                  {...ctl}
                  className="w-full"
                  placeholder="Elige un motivo"
                  options={[
                    { value: "NOT_APPLICABLE", label: "No aplica al comprador" },
                    { value: "BANK_WAIVED", label: "El banco no lo pide" },
                  ]}
                />
              )}
            </FormField>
            <FormField id="nota" label="Nota interna" optional="opcional, el comprador no la ve">
              {(ctl) => <Input.TextArea {...ctl} rows={3} />}
            </FormField>
          </>
        )}
      </ActionModal>
    </>
  );
}

const meta = {
  title: "Componentes/ActionModal",
  component: ActionModal,
  parameters: {
    docs: {
      story: { inline: false, iframeHeight: 460 },
      description: {
        component:
          'Modal de una acción: título, qué va a pasar, los campos y dos botones (cancelar y el verbo de la acción, nunca "Aceptar"). Confirma también con Enter. `danger` solo para acciones destructivas. Sirve directo el `handleSubmit` de React Hook Form.',
      },
    },
  },
  argTypes: {
    title: { control: "text" },
    description: { control: "text", description: "Qué pasa al confirmar." },
    okText: { control: "text", description: "Verbo de la acción." },
    cancelText: { control: "text" },
    danger: { control: "boolean" },
    loading: { control: "boolean" },
    okDisabled: { control: "boolean" },
  },
  args: { open: true, title: "", okText: "", onSubmit: () => {}, onCancel: () => {} },
  render: (args) => (
    <Demo
      description={args.description}
      danger={args.danger}
      loading={args.loading}
      okDisabled={args.okDisabled}
    />
  ),
} satisfies Meta<typeof ActionModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ConCampos: Story = { name: "Con campos" };
export const ConErrorEnUnCampo: Story = {
  name: "Con error en un campo",
  render: () => <Demo error="Elige el motivo." />,
};
export const Cargando: Story = { args: { loading: true } };
export const Deshabilitado: Story = {
  render: () => (
    <Demo
      title="Registrar radicación"
      okText="Registrar radicación"
      description="Prepara el paquete antes de radicar."
      okDisabled
      withFields={false}
    />
  ),
};
/** Destructiva: el botón de la acción va en `danger`. */
export const Destructiva: Story = {
  render: () => (
    <Demo
      title="¿Ya no quieres continuar?"
      okText="Cerrar mi solicitud"
      cancelText="Volver"
      description="Si cierras tu solicitud, tu asesor ya no podrá seguir con el trámite."
      danger
    />
  ),
};
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
