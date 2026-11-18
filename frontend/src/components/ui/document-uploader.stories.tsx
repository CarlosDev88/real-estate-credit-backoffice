import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { DocumentUploader, type UploadContext } from "@/components/ui/document-uploader";
import { ApiError } from "@/lib/api/errors";
import { DARK, MOBILE } from "@/stories/globals";

/** Subida simulada: avanza el progreso y termina (o falla) sin llamar a la API. */
function fakeUpload(fail?: string) {
  return (_file: File, { onProgress, signal }: UploadContext) =>
    new Promise<void>((resolve, reject) => {
      let percent = 0;
      const timer = setInterval(() => {
        percent += 20;
        onProgress(Math.min(percent, 100));
        if (percent >= 100) {
          clearInterval(timer);
          if (fail) reject(new ApiError(422, "FILE_REJECTED", fail));
          else resolve();
        }
      }, 300);
      signal.addEventListener("abort", () => {
        clearInterval(timer);
        reject(new DOMException("Cancelado", "AbortError"));
      });
    });
}

const PDF_AND_IMAGES = ["application/pdf", "image/jpeg", "image/png"] as const;

const meta = {
  title: "Componentes/DocumentUploader",
  component: DocumentUploader,
  parameters: {
    docs: {
      description: {
        component:
          'Carga de documentos: `Upload.Dragger` en web; "Tomar foto" y "Elegir archivo" en móvil. Valida tipo y tamaño antes de enviar, muestra el progreso y deja cancelar. El envío lo hace quien lo usa (`onUpload`); el componente solo pinta el estado.',
      },
    },
  },
  argTypes: {
    accept: { control: "object", description: "Tipos MIME permitidos (`allowed_mime_types`)." },
    maxBytes: { control: "number", description: "Tamaño máximo en bytes (`max_size_bytes`)." },
    replace: { control: "boolean", description: "Reemplazo de un documento rechazado." },
    disabled: { control: "boolean" },
    onUpload: { control: false },
  },
  args: { onUpload: fakeUpload(), accept: PDF_AND_IMAGES, maxBytes: 10 * 1024 * 1024 },
  decorators: [(Story) => <div className="max-w-lg">{Story()}</div>],
} satisfies Meta<typeof DocumentUploader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basico: Story = { name: "Básico" };
export const Reemplazo: Story = { args: { replace: true } };
export const Deshabilitado: Story = {
  args: { disabled: true },
  parameters: {
    // Un control inactivo no tiene mínimo de contraste (WCAG 1.4.3), pero axe no lo sabe:
    // el Dragger de Ant Design no marca `aria-disabled`.
    a11y: { config: { rules: [{ id: "color-contrast", enabled: false }] } },
  },
};
/** La API rechaza el archivo: el error queda en línea con "Reintentar". */
export const ErrorDeLaApi: Story = {
  name: "Error de la API",
  args: { onUpload: fakeUpload("El archivo está dañado o protegido con contraseña.") },
};
export const Oscuro: Story = { globals: DARK };
/** En móvil: "Tomar foto" y "Elegir archivo" en lugar de arrastrar. */
export const Movil: Story = { name: "Móvil", globals: MOBILE };
