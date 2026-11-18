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
  useCatalog,
  useMunicipalities,
} from "@/features/admin-common/catalogs";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import {
  formatOrdering,
  MOBILE_QUERY,
  parseOrdering,
  serializeListParams,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import {
  DEFAULT_PARTNER_ORDERING,
  PARTNER_SORT_FIELDS,
  PARTNER_STATUS_CODES,
  PARTNERS_CONFIG,
  PARTNERS_HREF,
  usePartnersParams,
  type PartnersParams,
} from "@/features/admin-partners/list-params";
import { PartnerFormModal } from "@/features/admin-partners/partner-form-modal";
import { PartnerPanel } from "@/features/admin-partners/partner-panel";
import { PartnerCards, PartnersTable } from "@/features/admin-partners/partners-table";
import { usePartnersList, type Partner } from "@/features/admin-partners/queries";
import { partnerStatusLabel } from "@/features/admin-partners/status";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const CLEARED: Partial<PartnersParams> = { search: "", status: "", city: "" };
const STATUS_OPTIONS: FilterOption[] = PARTNER_STATUS_CODES.map((value) => ({
  value,
  label: partnerStatusLabel(value),
}));

/** `/admin/constructoras` (REQ §6 vista 12): constructoras aliadas y sus miembros. */
export function PartnersScreen() {
  const { params, update } = usePartnersParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const [creating, setCreating] = useState(false);

  const list = usePartnersList(params);
  const cities = useMunicipalities();
  const departments = useCatalog(DEPARTMENT_CATALOG);
  const cityOptions = useMemo<FilterOption[]>(
    () =>
      cities.items.map((item) => ({
        value: item.code,
        label: cityOptionLabel(item, departments.items),
      })),
    [cities.items, departments.items],
  );

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const hrefOf = useCallback(
    (partner: Partner) =>
      `${PARTNERS_HREF}?${serializeListParams({ ...params, constructora: partner.id }, PARTNERS_CONFIG)}`,
    [params],
  );
  const open = useCallback((partner: Partner) => update({ constructora: partner.id }), [update]);
  const clear = () => update(CLEARED);
  const filtered = params.search !== "" || params.status !== "" || params.city !== "";
  const canCreate = has("partners.create");

  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando constructoras" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las constructoras"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay constructoras con estos filtros"
        description="Prueba con otra búsqueda o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Todavía no hay constructoras"
        description={
          canCreate ? "Registra la primera para crear sus proyectos y sus miembros." : undefined
        }
      />
    );
  } else if (mobile) {
    body = <PartnerCards rows={rows} onOpen={open} hrefOf={hrefOf} busy={busy} />;
  } else {
    body = (
      <PartnersTable
        rows={rows}
        sorting={parseOrdering(params.ordering, PARTNER_SORT_FIELDS, DEFAULT_PARTNER_ORDERING)}
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
        title="Constructoras"
        description="Constructoras aliadas, sus datos de contacto, sus proyectos y las personas que las representan."
        actions={
          canCreate && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setCreating(true)}>
              Nueva constructora
            </Button>
          )
        }
      />

      <section
        aria-label="Listado de constructoras"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Razón social, nombre o NIT",
            ariaLabel: "Buscar constructoras por razón social, nombre o NIT",
          }}
          onSearch={(search) => update({ search })}
          selects={[
            { key: "status", label: "Estado", value: params.status, options: STATUS_OPTIONS },
            {
              key: "city",
              label: "Municipio",
              ariaLabel: "Filtrar por municipio de sus proyectos",
              value: params.city,
              options: cityOptions,
              loading: cities.isPending,
              searchable: true,
            },
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
            itemsLabel="Constructoras"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>

      {params.constructora && (
        <PartnerPanel
          key={params.constructora}
          partnerId={params.constructora}
          onClose={() => update({ constructora: "" })}
          permissions={{
            canEdit: has("partners.update"),
            canManageStatus: has("partners.manage_status"),
            canReadMembers: has("partner_members.read"),
            canAddMembers: has("partner_members.create"),
            canPickUsers: has("users.read"),
          }}
        />
      )}
      {creating && (
        <PartnerFormModal
          onClose={() => setCreating(false)}
          onCreated={(partner) => update({ constructora: partner.id })}
        />
      )}
    </div>
  );
}
