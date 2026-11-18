"use client";

import { Button } from "antd";
import { useState } from "react";

import { PlusIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { MOBILE_QUERY } from "@/features/admin-common/list-params";
import { useDocumentsParams, type DocumentsView } from "@/features/admin-documents/list-params";
import { PreviewTab } from "@/features/admin-documents/preview-tab";
import { RequirementsTab } from "@/features/admin-documents/requirements-tab";
import { TypesTab } from "@/features/admin-documents/types-tab";
import { useMe } from "@/features/auth/queries";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const TAB_LABELS: Record<DocumentsView, string> = {
  tipos: "Tipos",
  requisitos: "Requisitos",
  "vista-previa": "Vista previa",
};
const CREATE_LABELS: Partial<Record<DocumentsView, string>> = {
  tipos: "Nuevo tipo",
  requisitos: "Nuevo requisito",
};

/**
 * `/admin/documentos` (REQ §6 vista 14): tipos documentales, requisitos por alcance y la
 * vista previa del checklist, en pestañas (`?vista=`).
 */
export function DocumentsScreen() {
  const { params, update, replace } = useDocumentsParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const [creating, setCreating] = useState(false);
  const perms = {
    canCreate: has("document_requirements.create"),
    canUpdate: has("document_requirements.update"),
    canPublish: has("document_requirements.publish"),
  };
  const view = params.vista;
  const createLabel = CREATE_LABELS[view];

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Documentos"
        description="Qué documentos se piden, a quién y para qué producto, y cómo quedaría el checklist de un caso."
        actions={
          perms.canCreate &&
          createLabel && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setCreating(true)}>
              {createLabel}
            </Button>
          )
        }
      />
      <ScrollTabs
        ariaLabel="Secciones de documentos"
        value={view}
        onChange={(key) => {
          setCreating(false);
          replace({ vista: key as DocumentsView });
        }}
        items={(Object.keys(TAB_LABELS) as DocumentsView[]).map((key) => ({
          key,
          label: TAB_LABELS[key],
        }))}
      />
      <div role="tabpanel" aria-label={TAB_LABELS[view]} className="grid gap-4">
        {view === "tipos" && (
          <TypesTab
            params={params}
            update={update}
            permissions={perms}
            mobile={mobile}
            creating={creating}
            onCloseCreate={() => setCreating(false)}
            onCreated={(type) => update({ abierto: type.id })}
          />
        )}
        {view === "requisitos" && (
          <RequirementsTab
            params={params}
            update={update}
            permissions={perms}
            mobile={mobile}
            creating={creating}
            onCloseCreate={() => setCreating(false)}
          />
        )}
        {view === "vista-previa" && <PreviewTab />}
      </div>
    </div>
  );
}
