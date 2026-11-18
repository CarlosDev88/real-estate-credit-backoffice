import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "antd";

import { Card, DataList, Datum } from "@/components/ui/card";
import { Money } from "@/components/ui/money";
import { StatusBadge } from "@/components/ui/status-badge";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/Card",
  component: Card,
  subcomponents: { DataList, Datum },
  parameters: {
    docs: {
      description: {
        component:
          'Tarjeta en el flujo de la página: borde y fondo, sin sombra. Es una `section` con el nombre de su título. `DataList` y `Datum` son la lista de datos de una ficha: en grilla (etiqueta arriba) o en línea (etiqueta a la izquierda, como el `.dl` del expediente). Un dato vacío muestra "—".',
      },
    },
  },
  argTypes: {
    title: { control: "text", description: "Título (`h2`) y nombre de la sección." },
    action: { control: false, description: "A la derecha del título: un total o un botón." },
    variant: {
      control: "inline-radio",
      options: ["backoffice", "portal"],
      description: "`portal`: radio `xl` y título de 20 px.",
    },
  },
  args: {
    title: "Datos del cliente",
    action: (
      <Button type="text" size="small">
        Editar
      </Button>
    ),
    children: (
      <DataList columns={3}>
        <Datum label="Nombres">Daniel Andrés</Datum>
        <Datum label="Apellidos">Mejía Castaño</Datum>
        <Datum label="Documento">
          <span className="font-mono">CC 1032445908</span>
        </Datum>
        <Datum label="Correo">daniel.mejia@correo.co</Datum>
        <Datum label="Teléfono">{null}</Datum>
        <Datum label="Origen">Feria de vivienda</Datum>
      </DataList>
    ),
  },
  decorators: [(Story) => <div className="max-w-3xl">{Story()}</div>],
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DatosEnGrilla: Story = { name: "Datos en grilla" };

/** Etiqueta a la izquierda y valor a la derecha (mockup `solicitud.html`, inmueble). */
export const DatosEnLinea: Story = {
  name: "Datos en línea",
  args: {
    title: "Inmueble",
    action: undefined,
    children: (
      <DataList layout="inline">
        <Datum label="Proyecto">Torres del Parque, apto 1204</Datum>
        <Datum label="Valor">
          <Money value={420_000_000} />
        </Datum>
        <Datum label="Estado">
          <StatusBadge kind="application" code="DOCUMENTS_REVIEW" label="Revisión documental" />
        </Datum>
        <Datum label="Matrícula inmobiliaria">{""}</Datum>
      </DataList>
    ),
  },
};

export const SinTitulo: Story = {
  name: "Sin título",
  args: { title: undefined, action: undefined, children: "Contenido de la tarjeta." },
};

export const Portal: Story = { args: { variant: "portal", title: "Contacto" } };

export const TextoLargo: Story = {
  name: "Texto largo",
  args: {
    title: "Observaciones del banco sobre la radicación número 3 de la solicitud",
    children: (
      <DataList>
        <Datum label="Comentario">
          El banco pide la certificación laboral con fecha de expedición no mayor a 30 días y el
          extracto bancario de los últimos tres meses con sello de la entidad.
        </Datum>
        <Datum label="Correo">
          correo.muy.largo.de.ejemplo.para.ver.el.corte@empresa-ejemplo.com.co
        </Datum>
      </DataList>
    ),
  },
};

export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
