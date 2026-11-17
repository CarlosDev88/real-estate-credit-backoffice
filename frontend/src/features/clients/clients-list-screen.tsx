"use client";

import { Alert, Button } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { MOBILE_QUERY } from "@/features/applications/applications-list-screen";
import { useCatalog } from "@/features/applications/queries";
import { useMe } from "@/features/auth/queries";
import { ClientCards } from "@/features/clients/components/client-cards";
import { ClientsFilters } from "@/features/clients/components/clients-filters";
import { ClientsTable } from "@/features/clients/components/clients-table";
import { PlusIcon } from "@/features/clients/components/icons";
import { ListPagination } from "@/features/clients/components/list-pagination";
import {
  formatClientOrdering,
  parseClientOrdering,
  useClientListParams,
  type ClientListParams,
} from "@/features/clients/list-params";
import {
  clientHref,
  NEW_CLIENT_HREF,
  ORIGIN_CATALOG,
  useClientsList,
  type Client,
} from "@/features/clients/queries";
import { clientTabQuery } from "@/features/clients/detail-tabs";
import { isApiError } from "@/lib/api/errors";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

function ListSkeleton() {
  return (
    <div role="status" aria-label="Cargando clientes" className="grid">
      {Array.from({ length: 6 }, (_, i) => (
        <div
          key={i}
          className="border-border-default flex h-11 items-center gap-4 border-b px-3 last:border-b-0"
        >
          <span className="bg-bg-muted h-3 w-40 animate-pulse rounded-full" />
          <span className="bg-bg-muted h-3 w-24 animate-pulse rounded-full" />
          <span className="bg-bg-muted h-3 flex-1 animate-pulse rounded-full" />
          <span className="bg-bg-muted h-3 w-20 animate-pulse rounded-full" />
        </div>
      ))}
    </div>
  );
}

const CLEARED: Partial<ClientListParams> = { search: "", origin: "" };

/** Listado de clientes (`/clientes`, REQ §6 vista 4). Mismo patrón que `/solicitudes`. */
export function ClientsListScreen() {
  const router = useRouter();
  const { params, update } = useClientListParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const canCreate = me.data?.permissions.includes("clients.create") ?? false;
  const origins = useCatalog(ORIGIN_CATALOG);
  const originOptions = useMemo(
    () => origins.items.map((item) => ({ value: item.code, label: item.label })),
    [origins.items],
  );

  const list = useClientsList(params);

  // Una página que ya no existe (la API responde 404) vuelve a la primera.
  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  // Desde "Nueva solicitud" (`/solicitudes`), el cliente abre en su pestaña Oportunidades.
  const forApplication = params.nueva_solicitud === "1";
  const hrefOf = useCallback(
    (client: Client) =>
      forApplication
        ? `${clientHref(client.id)}?${clientTabQuery("oportunidades")}`
        : clientHref(client.id),
    [forApplication],
  );
  const open = useCallback((client: Client) => router.push(hrefOf(client)), [router, hrefOf]);
  const clear = () => update(CLEARED);
  const filtered = params.search !== "" || params.origin !== "";

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
          title="No pudimos cargar los clientes"
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
    body = filtered ? (
      <EmptyState
        title="No hay clientes con estos filtros"
        description="Prueba con otra búsqueda o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Todavía no hay clientes"
        description={
          canCreate
            ? "Registra el primero para crear sus oportunidades y solicitudes."
            : "Aquí verás los clientes a tu cargo."
        }
        action={
          canCreate ? (
            <Link href={NEW_CLIENT_HREF} className="text-text-link underline">
              Registrar un cliente
            </Link>
          ) : undefined
        }
      />
    );
  } else if (mobile) {
    body = <ClientCards rows={rows} onOpen={open} hrefOf={hrefOf} busy={busy} />;
  } else {
    body = (
      <ClientsTable
        rows={rows}
        sorting={parseClientOrdering(params.ordering)}
        onSort={(sorting) => update({ ordering: formatClientOrdering(sorting) })}
        onOpen={open}
        hrefOf={hrefOf}
        busy={busy}
      />
    );
  }

  return (
    <div className="grid content-start gap-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="m-0 text-3xl font-semibold tracking-tight">Clientes</h1>
          <p className="text-text-secondary mt-0.5 mb-0">
            Compradores con sus oportunidades y solicitudes de crédito.
          </p>
        </div>
        {canCreate && (
          <Button type="primary" icon={<PlusIcon />} onClick={() => router.push(NEW_CLIENT_HREF)}>
            Nuevo cliente
          </Button>
        )}
      </div>

      {forApplication && (
        <Alert
          type="info"
          showIcon
          title="Elige el cliente y su oportunidad"
          description="La solicitud de crédito se crea desde una oportunidad del cliente, en su pestaña Oportunidades."
          closable={{ "aria-label": "Cerrar ayuda" }}
          onClose={() => update({ nueva_solicitud: "" })}
        />
      )}

      <section
        aria-label="Listado de clientes"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <ClientsFilters
          params={params}
          origins={originOptions}
          originsLoading={origins.isPending}
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
            itemsLabel="Clientes"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>
    </div>
  );
}
