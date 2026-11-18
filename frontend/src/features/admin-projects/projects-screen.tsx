"use client";

import { Button } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { PlusIcon } from "@/components/ui/icons";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/state-views";
import {
  cityOptionLabel,
  DEPARTMENT_CATALOG,
  PROJECT_STATUS_CATALOG,
  useCatalog,
  useMunicipalities,
} from "@/features/admin-common/catalogs";
import {
  AdminListFilters,
  type FilterOption,
  type SelectFilter,
} from "@/features/admin-common/list-filters";
import {
  formatOrdering,
  MOBILE_QUERY,
  parseOrdering,
  serializeListParams,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { partnerName, usePartnerOptions } from "@/features/admin-common/partner-select";
import {
  DEFAULT_PROJECT_ORDERING,
  PROJECT_SORT_FIELDS,
  PROJECTS_CONFIG,
  PROJECTS_HREF,
  useProjectsParams,
  type ProjectsParams,
} from "@/features/admin-projects/list-params";
import { ProjectFormModal } from "@/features/admin-projects/project-form-modal";
import { ProjectPanel } from "@/features/admin-projects/project-panel";
import { ProjectCards, ProjectsTable } from "@/features/admin-projects/projects-table";
import { useProjectsList, type Project } from "@/features/admin-projects/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const CLEARED: Partial<ProjectsParams> = { search: "", status: "", partner: "", city: "" };

/**
 * `/proyectos` (REQ §6 vista 13): proyectos inmobiliarios y su validación. Lo ven el
 * administrador, el asesor y la constructora (solo los suyos: lo decide la API).
 */
export function ProjectsScreen() {
  const { params, update } = useProjectsParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const partnerScoped = !!me.data?.scope.partner_id;
  const [creating, setCreating] = useState(false);

  const list = useProjectsList(params);
  const statuses = useCatalog(PROJECT_STATUS_CATALOG);
  const cities = useMunicipalities();
  const departments = useCatalog(DEPARTMENT_CATALOG);
  // Filtro por constructora: asesor y administrador (la constructora solo ve los suyos).
  const filterByPartner = !partnerScoped && has("partners.read");
  const partners = usePartnerOptions("", filterByPartner, "");

  const statusOptions = useMemo<FilterOption[]>(
    () => statuses.items.map((item) => ({ value: item.code, label: item.label })),
    [statuses.items],
  );
  const cityOptions = useMemo<FilterOption[]>(
    () =>
      cities.items.map((item) => ({
        value: item.code,
        label: cityOptionLabel(item, departments.items),
      })),
    [cities.items, departments.items],
  );
  const partnerOptions = useMemo<FilterOption[]>(
    () => (partners.data ?? []).map((p) => ({ value: p.id, label: partnerName(p) })),
    [partners.data],
  );

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const hrefOf = useCallback(
    (project: Project) =>
      `${PROJECTS_HREF}?${serializeListParams({ ...params, proyecto: project.id }, PROJECTS_CONFIG)}`,
    [params],
  );
  const open = useCallback((project: Project) => update({ proyecto: project.id }), [update]);
  const clear = () => update(CLEARED);
  const filtered =
    params.search !== "" || params.status !== "" || params.partner !== "" || params.city !== "";
  const canCreate = has("projects.create");

  const selects: SelectFilter[] = [
    { key: "status", label: "Estado", value: params.status, options: statusOptions },
    ...(filterByPartner
      ? [
          {
            key: "partner",
            label: "Constructora",
            value: params.partner,
            options: partnerOptions,
            loading: partners.isPending,
            searchable: true,
          },
        ]
      : []),
    {
      key: "city",
      label: "Municipio",
      value: params.city,
      options: cityOptions,
      loading: cities.isPending,
      searchable: true,
    },
  ];

  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;
  const showPartner = !partnerScoped;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando proyectos" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los proyectos"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay proyectos con estos filtros"
        description="Prueba con otra búsqueda o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Todavía no hay proyectos"
        description={
          canCreate
            ? "Crea el primero: nace en borrador y después se envía a validación."
            : undefined
        }
      />
    );
  } else if (mobile) {
    body = (
      <ProjectCards
        rows={rows}
        statuses={statuses.items}
        showPartner={showPartner}
        onOpen={open}
        hrefOf={hrefOf}
        busy={busy}
      />
    );
  } else {
    body = (
      <ProjectsTable
        rows={rows}
        statuses={statuses.items}
        showPartner={showPartner}
        sorting={parseOrdering(params.ordering, PROJECT_SORT_FIELDS, DEFAULT_PROJECT_ORDERING)}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        hrefOf={hrefOf}
        busy={busy}
      />
    );
  }

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Proyectos"
        description={
          partnerScoped
            ? "Los proyectos de tu constructora y su validación."
            : "Proyectos inmobiliarios de las constructoras aliadas y su validación."
        }
        actions={
          canCreate && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setCreating(true)}>
              Nuevo proyecto
            </Button>
          )
        }
      />

      <section
        aria-label="Listado de proyectos"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Nombre, código o dirección",
            ariaLabel: "Buscar proyectos por nombre, código o dirección",
          }}
          onSearch={(search) => update({ search })}
          selects={selects}
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
            itemsLabel="Proyectos"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>

      {params.proyecto && (
        <ProjectPanel
          key={params.proyecto}
          projectId={params.proyecto}
          statuses={statuses.items}
          permissions={{ canEdit: has("projects.update"), partnerScoped }}
          onClose={() => update({ proyecto: "" })}
        />
      )}
      {creating && (
        <ProjectFormModal
          partnerScoped={partnerScoped}
          onClose={() => setCreating(false)}
          onCreated={(project) => update({ proyecto: project.id })}
        />
      )}
    </div>
  );
}
