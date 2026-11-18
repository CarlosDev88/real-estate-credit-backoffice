"use client";

import Link from "next/link";
import { useMemo } from "react";

import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { RelativeTime } from "@/components/ui/relative-time";
import { ToneBadge } from "@/components/ui/status-badge";
import { USER_SORT_FIELDS } from "@/features/admin-users/list-params";
import { refName, roleName, type Role, type User } from "@/features/admin-users/queries";
import { statusOf, USER_STATUSES } from "@/features/admin-users/status";
import { formatDate } from "@/lib/format";

const DASH = <span className="text-text-tertiary">—</span>;

export function UserStatusBadge({ status }: { status: string }) {
  const option = statusOf(USER_STATUSES, status);
  return <ToneBadge tone={option.tone}>{option.label}</ToneBadge>;
}

/** Nombres de los roles del usuario, separados por coma. */
export function rolesText(user: Pick<User, "roles">, roles: readonly Role[] | undefined): string {
  return user.roles.map((code) => roleName(roles, code)).join(", ");
}

function LastLogin({ value }: { value: string | null }) {
  if (!value) return <span className="text-text-tertiary text-sm">Nunca</span>;
  return <RelativeTime value={value} className="text-text-secondary text-sm" />;
}

interface UsersListProps {
  rows: User[];
  roles: readonly Role[] | undefined;
  onOpen: (user: User) => void;
  /** Enlace del nombre: el mismo listado con el panel del usuario abierto. */
  hrefOf: (user: User) => string;
  busy?: boolean;
}

const helper = dataColumns<User>();

const makeColumns = (hrefOf: (user: User) => string, roles: readonly Role[] | undefined) =>
  helper.columns([
    helper.accessor((row) => row.first_name, {
      id: "first_name",
      header: "Nombre",
      cell: ({ row }) => (
        <Link
          href={hrefOf(row.original)}
          scroll={false}
          className="text-text-link block max-w-[240px] truncate font-medium no-underline hover:underline"
        >
          {row.original.name || row.original.email}
        </Link>
      ),
    }),
    helper.accessor((row) => row.email, {
      id: "email",
      header: "Correo",
      cell: ({ row }) => (
        <span className="block max-w-[260px] truncate text-sm">{row.original.email}</span>
      ),
    }),
    helper.display({
      id: "roles",
      header: "Roles",
      cell: ({ row }) => (
        <span className="block max-w-[220px] truncate text-sm">
          {rolesText(row.original, roles) || DASH}
        </span>
      ),
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
      cell: ({ row }) => <UserStatusBadge status={row.original.status} />,
    }),
    helper.accessor((row) => row.last_login, {
      id: "last_login",
      header: "Último ingreso",
      cell: ({ row }) => <LastLogin value={row.original.last_login} />,
    }),
    helper.accessor((row) => row.created_at, {
      id: "created_at",
      header: "Creado",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.created_at)}</span>
      ),
    }),
  ]);

/** Tabla de usuarios (escritorio). Un clic o Enter en la fila abre el panel. */
export function UsersTable({
  rows,
  roles,
  sorting,
  onSort,
  onOpen,
  hrefOf,
  busy,
}: UsersListProps & { sorting: TableSort; onSort: (sorting: TableSort) => void }) {
  const columns = useMemo(() => makeColumns(hrefOf, roles), [hrefOf, roles]);
  return (
    <DataTable
      ariaLabel="Usuarios"
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      sortableFields={USER_SORT_FIELDS}
      onSort={onSort}
      onOpen={onOpen}
      busy={busy}
      stickyColumn="first_name"
      minWidth={1040}
    />
  );
}

/** Listado en móvil (≤ 860 px): una tarjeta por usuario. */
export function UserCards({ rows, roles, onOpen, hrefOf, busy }: UsersListProps) {
  return (
    <CardList
      ariaLabel="Usuarios"
      rows={rows}
      getRowId={(user) => user.id}
      onOpen={onOpen}
      busy={busy}
      renderCard={(user) => (
        <>
          <div className="flex items-center gap-2">
            <Link
              href={hrefOf(user)}
              scroll={false}
              className="text-text-link min-w-0 truncate font-medium no-underline"
            >
              {user.name || user.email}
            </Link>
            <span className="ml-auto shrink-0">
              <UserStatusBadge status={user.status} />
            </span>
          </div>
          <div className="text-text-secondary truncate text-sm">{user.email}</div>
          <div className="text-text-secondary flex items-center gap-2 text-sm">
            <span className="min-w-0 truncate">{rolesText(user, roles) || "Sin roles"}</span>
            <span className="ml-auto whitespace-nowrap">
              <LastLogin value={user.last_login} />
            </span>
          </div>
        </>
      )}
    />
  );
}
