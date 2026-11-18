import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "antd";
import { useState } from "react";

import { DocumentViewer, type ViewerFile } from "@/components/ui/document-viewer";
import { DARK, MOBILE } from "@/stories/globals";

// Archivos de muestra de .storybook/public (sin datos reales).
const PDF: ViewerFile = {
  name: "certificado-laboral.pdf",
  kind: "pdf",
  url: "muestra.pdf",
  size: "1 KB",
};
const IMAGE: ViewerFile = {
  name: "cedula-frente.svg",
  kind: "image",
  url: "cedula.svg",
  size: "1 KB",
};
const MISSING: ViewerFile = { name: "no-existe.pdf", kind: "pdf", url: "no-existe.pdf" };

function Viewer({ file, note }: { file: ViewerFile; note?: string }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Ver {file.name}</Button>
      <DocumentViewer open={open} file={file} note={note} onClose={() => setOpen(false)} />
    </>
  );
}

const meta = {
  title: "Componentes/DocumentViewer",
  component: DocumentViewer,
  parameters: {
    layout: "fullscreen",
    docs: {
      story: { inline: false, iframeHeight: 560 },
      description: {
        component:
          "Visor sobre PDF.js: zoom, páginas, girar y descargar por URL prefirmada. Las imágenes se muestran directo. Se abre en un diálogo que mantiene el foco y lo devuelve al cerrar.",
      },
    },
  },
  argTypes: {
    file: { control: false, description: "`name`, `kind` (`pdf` o `image`), `url` y `size`." },
    note: { control: "text", description: "Nota al pie (por ejemplo, cuándo vence el enlace)." },
  },
  args: { open: true, file: PDF, onClose: () => {} },
  render: (args) => <Viewer file={args.file ?? PDF} note={args.note as string | undefined} />,
} satisfies Meta<typeof DocumentViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Pdf: Story = {
  name: "PDF",
  args: { note: "El enlace de descarga vence en 5 minutos." },
};
export const Imagen: Story = { args: { file: IMAGE } };
/** El archivo no se pudo abrir: error en el visor, con la descarga como salida. */
export const NoSePudoAbrir: Story = { name: "Error", args: { file: MISSING } };
export const Oscuro: Story = { globals: DARK };
export const Movil: Story = { name: "Móvil", args: { file: IMAGE }, globals: MOBILE };
