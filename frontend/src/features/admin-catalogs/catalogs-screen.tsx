"use client";

import { Button } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PlusIcon } from "@/components/ui/icons";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import {
  DEFAULT_PAGE_SIZE,
  formatOrdering,
  MOBILE_QUERY,
  parseOrdering,
  parsePageSize,
  positiveInt,
  useListParams,
  type ListParamsConfig,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { CatalogFormModal } from "@/features/admin-catalogs/catalog-modals";
import {
  useCatalogs,
  type Catalog,
  type CatalogsListParams,
} from "@/features/admin-catalogs/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { formatInteger } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

export const CATALOGS_HREF = "/admin/catalogos";
export const catalogHref = (id: string) => `${CATALOGS_HREF}/${id}`;
const SORT_FIELDS = ["code", "name", "created_at", "updated_at"] as const;
const DEFAULT_ORDERING = "code";

const DEFAULTS: CatalogsListParams = {
  search: "",
  public: "",
  ordering: DEFAULT_ORDERING,
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
};

export function parseCatalogsParams(search: URLSearchParams): CatalogsListParams {
  const visibility = search.get("public") ?? "";
  return {
    search: (search.get("search") ?? "").trim(),
    public: visibility === "true" || visibility === "false" ? visibility : "",
    ordering: formatOrdering(parseOrdering(search.get("ordering"), SORT_FIELDS, DEFAULT_ORDERING)),
    page: positiveInt(search.get("page")) ?? 1,
    page_size: parsePageSize(search),
  };
}

const CONFIG: ListParamsConfig<CatalogsListParams> = {
  defaults: DEFAULTS,
  order: ["search", "public", "ordering", "page", "page_size"],
  parse: parseCatalogsParams,
};

const PUBLIC_OPTIONS: FilterOption[] = [
  { value: "true", label: "Públicos" },
  { value: "false", label: "Internos" },
];

/** "Del sistema": catálogo que la API no deja administrar (`is_manageable: false`). */
export function SystemBadge({ catalog }: { catalog: Pick<Catalog, "is_manageable"> }) {
  return catalog.is_manageable ? null : <ToneBadge tone="neutral">Del sistema</ToneBadge>;
}

const helper = dataColumns<Catalog>();
const columns = helper.columns([
  helper.accessor((row) => row.name, {
    id: "name",
    header: "Catálogo",
    cell: ({ row }) => (
      <Link
        href={catalogHref(row.original.id)}
        className="text-text-link block max-w-[280px] truncate font-medium no-underline hover:underline"
      >
        {row.original.name}
      </Link>
    ),
  }),
  helper.accessor((row) => row.code, {
    id: "code",
    header: "Código",
    cell: ({ row }) => <span className="font-mono text-sm">{row.original.code}</span>,
  }),
  helper.display({
    id: "items",
    header: "Valores",
    cell: ({ row }) => (
      <span className="text-sm tabular-nums">{formatInteger(row.original.items_count)}</span>
    ),
  }),
  helper.display({
    id: "visibility",
    header: "Visibilidad",
    cell: ({ row }) => (
      <span className="text-sm">{row.original.is_public ? "Público" : "Interno"}</span>
    ),
  }),
  helper.display({
    id: "system",
    header: "Edición",
    cell: ({ row }) =>
      row.original.is_manageable ? (
        <span className="text-text-secondary text-sm">Editable</span>
      ) : (
        <SystemBadge catalog={row.original} />
      ),
  }),
]);

/** `/admin/catalogos` (REQ §6 vista 14): catálogos de la app y sus valores. */
export function CatalogsScreen() {
  const router = useRouter();
  const { params, update } = useListParams(CONFIG);
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const canCreate = me.data?.permissions.includes("catalogs.create") ?? false;
  const [creating, setCreating] = useState(false);
  const list = useCatalogs(params);
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;
  const clear = () => update({ search: "", public: "" });
  const filtered = params.search !== "" || params.public !== "";
  const open = useMemo(() => (catalog: Catalog) => router.push(catalogHref(catalog.id)), [router]);

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando catálogos" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los catálogos"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay catálogos con estos filtros"
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState title="Todavía no hay catálogos" />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Catálogos"
        rows={rows}
        getRowId={(catalog) => catalog.id}
        onOpen={open}
        busy={busy}
        renderCard={(catalog) => (
          <>
            <div className="flex items-center gap-2">
              <Link
                href={catalogHref(catalog.id)}
                className="text-text-link min-w-0 truncate font-medium no-underline"
              >
                {catalog.name}
              </Link>
              <span className="ml-auto shrink-0">
                <SystemBadge catalog={catalog} />
              </span>
            </div>
            <span className="text-text-secondary text-sm">
              <span className="font-mono">{catalog.code}</span> ·{" "}
              {formatInteger(catalog.items_count)} valores
            </span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Catálogos"
        columns={columns}
        rows={rows}
        getRowId={(catalog) => catalog.id}
        sorting={parseOrdering(params.ordering, SORT_FIELDS, DEFAULT_ORDERING)}
        sortableFields={SORT_FIELDS}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        busy={busy}
        stickyColumn="name"
        minWidth={760}
      />
    );
  }

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Catálogos"
        description="Las listas de valores que usan los formularios: orígenes, finalidades, motivos y más."
        actions={
          canCreate && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setCreating(true)}>
              Nuevo catálogo
            </Button>
          )
        }
      />
      <section
        aria-label="Listado de catálogos"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Nombre o código",
            ariaLabel: "Buscar catálogos por nombre o código",
          }}
          onSearch={(search) => update({ search })}
          selects={[
            { key: "public", label: "Visibilidad", value: params.public, options: PUBLIC_OPTIONS },
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
            itemsLabel="Catálogos"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>
      {creating && (
        <CatalogFormModal
          onClose={() => setCreating(false)}
          onCreated={(catalog) => router.push(catalogHref(catalog.id))}
        />
      )}
    </div>
  );
}
