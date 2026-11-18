import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { DARK, MOBILE } from "@/stories/globals";

const meta = {
  title: "Componentes/Estados de carga y error",
  component: ErrorState,
  subcomponents: { LoadingState },
  parameters: {
    docs: {
      description: {
        component:
          '`LoadingState`: esqueleto con la forma de lo que viene (un bloque por tarjeta) o una línea de texto. `ErrorState`: error al cargar, siempre con "Reintentar" y `role="alert"`, en tres formas: `inline` (dentro de una tarjeta), `banner` (una pestaña o lista) y `page` (la vista entera). El vacío es `EmptyState`.',
      },
    },
  },
  argTypes: {
    title: { control: "text", description: "Qué no se pudo cargar." },
    message: { control: "text", description: "Detalle (mensaje de la API)." },
    variant: { control: "inline-radio", options: ["inline", "banner", "page"] },
    retrying: { control: "boolean", description: "Reintentando: el botón muestra que trabaja." },
    titleAs: { control: "inline-radio", options: ["p", "h1", "h2"] },
  },
  args: {
    title: "No pudimos cargar las radicaciones",
    message: "No hay conexión con el servidor. Revisa tu red e inténtalo de nuevo.",
    onRetry: () => {},
  },
  decorators: [(Story) => <div className="max-w-2xl">{Story()}</div>],
} satisfies Meta<typeof ErrorState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ErrorBanner: Story = { name: "Error: banner" };
export const ErrorEnLinea: Story = {
  name: "Error: en línea",
  render: (args) => (
    <Card title="Respuestas del banco">
      <ErrorState {...args} variant="inline" title="No pudimos cargar las respuestas." />
    </Card>
  ),
};
export const ErrorDePagina: Story = {
  name: "Error: página",
  args: { variant: "page", titleAs: "h1", title: "No pudimos cargar tu solicitud" },
};
export const Reintentando: Story = { args: { retrying: true } };
export const CargandoTarjetas: Story = {
  name: "Cargando: tarjetas",
  render: () => <LoadingState label="Cargando radicaciones" blocks={[128, 96]} />,
};
export const CargandoTexto: Story = {
  name: "Cargando: texto",
  render: () => <LoadingState label="Cargando las respuestas…" blocks={[]} />,
};
export const CargandoPortal: Story = {
  name: "Cargando: portal",
  render: () => <LoadingState variant="portal" blocks={[112, 112]} />,
};
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { ...ErrorDePagina, name: "Móvil", globals: MOBILE };
