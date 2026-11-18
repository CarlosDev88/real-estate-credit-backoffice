import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button, Radio, Select } from "antd";
import { useState } from "react";

import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Card, DataList, Datum } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { SidePanel } from "@/components/ui/side-panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { DARK, MOBILE } from "@/stories/globals";

function Review() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Revisar documento</Button>
      <SidePanel
        open={open}
        onClose={() => setOpen(false)}
        eyebrow="Daniel Mejía · Titular"
        title="Certificado laboral"
        footer={
          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancelar</Button>
            <Button>Siguiente</Button>
            <Button type="primary">Aprobar documento</Button>
          </div>
        }
      >
        <div className="grid content-start gap-5">
          <Card title="Archivo">
            <DataList layout="inline">
              <Datum label="Nombre">certificado-laboral.pdf</Datum>
              <Datum label="Análisis">
                <StatusBadge kind="fileScan" code="CLEAN" label="Sin amenazas" />
              </Datum>
            </DataList>
          </Card>
          <Radio.Group
            defaultValue="APPROVED"
            options={[
              { value: "APPROVED", label: "Aprobar" },
              { value: "REJECTED", label: "Rechazar" },
            ]}
          />
        </div>
      </SidePanel>
    </>
  );
}

function Filters() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Filtros (1)</Button>
      <BottomSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Filtros"
        closeLabel="Cerrar filtros"
        footer={
          <div className="flex gap-2">
            <Button size="large" className="flex-1">
              Limpiar
            </Button>
            <Button size="large" type="primary" className="flex-1" onClick={() => setOpen(false)}>
              Ver resultados
            </Button>
          </div>
        }
      >
        <FormField id="banco" label="Banco">
          {(ctl) => (
            <Select
              {...ctl}
              size="large"
              className="w-full"
              defaultValue="all"
              options={[
                { value: "all", label: "Todos" },
                { value: "b1", label: "Banco de ejemplo" },
              ]}
            />
          )}
        </FormField>
      </BottomSheet>
    </>
  );
}

function Panels() {
  return <Review />;
}

const meta = {
  title: "Componentes/Paneles",
  component: Panels,
  subcomponents: { SidePanel, BottomSheet },
  parameters: {
    layout: "fullscreen",
    docs: {
      story: { inline: false, iframeHeight: 560 },
      description: {
        component:
          "`SidePanel`: panel lateral de revisión o detalle, a la derecha sin dejar la vista (pantalla completa en móvil); el título es un `h2` que se puede enfocar al abrir. `BottomSheet`: hoja inferior de móvil para filtros o una acción corta. Los dos mantienen el foco adentro, lo devuelven al cerrar y se vacían al cerrarse.",
      },
    },
  },
} satisfies Meta<typeof Panels>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PanelLateral: Story = { name: "Panel lateral" };
export const PanelLateralOscuro: Story = { name: "Panel lateral · oscuro", globals: DARK };
export const PanelLateralMovil: Story = { name: "Panel lateral · móvil", globals: MOBILE };
export const HojaInferior: Story = {
  name: "Hoja inferior",
  render: () => <Filters />,
  globals: MOBILE,
};
export const HojaInferiorOscura: Story = {
  name: "Hoja inferior · oscuro",
  render: () => <Filters />,
  globals: { ...MOBILE, ...DARK },
};
