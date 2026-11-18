"use client";

import { Button } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PlusIcon } from "@/components/ui/icons";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/state-views";
import {
  ACTIVE_STATUS_CODES,
  ActiveStatusBadge,
  activeStatusLabel,
} from "@/features/admin-common/active-status";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import {
  formatOrdering,
  MOBILE_QUERY,
  parseOrdering,
  serializeListParams,
} from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { BankFormModal } from "@/features/admin-banks/bank-form-modal";
import { BankPanel } from "@/features/admin-banks/bank-panel";
import {
  BANK_SORT_FIELDS,
  BANKS_CONFIG,
  BANKS_HREF,
  DEFAULT_BANK_ORDERING,
  useBanksParams,
  type BanksParams,
} from "@/features/admin-banks/list-params";
import { useBanksList, type Bank } from "@/features/admin-banks/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const CLEARED: Partial<BanksParams> = { search: "", status: "" };
const STATUS_OPTIONS: FilterOption[] = ACTIVE_STATUS_CODES.map((value) => ({
  value,
  label: activeStatusLabel(value),
}));
const DASH = <span className="text-text-tertiary">—</span>;

const helper = dataColumns<Bank>();
const makeColumns = (hrefOf: (bank: Bank) => string) =>
  helper.columns([
    helper.accessor((row) => row.name, {
      id: "name",
      header: "Banco",
      cell: ({ row }) => (
        <div className="grid max-w-[280px]">
          <Link
            href={hrefOf(row.original)}
            scroll={false}
            className="text-text-link truncate font-medium no-underline hover:underline"
          >
            {row.original.name}
          </Link>
          {row.original.short_name && (
            <span className="text-text-tertiary truncate text-xs">{row.original.short_name}</span>
          )}
        </div>
      ),
    }),
    helper.accessor((row) => row.code, {
      id: "code",
      header: "Código",
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.code}</span>,
    }),
    helper.display({
      id: "tax_id",
      header: "NIT",
      cell: ({ row }) =>
        row.original.tax_id ? (
          <span className="text-sm tabular-nums">{row.original.tax_id}</span>
        ) : (
          DASH
        ),
    }),
    helper.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => <ActiveStatusBadge status={row.original.status} />,
    }),
    helper.accessor((row) => row.updated_at, {
      id: "updated_at",
      header: "Actualizado",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.updated_at)}</span>
      ),
    }),
  ]);

/** `/admin/bancos` (REQ §6 vista 14): bancos y, dentro de cada uno, sus productos. */
export function BanksScreen() {
  const { params, update } = useBanksParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const [creating, setCreating] = useState(false);
  const list = useBanksList(params);

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const hrefOf = useCallback(
    (bank: Bank) =>
      `${BANKS_HREF}?${serializeListParams({ ...params, banco: bank.id }, BANKS_CONFIG)}`,
    [params],
  );
  const open = useCallback((bank: Bank) => update({ banco: bank.id }), [update]);
  const columns = useMemo(() => makeColumns(hrefOf), [hrefOf]);
  const clear = () => update(CLEARED);
  const filtered = params.search !== "" || params.status !== "";
  const canCreate = has("banks.create");

  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando bancos" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los bancos"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay bancos con estos filtros"
        description="Prueba con otra búsqueda o limpia los filtros."
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState title="Todavía no hay bancos" />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Bancos"
        rows={rows}
        getRowId={(bank) => bank.id}
        onOpen={open}
        busy={busy}
        renderCard={(bank) => (
          <>
            <div className="flex items-center gap-2">
              <Link
                href={hrefOf(bank)}
                scroll={false}
                className="text-text-link min-w-0 truncate font-medium no-underline"
              >
                {bank.name}
              </Link>
              <span className="ml-auto shrink-0">
                <ActiveStatusBadge status={bank.status} />
              </span>
            </div>
            <span className="text-text-secondary font-mono text-sm">{bank.code}</span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Bancos"
        columns={columns}
        rows={rows}
        getRowId={(bank) => bank.id}
        sorting={parseOrdering(params.ordering, BANK_SORT_FIELDS, DEFAULT_BANK_ORDERING)}
        sortableFields={BANK_SORT_FIELDS}
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
        title="Bancos"
        description="Bancos aliados, sus productos de crédito y las reglas que evalúan cada solicitud."
        actions={
          canCreate && (
            <Button type="primary" icon={<PlusIcon />} onClick={() => setCreating(true)}>
              Nuevo banco
            </Button>
          )
        }
      />
      <section
        aria-label="Listado de bancos"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Nombre, código o NIT",
            ariaLabel: "Buscar bancos por nombre, código o NIT",
          }}
          onSearch={(search) => update({ search })}
          selects={[
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
            itemsLabel="Bancos"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>

      {params.banco && (
        <BankPanel
          key={params.banco}
          bankId={params.banco}
          permissions={{ canCreate: canCreate, canUpdate: has("banks.update") }}
          onClose={() => update({ banco: "" })}
        />
      )}
      {creating && (
        <BankFormModal
          onClose={() => setCreating(false)}
          onCreated={(bank) => update({ banco: bank.id })}
        />
      )}
    </div>
  );
}
