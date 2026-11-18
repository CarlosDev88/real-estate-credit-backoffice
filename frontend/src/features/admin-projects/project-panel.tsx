"use client";

import { Button } from "antd";
import { useState } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import type { MetadataItem } from "@/features/admin-common/catalogs";
import { ReasonModal } from "@/features/admin-common/reason-modal";
import { actionsFor, type ProjectAction } from "@/features/admin-projects/actions";
import { ProjectFormModal } from "@/features/admin-projects/project-form-modal";
import { ProjectStatusBadge } from "@/features/admin-projects/projects-table";
import {
  useProject,
  useProjectTransition,
  type ProjectDetail,
} from "@/features/admin-projects/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateOnly, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

export interface ProjectPermissions {
  /** `projects.update`. */
  canEdit: boolean;
  /** El usuario es de una constructora (`scope.partner_id`). */
  partnerScoped: boolean;
}

/**
 * Se puede editar: no archivado y, para la constructora, solo en borrador (RF-17). Es una
 * pista para no ofrecer un botón que la API va a rechazar (`409 PROJECT_NOT_EDITABLE`).
 */
export function canEditProject(project: ProjectDetail, permissions: ProjectPermissions): boolean {
  if (!permissions.canEdit || project.status === "ARCHIVED") return false;
  return !permissions.partnerScoped || project.status === "DRAFT";
}

function ProjectData({
  project,
  statuses,
}: {
  project: ProjectDetail;
  statuses: readonly MetadataItem[];
}) {
  const city = [project.city.label, project.city.department_label].filter(Boolean).join(", ");
  return (
    <DataList layout="inline">
      <Datum label="Constructora">{project.partner.name}</Datum>
      <Datum label="Código">{project.code}</Datum>
      <Datum label="Estado">
        <ProjectStatusBadge status={project.status} statuses={statuses} />
      </Datum>
      <Datum label="Municipio">{city}</Datum>
      <Datum label="Dirección">{project.address}</Datum>
      <Datum label="Entrega estimada">{formatDateOnly(project.estimated_delivery_date)}</Datum>
      <Datum label="Descripción">
        {project.description && <span className="whitespace-pre-line">{project.description}</span>}
      </Datum>
      <Datum label="Creado por">{project.created_by.name}</Datum>
      <Datum label="Validado por">
        {project.validated_by &&
          `${project.validated_by.name} · ${formatDateTime(project.validated_at)}`}
      </Datum>
      <Datum label="Creado">{formatDateTime(project.created_at)}</Datum>
      <Datum label="Actualizado">{formatDateTime(project.updated_at)}</Datum>
    </DataList>
  );
}

/**
 * Panel del proyecto (`GET /projects/{id}`): datos, editar y los botones del flujo de
 * validación que manda la API (`available_actions`) para este usuario.
 */
export function ProjectPanel({
  projectId,
  statuses,
  permissions,
  onClose,
}: {
  projectId: string;
  statuses: readonly MetadataItem[];
  permissions: ProjectPermissions;
  onClose: () => void;
}) {
  const toast = useToast();
  const query = useProject(projectId);
  const transition = useProjectTransition(projectId);
  const [editing, setEditing] = useState(false);
  const [action, setAction] = useState<ProjectAction | null>(null);
  const project = query.data;
  const actions = project ? actionsFor(project.available_actions) : [];
  const editable = project ? canEditProject(project, permissions) : false;
  const primary = actions.find((a) => a.primary);

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando proyecto" blocks={[24, 24, 24, 24, 24, 24]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Este proyecto no existe o no es tuyo" : "No pudimos cargar el proyecto"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    body = <ProjectData project={query.data} statuses={statuses} />;
  }

  const footer = project && (actions.length > 0 || editable) && (
    <div className="flex flex-wrap gap-2">
      {actions
        .filter((a) => a !== primary)
        .map((a) => (
          <Button key={a.label} danger={a.danger} onClick={() => setAction(a)}>
            {a.label}
          </Button>
        ))}
      <div className="flex-1" />
      {editable && (
        <Button type={primary ? "default" : "primary"} onClick={() => setEditing(true)}>
          Editar
        </Button>
      )}
      {primary && (
        <Button type="primary" onClick={() => setAction(primary)}>
          {primary.label}
        </Button>
      )}
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Proyecto"
        title={project?.name ?? "Proyecto"}
        footer={footer || undefined}
        width={560}
      >
        {body}
      </SidePanel>
      {project && editing && (
        <ProjectFormModal
          project={project}
          partnerScoped={permissions.partnerScoped}
          onClose={() => setEditing(false)}
        />
      )}
      {project && action && (
        <ReasonModal
          title={action.title}
          description={action.description}
          okText={action.label}
          reasonRequired={action.reasonRequired}
          danger={action.danger}
          loading={transition.isPending}
          onConfirm={(reason) => transition.mutateAsync({ endpoint: action.endpoint, reason })}
          onDone={() => {
            toast.success({ title: action.toast });
            setAction(null);
          }}
          onCancel={() => setAction(null)}
        />
      )}
    </>
  );
}
