"use client";

import { Button } from "antd";
import { useState } from "react";

import { PlusIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { MOBILE_QUERY } from "@/features/admin-common/list-params";
import { useMe } from "@/features/auth/queries";
import { InvitationsTab } from "@/features/admin-users/invitations-tab";
import { InviteModal } from "@/features/admin-users/invite-modal";
import { useAdminUsersParams, type AdminUsersView } from "@/features/admin-users/list-params";
import { useRoles } from "@/features/admin-users/queries";
import { UsersTab } from "@/features/admin-users/users-tab";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const TAB_LABELS: Record<AdminUsersView, string> = {
  usuarios: "Usuarios",
  invitaciones: "Invitaciones",
};

/**
 * `/admin/usuarios` (REQ §6 vista 11): usuarios internos y sus invitaciones, en dos
 * pestañas (`?vista=`). Cada acción aparece solo con su permiso de `/auth/me`.
 */
export function AdminUsersScreen() {
  const { params, update, replace } = useAdminUsersParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const canReadRoles = has("roles.read");
  const roles = useRoles(canReadRoles);
  const [inviting, setInviting] = useState(false);

  const tabs: AdminUsersView[] = has("invitations.read")
    ? ["usuarios", "invitaciones"]
    : ["usuarios"];
  const view: AdminUsersView = tabs.includes(params.vista) ? params.vista : "usuarios";
  const canInvite = has("invitations.create") && canReadRoles;
  const rolesLoading = canReadRoles && roles.isPending;

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Usuarios"
        description="Personas con acceso al backoffice, sus roles y las invitaciones enviadas."
        actions={
          canInvite && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setInviting(true)}>
              Invitar usuario
            </Button>
          )
        }
      />

      {tabs.length > 1 && (
        <ScrollTabs
          ariaLabel="Secciones de usuarios"
          value={view}
          onChange={(key) => replace({ vista: key as AdminUsersView })}
          items={tabs.map((key) => ({ key, label: TAB_LABELS[key] }))}
        />
      )}

      {view === "usuarios" && (
        <div role="tabpanel" aria-label={TAB_LABELS.usuarios} className="grid gap-4">
          <UsersTab
            params={params}
            update={update}
            roles={roles.data}
            rolesLoading={rolesLoading}
            mobile={mobile}
            permissions={{
              canEdit: has("users.update"),
              canAssignRoles: has("roles.assign") && canReadRoles,
              canManageStatus: has("users.manage_status"),
              meId: me.data?.id ?? null,
            }}
          />
        </div>
      )}
      {view === "invitaciones" && (
        <div role="tabpanel" aria-label={TAB_LABELS.invitaciones} className="grid gap-4">
          <InvitationsTab
            params={params}
            update={update}
            roles={roles.data}
            rolesLoading={rolesLoading}
            mobile={mobile}
            permissions={{
              canCreate: has("invitations.create"),
              canRevoke: has("invitations.revoke"),
            }}
          />
        </div>
      )}

      {inviting && (
        <InviteModal
          open
          onClose={() => setInviting(false)}
          // La invitación nueva se ve en su pestaña (si el usuario puede verlas).
          onInvited={() => {
            if (tabs.includes("invitaciones")) replace({ vista: "invitaciones" });
          }}
          roles={roles.data}
          rolesLoading={rolesLoading}
        />
      )}
    </div>
  );
}
