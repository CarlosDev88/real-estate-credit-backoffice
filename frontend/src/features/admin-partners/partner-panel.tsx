"use client";

import { Button, Pagination } from "antd";
import { useState } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { PROJECT_STATUS_CATALOG, useCatalog } from "@/features/admin-common/catalogs";
import { partnerName } from "@/features/admin-common/partner-select";
import { ReasonModal } from "@/features/admin-common/reason-modal";
import { MemberModal } from "@/features/admin-partners/member-modal";
import { PartnerFormModal } from "@/features/admin-partners/partner-form-modal";
import {
  MEMBERS_PAGE_SIZE,
  useMembers,
  usePartner,
  useSetPartnerActive,
  type PartnerDetail,
  type PartnerMetrics,
} from "@/features/admin-partners/queries";
import { PartnerStatusBadge } from "@/features/admin-partners/status";
import { isApiError } from "@/lib/api/errors";
import { formatDateOnly, formatDateTime, formatInteger } from "@/lib/format";
import { useToast } from "@/providers/toast";

export interface PartnerPermissions {
  /** `partners.update`. */
  canEdit: boolean;
  /** `partners.manage_status`. */
  canManageStatus: boolean;
  /** `partner_members.read`. */
  canReadMembers: boolean;
  /** `partner_members.create`. */
  canAddMembers: boolean;
  /** `users.read`: agregar un usuario existente (si no, solo invitar por correo). */
  canPickUsers: boolean;
}

type Modal = "edit" | "status" | "member" | null;

/** Proyectos por estado (etiquetas del catálogo `project_status`) y miembros activos. */
function Metrics({ metrics }: { metrics: PartnerMetrics }) {
  const statuses = useCatalog(PROJECT_STATUS_CATALOG);
  const byStatus = metrics.projects_by_status ?? {};
  return (
    <section aria-labelledby="partner-metrics" className="grid gap-2">
      <h3 id="partner-metrics" className="m-0 text-base font-semibold">
        Proyectos y miembros
      </h3>
      <dl className="m-0 grid grid-cols-2 gap-2 min-[600px]:grid-cols-5">
        {statuses.items.map((status) => (
          <div
            key={status.code}
            className="border-border-default bg-bg-subtle grid gap-0.5 rounded-md border px-3 py-2"
          >
            <dt className="text-text-tertiary text-xs">{status.label}</dt>
            <dd className="m-0 text-lg font-semibold tabular-nums">
              {formatInteger(byStatus[status.code] ?? 0)}
            </dd>
          </div>
        ))}
        <div className="border-border-default bg-bg-subtle grid gap-0.5 rounded-md border px-3 py-2">
          <dt className="text-text-tertiary text-xs">Miembros activos</dt>
          <dd className="m-0 text-lg font-semibold tabular-nums">
            {formatInteger(metrics.active_members ?? 0)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Members({
  partner,
  canAdd,
  onAdd,
}: {
  partner: PartnerDetail;
  canAdd: boolean;
  onAdd: () => void;
}) {
  const [page, setPage] = useState(1);
  const members = useMembers(partner.id, page, true);
  const rows = members.data?.items ?? [];

  let body;
  if (members.isPending) {
    body = <LoadingState label="Cargando miembros" blocks={[44, 44]} />;
  } else if (members.isError) {
    body = (
      <ErrorState
        variant="inline"
        title="No pudimos cargar los miembros"
        onRetry={() => void members.refetch()}
        retrying={members.isFetching}
      />
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        size="sm"
        title="Todavía no tiene miembros"
        description={canAdd ? "Invita a las personas de la constructora." : undefined}
      />
    );
  } else {
    body = (
      <ul aria-label="Miembros" className="m-0 grid list-none gap-0 p-0">
        {rows.map((member) => (
          <li
            key={member.id}
            className="border-border-default grid gap-0.5 border-b py-2 text-sm last:border-b-0"
          >
            <div className="flex items-center gap-2">
              <span className="min-w-0 truncate font-medium">
                {member.user.name || member.user.email}
              </span>
              <span className="ml-auto">
                <PartnerStatusBadge status={member.ended_at ? "INACTIVE" : member.status} />
              </span>
            </div>
            <div className="text-text-secondary flex flex-wrap gap-x-2">
              <span className="truncate">{member.user.email}</span>
              {member.job_title && <span>· {member.job_title}</span>}
              <span className="text-text-tertiary ml-auto whitespace-nowrap">
                {member.ended_at
                  ? `${formatDateOnly(member.started_at)} – ${formatDateOnly(member.ended_at)}`
                  : `Desde ${formatDateOnly(member.started_at)}`}
              </span>
            </div>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <section aria-labelledby="partner-members" className="grid gap-2">
      <div className="flex items-center gap-2">
        <h3 id="partner-members" className="m-0 flex-1 text-base font-semibold">
          Miembros
        </h3>
        {canAdd && (
          <Button size="small" onClick={onAdd}>
            Agregar miembro
          </Button>
        )}
      </div>
      {body}
      {members.data && members.data.total > MEMBERS_PAGE_SIZE && (
        <Pagination
          size="small"
          simple
          current={page}
          pageSize={MEMBERS_PAGE_SIZE}
          total={members.data.total}
          onChange={setPage}
          className="justify-self-end"
        />
      )}
    </section>
  );
}

/** Panel lateral de la constructora (`GET /partners/{id}`): datos, métricas y miembros. */
export function PartnerPanel({
  partnerId,
  permissions,
  onClose,
}: {
  partnerId: string;
  permissions: PartnerPermissions;
  onClose: () => void;
}) {
  const toast = useToast();
  const query = usePartner(partnerId);
  const setActive = useSetPartnerActive(partnerId);
  const [modal, setModal] = useState<Modal>(null);
  const partner = query.data;
  const activate = partner?.status === "INACTIVE";
  const close = () => setModal(null);

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando constructora" blocks={[24, 24, 24, 24, 80]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Esta constructora ya no existe" : "No pudimos cargar la constructora"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    const data = query.data;
    body = (
      <div className="grid gap-6">
        <DataList layout="inline">
          <Datum label="Razón social">{data.legal_name}</Datum>
          <Datum label="Nombre comercial">{data.trade_name}</Datum>
          <Datum label="NIT">{data.tax_id}</Datum>
          <Datum label="Estado">
            <PartnerStatusBadge status={data.status} />
          </Datum>
          <Datum label="Contacto">{data.contact_name}</Datum>
          <Datum label="Correo del contacto">{data.contact_email}</Datum>
          <Datum label="Teléfono del contacto">{data.contact_phone}</Datum>
          <Datum label="Creada">{formatDateTime(data.created_at)}</Datum>
          <Datum label="Actualizada">{formatDateTime(data.updated_at)}</Datum>
        </DataList>
        <Metrics metrics={data.metrics as PartnerMetrics} />
        {permissions.canReadMembers && (
          <Members
            partner={data}
            canAdd={permissions.canAddMembers && data.status === "ACTIVE"}
            onAdd={() => setModal("member")}
          />
        )}
      </div>
    );
  }

  const footer = partner && (permissions.canEdit || permissions.canManageStatus) && (
    <div className="flex flex-wrap gap-2">
      {permissions.canManageStatus && (
        <Button danger={!activate} onClick={() => setModal("status")}>
          {activate ? "Activar" : "Desactivar"}
        </Button>
      )}
      <div className="flex-1" />
      {permissions.canEdit && (
        <Button type="primary" onClick={() => setModal("edit")}>
          Editar
        </Button>
      )}
    </div>
  );
  const label = partner ? partnerName(partner) : "";

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Constructora"
        title={label || "Constructora"}
        footer={footer || undefined}
        width={600}
      >
        {body}
      </SidePanel>
      {partner && modal === "edit" && <PartnerFormModal partner={partner} onClose={close} />}
      {partner && modal === "member" && (
        <MemberModal
          partnerId={partner.id}
          partnerLabel={label}
          canPickUsers={permissions.canPickUsers}
          onClose={close}
        />
      )}
      {partner && modal === "status" && (
        <ReasonModal
          title={activate ? "Activar constructora" : "Desactivar constructora"}
          description={
            activate
              ? `Los miembros de ${label} vuelven a trabajar en sus proyectos.`
              : `Mientras esté inactiva, sus miembros no pueden crear, editar ni enviar proyectos, y no se le agregan miembros ni proyectos nuevos.`
          }
          okText={activate ? "Activar" : "Desactivar"}
          reasonRequired={!activate}
          danger={!activate}
          loading={setActive.isPending}
          onConfirm={(reason) => setActive.mutateAsync({ active: activate, reason })}
          onDone={() => {
            toast.success({
              title: activate ? "Constructora activada" : "Constructora desactivada",
            });
            close();
          }}
          onCancel={close}
        />
      )}
    </>
  );
}
