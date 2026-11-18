"use client";

import Link from "next/link";
import { useMemo } from "react";

import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { ToneBadge } from "@/components/ui/status-badge";
import { labelOf, type MetadataItem } from "@/features/admin-common/catalogs";
import { PROJECT_SORT_FIELDS } from "@/features/admin-projects/list-params";
import type { Project } from "@/features/admin-projects/queries";
import { formatDate, formatDateOnly } from "@/lib/format";

const DASH = <span className="text-text-tertiary">—</span>;

/**
 * Estado del proyecto con la etiqueta del catálogo `project_status`. No está en
 * `status-tones`: `ToneBadge` con tono neutro (spec F6, anotado).
 */
export function ProjectStatusBadge({
  status,
  statuses,
}: {
  status: string;
  statuses: readonly MetadataItem[];
}) {
  return <ToneBadge tone="neutral">{labelOf(statuses, status)}</ToneBadge>;
}

interface ProjectsListProps {
  rows: Project[];
  statuses: readonly MetadataItem[];
  /** Columna de la constructora: no para el usuario de una constructora (son todos suyos). */
  showPartner: boolean;
  onOpen: (project: Project) => void;
  hrefOf: (project: Project) => string;
  busy?: boolean;
}

const helper = dataColumns<Project>();

function makeColumns(
  hrefOf: (project: Project) => string,
  statuses: readonly MetadataItem[],
  showPartner: boolean,
) {
  return helper.columns([
    helper.accessor((row) => row.name, {
      id: "name",
      header: "Proyecto",
      cell: ({ row }) => (
        <div className="grid max-w-[280px]">
          <Link
            href={hrefOf(row.original)}
            scroll={false}
            className="text-text-link truncate font-medium no-underline hover:underline"
          >
            {row.original.name}
          </Link>
          {row.original.code && (
            <span className="text-text-tertiary truncate font-mono text-xs">
              {row.original.code}
            </span>
          )}
        </div>
      ),
    }),
    ...(showPartner
      ? [
          helper.display({
            id: "partner",
            header: "Constructora",
            cell: ({ row }) => (
              <span className="block max-w-[200px] truncate text-sm">
                {row.original.partner.name}
              </span>
            ),
          }),
        ]
      : []),
    helper.display({
      id: "city",
      header: "Municipio",
      cell: ({ row }) => (
        <span className="block max-w-[180px] truncate text-sm">
          {row.original.city.label || DASH}
        </span>
      ),
    }),
    helper.accessor((row) => row.status, {
      id: "status",
      header: "Estado",
      cell: ({ row }) => <ProjectStatusBadge status={row.original.status} statuses={statuses} />,
    }),
    helper.accessor((row) => row.estimated_delivery_date, {
      id: "estimated_delivery_date",
      header: "Entrega estimada",
      cell: ({ row }) =>
        row.original.estimated_delivery_date ? (
          <span className="text-sm">{formatDateOnly(row.original.estimated_delivery_date)}</span>
        ) : (
          DASH
        ),
    }),
    helper.accessor((row) => row.updated_at, {
      id: "updated_at",
      header: "Actualizado",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.updated_at)}</span>
      ),
    }),
  ]);
}

export function ProjectsTable({
  rows,
  statuses,
  showPartner,
  sorting,
  onSort,
  onOpen,
  hrefOf,
  busy,
}: ProjectsListProps & { sorting: TableSort; onSort: (sorting: TableSort) => void }) {
  const columns = useMemo(
    () => makeColumns(hrefOf, statuses, showPartner),
    [hrefOf, statuses, showPartner],
  );
  return (
    <DataTable
      ariaLabel="Proyectos"
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      sortableFields={PROJECT_SORT_FIELDS}
      onSort={onSort}
      onOpen={onOpen}
      busy={busy}
      stickyColumn="name"
    />
  );
}

export function ProjectCards({
  rows,
  statuses,
  showPartner,
  onOpen,
  hrefOf,
  busy,
}: ProjectsListProps) {
  return (
    <CardList
      ariaLabel="Proyectos"
      rows={rows}
      getRowId={(project) => project.id}
      onOpen={onOpen}
      busy={busy}
      renderCard={(project) => (
        <>
          <div className="flex items-center gap-2">
            <Link
              href={hrefOf(project)}
              scroll={false}
              className="text-text-link min-w-0 truncate font-medium no-underline"
            >
              {project.name}
            </Link>
            <span className="ml-auto">
              <ProjectStatusBadge status={project.status} statuses={statuses} />
            </span>
          </div>
          <div className="text-text-secondary truncate text-sm">
            {[showPartner ? project.partner.name : null, project.city.label]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </>
      )}
    />
  );
}
