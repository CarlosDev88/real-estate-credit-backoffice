"use client";

import { Button } from "antd";
import { useCallback, useEffect, useMemo } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { ErrorState } from "@/components/ui/state-views";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import {
  formatOrdering,
  parseOrdering,
  serializeListParams,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import {
  ADMIN_USERS_CONFIG,
  ADMIN_USERS_HREF,
  DEFAULT_ORDERING,
  USER_SORT_FIELDS,
  type AdminUsersParams,
} from "@/features/admin-users/list-params";
import { useUsersList, type Role, type User } from "@/features/admin-users/queries";
import { USER_STATUSES } from "@/features/admin-users/status";
import { UserPanel, type UserPermissions } from "@/features/admin-users/user-panel";
import { UserCards, UsersTable } from "@/features/admin-users/users-table";
import { isApiError } from "@/lib/api/errors";

const CLEARED: Partial<AdminUsersParams> = { search: "", role: "", status: "" };
const STATUS_OPTIONS: FilterOption[] = USER_STATUSES.map(({ value, label }) => ({ value, label }));

interface UsersTabProps {
  params: AdminUsersParams;
  update: (patch: Partial<AdminUsersParams>) => void;
  roles: readonly Role[] | undefined;
  rolesLoading: boolean;
  permissions: UserPermissions;
  mobile: boolean;
}

/** Pestaña "Usuarios": `GET /users` con búsqueda, rol y estado; el detalle va en un panel. */
export function UsersTab({
  params,
  update,
  roles,
  rolesLoading,
  permissions,
  mobile,
}: UsersTabProps) {
  const list = useUsersList(params);

  // Una página que ya no existe (la API responde 404) vuelve a la primera.
  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const hrefOf = useCallback(
    (user: User) => {
      const qs = serializeListParams({ ...params, usuario: user.id }, ADMIN_USERS_CONFIG);
      return `${ADMIN_USERS_HREF}?${qs}`;
    },
    [params],
  );
  const open = useCallback((user: User) => update({ usuario: user.id }), [update]);
  const clear = () => update(CLEARED);
  const filtered = params.search !== "" || params.role !== "" || params.status !== "";
  const roleOptions = useMemo<FilterOption[]>(
    () => (roles ?? []).map((role) => ({ value: role.code, label: role.name })),
    [roles],
  );

  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando usuarios" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los usuarios"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay usuarios con estos filtros"
        description="Prueba con otra búsqueda o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Todavía no hay usuarios"
        description="Invita a las personas del equipo desde la pestaña Invitaciones."
      />
    );
  } else if (mobile) {
    body = <UserCards rows={rows} roles={roles} onOpen={open} hrefOf={hrefOf} busy={busy} />;
  } else {
    body = (
      <UsersTable
        rows={rows}
        roles={roles}
        sorting={parseOrdering(params.ordering, USER_SORT_FIELDS, DEFAULT_ORDERING)}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        hrefOf={hrefOf}
        busy={busy}
      />
    );
  }

  return (
    <>
      <section
        aria-label="Listado de usuarios"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Nombre o correo",
            ariaLabel: "Buscar usuarios por nombre o correo",
          }}
          onSearch={(search) => update({ search })}
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
            itemsLabel="Usuarios"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>

      {params.usuario && (
        <UserPanel
          key={params.usuario}
          userId={params.usuario}
          roles={roles}
          permissions={permissions}
          onClose={() => update({ usuario: "" })}
        />
      )}
    </>
  );
}
