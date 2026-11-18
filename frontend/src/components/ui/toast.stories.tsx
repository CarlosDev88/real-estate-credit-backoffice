import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "antd";

import { DARK, MOBILE } from "@/stories/globals";
import { useToast, type ToastOptions } from "@/providers/toast";

function ToastButtons() {
  const toast = useToast();
  const samples: [string, ToastOptions][] = [
    ["Éxito", { tone: "success", title: "Documento aprobado", message: "Cédula de Daniel Mejía." }],
    ["Información", { tone: "info", title: "El banco recibió la radicación" }],
    ["Advertencia", { tone: "warning", title: "El acceso del comprador vence mañana" }],
    [
      "Error",
      {
        tone: "danger",
        title: "Alguien cambió esta solicitud",
        message: "Recarga para ver los cambios antes de seguir.",
        action: { label: "Recargar", onClick: () => {} },
      },
    ],
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {samples.map(([label, options]) => (
        <Button key={label} onClick={() => toast.show(options)}>
          {label}
        </Button>
      ))}
    </div>
  );
}

const meta = {
  title: "Componentes/Toasts",
  component: ToastButtons,
  parameters: {
    docs: {
      description: {
        component:
          '`useToast()` (de `providers/toast`): éxito, información y advertencia se cierran a los 5 s (con pausa al pasar el mouse); los errores se quedan hasta cerrarlos. Máximo 3. Arriba a la derecha en web y abajo en móvil. `role="status"` para éxito e información y `role="alert"` para errores. Los errores de escritura de la API ya salen solos (MutationCache global).',
      },
    },
  },
} satisfies Meta<typeof ToastButtons>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Tonos: Story = {};
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", globals: MOBILE };
