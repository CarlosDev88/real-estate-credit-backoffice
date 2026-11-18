"use client";

import { Button } from "antd";
import { useEffect, useMemo, useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { ErrorState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import { formatOrdering, parseOrdering } from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import {
  DEFAULT_ORDERING,
  INVITATION_SORT_FIELDS,
  type AdminUsersParams,
} from "@/features/admin-users/list-params";
import {
  refName,
  roleName,
  useInvitationsList,
  useResendInvitation,
  useRevokeInvitation,
  type Invitation,
  type Role,
} from "@/features/admin-users/queries";
import { INVITATION_STATUSES, statusOf } from "@/features/admin-users/status";
import { isApiError } from "@/lib/api/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

const CLEARED: Partial<AdminUsersParams> = { role: "", status: "" };
const STATUS_OPTIONS: FilterOption[] = INVITATION_STATUSES.map(({ value, label }) => ({
  value,
  label,
}));
const DASH = <span className="text-text-tertiary">—</span>;

export function InvitationStatusBadge({ status }: { status: string }) {
  const option = statusOf(INVITATION_STATUSES, status);
  return <ToneBadge tone={option.tone}>{option.label}</ToneBadge>;
}

/** Se reenvía una invitación pendiente o vencida (la API revoca el enlace anterior). */
export const canResend = (invitation: Invitation) =>
  invitation.status === "PENDING" || invitation.status === "EXPIRED";
/** Se revoca una invitación pendiente. */
export const canRevoke = (invitation: Invitation) => invitation.status === "PENDING";

export interface InvitationPermissions {
  /** `invitations.create`: invitar y reenviar. */
  canCreate: boolean;
  /** `invitations.revoke`. */
  canRevoke: boolean;
}

interface RowActionsProps {
  invitation: Invitation;
  permissions: InvitationPermissions;
  onResend: (invitation: Invitation) => void;
  onRevoke: (invitation: Invitation) => void;
  resending: boolean;
}

function RowActions({ invitation, permissions, onResend, onRevoke, resending }: RowActionsProps) {
  const resend = permissions.canCreate && canResend(invitation);
  const revoke = permissions.canRevoke && canRevoke(invitation);
  if (!resend && !revoke) return DASH;
  return (
    <div className="flex gap-1">
      {resend && (
        <Button
          size="small"
          loading={resending}
          onClick={() => onResend(invitation)}
          aria-label={`Reenviar la invitación de ${invitation.email}`}
        >
          Reenviar
        </Button>
      )}
      {revoke && (
        <Button
          size="small"
          danger
          onClick={() => onRevoke(invitation)}
          aria-label={`Revocar la invitación de ${invitation.email}`}
        >
          Revocar
        </Button>
      )}
    </div>
  );
}

const helper = dataColumns<Invitation>();

function makeColumns(
  roles: readonly Role[] | undefined,
  actions: Omit<RowActionsProps, "invitation" | "resending"> & { resendingId: string | null },
) {
  return helper.columns([
    helper.accessor((row) => row.email, {
      id: "email",
      header: "Correo",
      cell: ({ row }) => (
        <span className="block max-w-[260px] truncate font-medium">{row.original.email}</span>
      ),
    }),
    helper.display({
      id: "role",
      header: "Rol",
      cell: ({ row }) => <span className="text-sm">{roleName(roles, row.original.role)}</span>,
    }),
    helper.display({
      id: "partner",
      header: "Constructora",
      cell: ({ row }) => (
        <span className="block max-w-[180px] truncate text-sm">
          {refName(row.original.partner) ?? DASH}
        </span>
      ),
    }),
    helper.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => <InvitationStatusBadge status={row.original.status} />,
    }),
    helper.display({
      id: "invited_by",
      header: "Invitó",
      cell: ({ row }) => (
        <span className="block max-w-[180px] truncate text-sm">
          {refName(row.original.invited_by) ?? DASH}
        </span>
      ),
    }),
    helper.accessor((row) => row.expires_at, {
      id: "expires_at",
      header: "Vence",
      cell: ({ row }) => (
        <time
          dateTime={row.original.expires_at}
          title={formatDateTime(row.original.expires_at) ?? undefined}
          className="text-text-secondary text-sm"
        >
          {formatDate(row.original.expires_at)}
        </time>
      ),
    }),
    helper.accessor((row) => row.created_at, {
      id: "created_at",
      header: "Enviada",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.created_at)}</span>
      ),
    }),
    helper.display({
      id: "actions",
      header: "Acciones",
      cell: ({ row }) => (
        <RowActions
          invitation={row.original}
          permissions={actions.permissions}
          onResend={actions.onResend}
          onRevoke={actions.onRevoke}
          resending={actions.resendingId === row.original.id}
        />
      ),
    }),
  ]);
}

interface InvitationsTabProps {
  params: AdminUsersParams;
  update: (patch: Partial<AdminUsersParams>) => void;
  roles: readonly Role[] | undefined;
  rolesLoading: boolean;
  permissions: InvitationPermissions;
  mobile: boolean;
}

/** Pestaña "Invitaciones": `GET /invitations` con rol y estado; reenviar y revocar. */
export function InvitationsTab({
  params,
  update,
  roles,
  rolesLoading,
  permissions,
  mobile,
}: InvitationsTabProps) {
  const toast = useToast();
  const list = useInvitationsList(params);
  const resend = useResendInvitation();
  const revoke = useRevokeInvitation();
  const [revoking, setRevoking] = useState<Invitation | null>(null);

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const onResend = (invitation: Invitation) =>
    resend.mutate(invitation.id, {
      onSuccess: () =>
        toast.success({
          title: "Invitación reenviada",
          message: `Le llegó un enlace nuevo a ${invitation.email}; el anterior ya no sirve.`,
        }),
    });
  const resendingId = resend.isPending ? (resend.variables ?? null) : null;
  const columns = makeColumns(roles, {
    permissions,
    onResend,
    onRevoke: setRevoking,
    resendingId,
  });

  const confirmRevoke = () => {
    if (!revoking) return;
    revoke.mutate(revoking.id, {
      onSuccess: () => {
        toast.success({ title: "Invitación revocada" });
        setRevoking(null);
      },
    });
  };

  const clear = () => update(CLEARED);
  const filtered = params.role !== "" || params.status !== "";
  const roleOptions = useMemo<FilterOption[]>(
    () => (roles ?? []).map((role) => ({ value: role.code, label: role.name })),
    [roles],
  );
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando invitaciones" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las invitaciones"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay invitaciones con estos filtros"
        description="Prueba con otro rol o estado, o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Todavía no hay invitaciones"
        description={
          permissions.canCreate
            ? "Invita a alguien del equipo: le llega un enlace para definir su contraseña."
            : "Aquí verás las invitaciones enviadas."
        }
      />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Invitaciones"
        rows={rows}
        getRowId={(row) => row.id}
        busy={busy}
        renderCard={(invitation) => (
          <>
            <div className="flex items-center gap-2">
              <span className="min-w-0 truncate font-medium">{invitation.email}</span>
              <span className="ml-auto">
                <InvitationStatusBadge status={invitation.status} />
              </span>
            </div>
            <div className="text-text-secondary flex gap-2 text-sm">
              <span className="min-w-0 truncate">
                {[roleName(roles, invitation.role), refName(invitation.partner)]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              <span className="ml-auto whitespace-nowrap">
                Vence {formatDate(invitation.expires_at)}
              </span>
            </div>
            <RowActions
              invitation={invitation}
              permissions={permissions}
              onResend={onResend}
              onRevoke={setRevoking}
              resending={resendingId === invitation.id}
            />
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Invitaciones"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        sorting={parseOrdering(params.ordering, INVITATION_SORT_FIELDS, DEFAULT_ORDERING)}
        sortableFields={INVITATION_SORT_FIELDS}
        onSort={(sorting: TableSort) => update({ ordering: formatOrdering(sorting) })}
        busy={busy}
        stickyColumn="email"
        minWidth={1080}
      />
    );
  }

  return (
    <>
      <section
        aria-label="Listado de invitaciones"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          selects={[
            {
              key: "role",
              label: "Rol",
              value: params.role,
              options: roleOptions,
              loading: rolesLoading,
            },
            { key: "status", label: "Estado", value: params.status, options: STATUS_OPTIONS },
          ]}
          onSelect={(key, value) => update({ [key]: value })}
          onClear={clear}
          mobile={mobile}
        />
        {body}
        {list.data && rows.length > 0 && (
          <ListPagination
            page={params.page}
            pageSize={params.page_size}
            total={list.data.total}
            itemsLabel="Invitaciones"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>

      <ActionModal
        open={revoking !== null}
        title="Revocar invitación"
        description={
          revoking
            ? `El enlace que le enviamos a ${revoking.email} deja de servir. Puedes invitarle de nuevo después.`
            : undefined
        }
        okText="Revocar"
        danger
        loading={revoke.isPending}
        onSubmit={confirmRevoke}
        onCancel={() => setRevoking(null)}
      />
    </>
  );
}
