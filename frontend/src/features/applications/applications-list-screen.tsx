"use client";

import { Alert, Button } from "antd";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { ApplicationCards } from "@/features/applications/application-cards";
import { ApplicationsTable, applicationHref } from "@/features/applications/applications-table";
import { ListFilters, type FilterDef } from "@/features/applications/list-filters";
import { ListPagination } from "@/features/applications/list-pagination";
import {
  filtersOf,
  formatOrdering,
  parseOrdering,
  useListParams,
  type ListParams,
} from "@/features/applications/list-params";
import {
  bankLabel,
  useActiveBanks,
  useApplicationsList,
  useCatalog,
  useQuickFilters,
  type Application,
} from "@/features/applications/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

/** Mismo corte que el shell y el mockup: en 860 px o menos, filtros en hoja y tarjetas. */
export const MOBILE_QUERY = "(max-width: 860px)";

function ListSkeleton() {
  return (
    <div role="status" aria-label="Cargando solicitudes" className="grid">
      {Array.from({ length: 6 }, (_, i) => (
        <div
          key={i}
          className="border-border-default flex h-[52px] items-center gap-4 border-b px-3 last:border-b-0"
        >
          <span className="bg-bg-muted h-3 w-24 animate-pulse rounded-full" />
          <span className="bg-bg-muted h-3 flex-1 animate-pulse rounded-full" />
          <span className="bg-bg-muted h-3 w-20 animate-pulse rounded-full" />
        </div>
      ))}
    </div>
  );
}

function useFilterDefs(canReadBanks: boolean): FilterDef[] {
  const banks = useActiveBanks(canReadBanks);
  const types = useCatalog("bank_product_type");
  const purposes = useCatalog("loan_purpose");

  return useMemo(() => {
    const toOptions = (items: { code: string; label: string }[]) =>
      items.map((item) => ({ value: item.code, label: item.label }));
    const defs: FilterDef[] = [];
    if (canReadBanks) {
      defs.push({
        key: "bank_id",
        label: "Banco",
        allLabel: "todos",
        ariaLabel: "Filtrar por banco",
        options: (banks.data ?? []).map((bank) => ({ value: bank.id, label: bankLabel(bank) })),
        loading: banks.isPending,
        width: 156,
      });
    }
    defs.push(
      {
        key: "product_type",
        label: "Tipo de crédito",
        allLabel: "todos",
        ariaLabel: "Filtrar por tipo de crédito",
        options: toOptions(types.items),
        loading: types.isPending,
        width: 196,
      },
      {
        key: "purpose",
        label: "Finalidad",
        allLabel: "todas",
        ariaLabel: "Filtrar por finalidad",
        options: toOptions(purposes.items),
        loading: purposes.isPending,
        width: 156,
      },
    );
    return defs;
  }, [canReadBanks, banks.data, banks.isPending, types, purposes]);
}

const CLEARED: Partial<ListParams> = { search: "", bank_id: "", product_type: "", purpose: "" };

/** Listado de solicitudes (`/solicitudes`, mockup `solicitudes.html`). */
export function ApplicationsListScreen() {
  const router = useRouter();
  const { params, update } = useListParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const canReadBanks = me.data?.permissions.includes("banks.read") ?? false;
  const filterDefs = useFilterDefs(canReadBanks);

  const list = useApplicationsList(params);
  const tabs = useQuickFilters(filtersOf(params));

  // Una página que ya no existe (la API responde 404) vuelve a la primera.
  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const open = useCallback(
    (application: Application) => router.push(applicationHref(application.id)),
    [router],
  );
  const clear = () => update(CLEARED);
  const filtered = Object.entries(CLEARED).some(([key]) => params[key as keyof ListParams] !== "");

  const data = list.data;
  const rows = data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <Alert
          type="error"
          showIcon
          title="No pudimos cargar las solicitudes"
          description={list.error.message}
          action={
            <Button size="small" onClick={() => void list.refetch()}>
              Reintentar
            </Button>
          }
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        title="No hay solicitudes con estos filtros"
        description="Prueba con otro estado o limpia los filtros."
        action={
          filtered ? (
            <Button size="small" onClick={clear}>
              Limpiar filtros
            </Button>
          ) : undefined
        }
      />
    );
  } else if (mobile) {
    body = <ApplicationCards rows={rows} onOpen={open} busy={busy} />;
  } else {
    body = (
      <ApplicationsTable
        rows={rows}
        sorting={parseOrdering(params.ordering)}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        busy={busy}
      />
    );
  }

  return (
    <div className="grid content-start gap-4">
      <div>
        <h1 className="m-0 text-3xl font-semibold tracking-tight">Solicitudes</h1>
        <p className="text-text-secondary mt-0.5 mb-0">
          Créditos de vivienda asignados a ti, desde el borrador hasta el desembolso.
        </p>
      </div>

      {tabs.data ? (
        <ScrollTabs
          ariaLabel="Filtro rápido por estado"
          items={tabs.data.map((tab) => ({ key: tab.code, label: tab.label, count: tab.count }))}
          value={params.quick_filter}
          onChange={(quick_filter) => update({ quick_filter })}
        />
      ) : tabs.isError ? (
        <div className="text-text-secondary flex items-center gap-2 text-sm" role="alert">
          No pudimos cargar las pestañas.
          <Button type="link" size="small" onClick={() => void tabs.refetch()}>
            Reintentar
          </Button>
        </div>
      ) : (
        <div
          aria-hidden="true"
          className="h-[38px] shadow-[inset_0_-1px_0_var(--um-border-default)]"
        />
      )}

      <section
        aria-label="Listado de solicitudes"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <ListFilters
          params={params}
          filters={filterDefs}
          onChange={update}
          onClear={clear}
          mobile={mobile}
        />
        {body}
        {data && rows.length > 0 && (
          <ListPagination
            page={params.page}
            pageSize={params.page_size}
            total={data.total}
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>
    </div>
  );
}
