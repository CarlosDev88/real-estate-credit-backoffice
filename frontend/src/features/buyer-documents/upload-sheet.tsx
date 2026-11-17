"use client";

import { Drawer, Input, Modal } from "antd";
import { useId, useState } from "react";
import type { ReactNode } from "react";

import { DocumentUploader } from "@/components/ui/document-uploader";
import { useAfterUpload, uploadSlotFile } from "@/features/buyer-documents/documents-queries";
import { requirementsText } from "@/features/buyer-documents/slot-format";
import { usePortal } from "@/features/buyer-portal/portal-context";
import type { BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useToast } from "@/providers/toast";

const svg = { viewBox: "0 0 20 20", fill: "currentColor", "aria-hidden": true } as const;

function Requirement({ icon, children }: { icon: string; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <svg {...svg} width={16} height={16} className="text-text-tertiary mt-0.5 flex-none">
        <path d={icon} />
      </svg>
      <span>{children}</span>
    </li>
  );
}

const ICON_FILE = "M5 2h7l4 4v12H5V2Zm7 1.5V7h3.5L12 3.5Z";
const ICON_INFO = "M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1 4h2v2H9V5Zm0 4h2v6H9V9Z";

/** Hoy en Bogotá (`YYYY-MM-DD`): una fecha futura la rechaza la API. */
function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());
}

function SheetBody({ slot, onDone }: { slot: BuyerDocumentSlot; onDone: () => void }) {
  const { applicationId } = usePortal();
  const afterUpload = useAfterUpload(applicationId);
  const toast = useToast();
  const id = useId();
  const [documentDate, setDocumentDate] = useState("");
  const requirements = requirementsText(slot);
  const holder = slot.participant
    ? `${slot.participant.full_name} · ${slot.participant.role_label}`
    : null;

  return (
    <div className="grid gap-4">
      {holder && <p className="text-text-tertiary m-0 -mt-2 text-sm">{holder}</p>}
      <ul className="bg-bg-subtle text-text-secondary m-0 grid list-none gap-1.5 rounded-lg p-3 text-sm">
        {requirements && <Requirement icon={ICON_FILE}>{requirements}</Requirement>}
        {slot.document_type.description && (
          <Requirement icon={ICON_INFO}>{slot.document_type.description}</Requirement>
        )}
      </ul>

      {slot.validity_days !== null && (
        <div className="grid max-w-80 gap-1.5">
          <label htmlFor={`${id}-date`} className="text-sm font-medium">
            Fecha del documento <span className="text-text-tertiary font-normal">(opcional)</span>
          </label>
          <Input
            id={`${id}-date`}
            type="date"
            size="large"
            max={today()}
            value={documentDate}
            aria-describedby={`${id}-date-help`}
            onChange={(event) => setDocumentDate(event.target.value)}
          />
          <p id={`${id}-date-help`} className="text-text-tertiary m-0 text-xs">
            La fecha de expedición o del periodo. Con ella calculamos hasta cuándo sirve.
          </p>
        </div>
      )}

      <DocumentUploader
        accept={slot.allowed_mime_types}
        maxBytes={slot.max_size_bytes}
        replace={!!slot.current_file}
        onUpload={async (file, { onProgress, signal }) => {
          await uploadSlotFile({
            slotId: slot.id,
            file,
            documentDate: documentDate || null,
            onProgress,
            signal,
          });
          toast.success({
            title: "Documento subido",
            message: `${slot.label}: tu asesor lo revisará pronto.`,
          });
          await afterUpload();
          onDone();
        }}
      />
    </div>
  );
}

/**
 * Hoja de carga (mockup `portal.html`): hoja inferior en móvil y modal en escritorio.
 * Ant Design atrapa el foco adentro, cierra con Escape y lo devuelve al botón que la abrió.
 */
export function UploadSheet({
  slot,
  onClose,
}: {
  slot: BuyerDocumentSlot | null;
  onClose: () => void;
}) {
  const isMobile = useMediaQuery("(max-width: 720px)");
  const title = slot?.label;
  const body = slot ? <SheetBody key={slot.id} slot={slot} onDone={onClose} /> : null;

  if (isMobile) {
    return (
      <Drawer
        open={slot !== null}
        onClose={onClose}
        placement="bottom"
        title={title}
        size="auto"
        closable={{ "aria-label": "Cerrar" }}
        destroyOnHidden
        styles={{ body: { paddingBottom: "calc(24px + env(safe-area-inset-bottom))" } }}
      >
        {body}
      </Drawer>
    );
  }
  return (
    <Modal
      open={slot !== null}
      onCancel={onClose}
      title={title}
      footer={null}
      destroyOnHidden
      closable={{ "aria-label": "Cerrar" }}
    >
      {body}
    </Modal>
  );
}
