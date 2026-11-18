"use client";

import { Button } from "antd";
import { useState } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { refName, useUser, type Role, type User } from "@/features/admin-users/queries";
import { EditUserModal, RolesModal, StatusModal } from "@/features/admin-users/user-modals";
import { rolesText, UserStatusBadge } from "@/features/admin-users/users-table";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

export interface UserPermissions {
  /** `users.update`. */
  canEdit: boolean;
  /** `roles.assign` (y `roles.read` para listar los roles). */
  canAssignRoles: boolean;
  /** `users.manage_status`. */
  canManageStatus: boolean;
  /** Id del usuario actual: no puede desactivarse a sí mismo. */
  meId: string | null;
}

type Modal = "edit" | "roles" | "status" | null;

function UserDetail({ user, roles }: { user: User; roles: readonly Role[] | undefined }) {
  return (
    <DataList layout="inline">
      <Datum label="Correo">{user.email}</Datum>
      <Datum label="Teléfono">{user.phone}</Datum>
      <Datum label="Estado">
        <UserStatusBadge status={user.status} />
      </Datum>
      <Datum label="Roles">{rolesText(user, roles)}</Datum>
      <Datum label="Constructora">{refName(user.partner)}</Datum>
      <Datum label="Último ingreso">{formatDateTime(user.last_login) ?? "Nunca"}</Datum>
      <Datum label="Creado">{formatDateTime(user.created_at)}</Datum>
      <Datum label="Actualizado">{formatDateTime(user.updated_at)}</Datum>
    </DataList>
  );
}

/** Panel lateral del usuario (`GET /users/{id}`) con sus acciones. */
export function UserPanel({
  userId,
  roles,
  permissions,
  onClose,
}: {
  userId: string;
  roles: readonly Role[] | undefined;
  permissions: UserPermissions;
  onClose: () => void;
}) {
  const query = useUser(userId);
  const [modal, setModal] = useState<Modal>(null);
  const user = query.data;
  const self = user !== undefined && user.id === permissions.meId;
  // Activar si está inactivo; desactivar si está activo o pendiente de contraseña.
  const activate = user?.status === "INACTIVE";
  const canToggle = permissions.canManageStatus && (activate || !self);

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando usuario" blocks={[24, 24, 24, 24, 24, 24]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Este usuario ya no existe" : "No pudimos cargar el usuario"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    body = (
      <div className="grid gap-4">
        <UserDetail user={query.data} roles={roles} />
        {self && (
          <p className="text-text-tertiary m-0 text-sm">
            Es tu cuenta: no puedes desactivarla desde aquí.
          </p>
        )}
      </div>
    );
  }

  const footer = user && (permissions.canEdit || permissions.canAssignRoles || canToggle) && (
    <div className="flex flex-wrap gap-2">
      {canToggle && (
        <Button danger={!activate} onClick={() => setModal("status")}>
          {activate ? "Activar" : "Desactivar"}
        </Button>
      )}
      <div className="flex-1" />
      {permissions.canAssignRoles && (
        <Button onClick={() => setModal("roles")}>Cambiar roles</Button>
      )}
      {permissions.canEdit && (
        <Button type="primary" onClick={() => setModal("edit")}>
          Editar
        </Button>
      )}
    </div>
  );

  const close = () => setModal(null);

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Usuario"
        title={user ? user.name || user.email : "Usuario"}
        footer={footer || undefined}
      >
        {body}
      </SidePanel>
      {/* Cada modal se monta al abrir: su formulario arranca con los datos de ese momento. */}
      {user && modal === "edit" && <EditUserModal user={user} open onClose={close} />}
      {user && modal === "roles" && <RolesModal user={user} open onClose={close} />}
      {user && modal === "status" && (
        <StatusModal user={user} open onClose={close} activate={activate} />
      )}
    </>
  );
}
