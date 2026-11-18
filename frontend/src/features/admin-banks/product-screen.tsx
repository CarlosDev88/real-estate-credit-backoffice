"use client";

import { Button } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { Card, DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PlusIcon } from "@/components/ui/icons";
import { ListPagination } from "@/components/ui/list-pagination";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ActiveStatusBadge } from "@/features/admin-common/active-status";
import { useCatalog } from "@/features/admin-common/catalogs";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import { formatOrdering, MOBILE_QUERY, parseOrdering } from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { ReasonModal } from "@/features/admin-common/reason-modal";
import { describeCondition } from "@/features/admin-banks/condition";
import {
  RULE_STATUS_CODES,
  ruleStatusLabel,
  RuleStatusBadge,
  SEVERITY_CODES,
  SeverityBadge,
  severityLabel,
} from "@/features/admin-banks/labels";
import {
  bankHref,
  DEFAULT_RULE_ORDERING,
  RULE_SORT_FIELDS,
  useRulesParams,
  type RulesParams,
} from "@/features/admin-banks/list-params";
import {
  LOAN_PURPOSE_CATALOG,
  ProductFormModal,
  PurposesModal,
} from "@/features/admin-banks/product-form-modal";
import {
  bankLabel,
  useProduct,
  useRulesList,
  useSetProductActive,
  type BankProduct,
  type Rule,
} from "@/features/admin-banks/queries";
import { RuleFormModal } from "@/features/admin-banks/rule-form-modal";
import { RulePanel } from "@/features/admin-banks/rule-panel";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDate, formatDateOnly, formatInteger } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useToast } from "@/providers/toast";

const CLEARED: Partial<RulesParams> = { search: "", status: "", severity: "", purpose: "" };
const STATUS_OPTIONS: FilterOption[] = RULE_STATUS_CODES.map((value) => ({
  value,
  label: ruleStatusLabel(value),
}));
const SEVERITY_OPTIONS: FilterOption[] = SEVERITY_CODES.map((value) => ({
  value,
  label: severityLabel(value),
}));

const range = (min: number | null, max: number | null, format: (n: number) => string) => {
  if (min === null && max === null) return null;
  if (min !== null && max !== null) return `${format(min)} a ${format(max)}`;
  return min !== null ? `Desde ${format(min)}` : `Hasta ${format(max!)}`;
};
const months = (n: number) => `${formatInteger(n)} meses`;

function ProductData({ product }: { product: BankProduct }) {
  return (
    <DataList columns={3}>
      <Datum label="Tipo">{product.product_type.label}</Datum>
      <Datum label="Código">
        <span className="font-mono">{product.code}</span>
      </Datum>
      <Datum label="Estado">
        <ActiveStatusBadge status={product.status} />
      </Datum>
      <Datum label="Montos">
        {product.min_amount_cop === null && product.max_amount_cop === null ? null : (
          <span className="flex flex-wrap gap-1">
            {product.min_amount_cop !== null && <Money value={product.min_amount_cop} />}
            {product.min_amount_cop !== null && product.max_amount_cop !== null && "a"}
            {product.max_amount_cop !== null && <Money value={product.max_amount_cop} />}
          </span>
        )}
      </Datum>
      <Datum label="Plazos">
        {range(product.min_term_months, product.max_term_months, months)}
      </Datum>
      <Datum label="Vigencia">
        {`${formatDateOnly(product.valid_from)} – ${formatDateOnly(product.valid_to) ?? "sin vencimiento"}`}
      </Datum>
    </DataList>
  );
}

const helper = dataColumns<Rule>();
const makeColumns = (open: (rule: Rule) => void) =>
  helper.columns([
    helper.accessor((row) => row.code, {
      id: "code",
      header: "Regla",
      cell: ({ row }) => (
        <button
          type="button"
          onClick={() => open(row.original)}
          className="text-text-link cursor-pointer border-0 bg-transparent p-0 text-left font-mono text-sm font-medium hover:underline"
        >
          {row.original.code}
        </button>
      ),
    }),
    helper.accessor((row) => row.version, {
      id: "version",
      header: "Versión",
      cell: ({ row }) => <span className="text-sm tabular-nums">v{row.original.version}</span>,
    }),
    helper.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => <RuleStatusBadge status={row.original.status} />,
    }),
    helper.display({
      id: "severity",
      header: "Severidad",
      cell: ({ row }) => <SeverityBadge severity={row.original.severity} />,
    }),
    helper.display({
      id: "purpose",
      header: "Finalidad",
      cell: ({ row }) => <span className="text-sm">{row.original.purpose?.label ?? "Todas"}</span>,
    }),
    helper.display({
      id: "condition",
      header: "Condición",
      cell: ({ row }) => (
        <span className="text-text-secondary block max-w-[320px] truncate font-mono text-xs">
          {describeCondition(row.original.condition)}
        </span>
      ),
    }),
    helper.accessor((row) => row.valid_from, {
      id: "valid_from",
      header: "Vigente desde",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.valid_from)}</span>
      ),
    }),
  ]);

function RulesSection({
  product,
  canCreate,
  canUpdate,
  canPublish,
}: {
  product: BankProduct;
  canCreate: boolean;
  canUpdate: boolean;
  canPublish: boolean;
}) {
  const { params, update } = useRulesParams();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const list = useRulesList(product.id, params);
  const purposes = useCatalog(LOAN_PURPOSE_CATALOG);
  const [creating, setCreating] = useState(false);
  const purposeOptions = useMemo<FilterOption[]>(
    () => purposes.items.map((item) => ({ value: item.code, label: item.label })),
    [purposes.items],
  );

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const open = useCallback((rule: Rule) => update({ regla: rule.id }), [update]);
  const columns = useMemo(() => makeColumns(open), [open]);
  const clear = () => update(CLEARED);
  const filtered =
    params.search !== "" || params.status !== "" || params.severity !== "" || params.purpose !== "";
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando reglas" rows={3} />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar las reglas"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay reglas con estos filtros"
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="Este producto todavía no tiene reglas"
        description={
          canCreate
            ? "Crea una para evaluar las solicitudes de este producto antes de radicarlas."
            : undefined
        }
      />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Reglas"
        rows={rows}
        getRowId={(rule) => rule.id}
        onOpen={open}
        busy={busy}
        renderCard={(rule) => (
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => open(rule)}
                className="text-text-link min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-mono text-sm font-medium"
              >
                {rule.code} v{rule.version}
              </button>
              <span className="ml-auto flex shrink-0 gap-1">
                <RuleStatusBadge status={rule.status} />
              </span>
            </div>
            <span className="text-text-secondary truncate font-mono text-xs">
              {describeCondition(rule.condition)}
            </span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Reglas"
        columns={columns}
        rows={rows}
        getRowId={(rule) => rule.id}
        sorting={parseOrdering(params.ordering, RULE_SORT_FIELDS, DEFAULT_RULE_ORDERING)}
        sortableFields={RULE_SORT_FIELDS}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        busy={busy}
        stickyColumn="code"
        minWidth={980}
      />
    );
  }

  return (
    <section aria-labelledby="product-rules" className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="product-rules" className="m-0 flex-1 text-xl font-semibold">
          Reglas
        </h2>
        {canCreate && (
          <Button icon={<PlusIcon />} onClick={() => setCreating(true)}>
            Nueva regla
          </Button>
        )}
      </div>
      <div className="bg-bg-surface border-border-default overflow-hidden rounded-lg border">
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Código o mensaje",
            ariaLabel: "Buscar reglas por código o mensaje",
          }}
          onSearch={(search) => update({ search })}
          selects={[
            { key: "status", label: "Estado", value: params.status, options: STATUS_OPTIONS },
            {
              key: "severity",
              label: "Severidad",
              value: params.severity,
              options: SEVERITY_OPTIONS,
            },
            {
              key: "purpose",
              label: "Finalidad",
              value: params.purpose,
              options: purposeOptions,
              loading: purposes.isPending,
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
            itemsLabel="Reglas"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </div>

      {params.regla && (
        <RulePanel
          key={params.regla}
          ruleId={params.regla}
          productId={product.id}
          permissions={{ canUpdate, canPublish }}
          onOpen={(id) => update({ regla: id })}
          onClose={() => update({ regla: "" })}
        />
      )}
      {creating && (
        <RuleFormModal
          productId={product.id}
          onClose={() => setCreating(false)}
          onSaved={(rule) => update({ regla: rule.id })}
        />
      )}
    </section>
  );
}

type Modal = "edit" | "purposes" | "status" | null;

/**
 * `/admin/bancos/productos/[id]` (REQ §6 vista 14): un producto con sus datos, sus
 * finalidades y sus reglas (listado, versiones y pruebas).
 */
export function ProductScreen({ productId }: { productId: string }) {
  const toast = useToast();
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const query = useProduct(productId);
  const setActive = useSetProductActive(productId);
  const [modal, setModal] = useState<Modal>(null);
  const product = query.data;
  useShellTrail(product?.name);
  const close = () => setModal(null);

  if (query.isPending) return <LoadingState label="Cargando producto" blocks={[72, 160, 240]} />;
  if (query.isError || !product) {
    const gone = isApiError(query.error) && query.error.status === 404;
    return (
      <ErrorState
        variant="page"
        titleAs="h1"
        title={gone ? "Este producto no existe" : "No pudimos cargar el producto"}
        message={query.error?.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }

  const canUpdate = has("banks.update");
  const activate = product.status === "INACTIVE";

  return (
    <div className="grid content-start gap-6">
      <PageHeader
        back={{ href: bankHref(product.bank.id), label: `Volver a ${bankLabel(product.bank)}` }}
        title={product.name}
        description={`${product.bank.name} · ${product.product_type.label}`}
        actions={
          canUpdate && (
            <>
              <Button danger={!activate} onClick={() => setModal("status")}>
                {activate ? "Activar" : "Desactivar"}
              </Button>
              <Button type="primary" onClick={() => setModal("edit")}>
                Editar
              </Button>
            </>
          )
        }
      />

      <Card title="Datos del producto">
        <ProductData product={product} />
      </Card>

      <Card
        title="Finalidades"
        action={
          canUpdate && (
            <Button size="small" onClick={() => setModal("purposes")}>
              Cambiar finalidades
            </Button>
          )
        }
      >
        {product.purposes.length === 0 ? (
          <p className="text-text-tertiary m-0 text-sm">Sin finalidades activas.</p>
        ) : (
          <ul
            aria-label="Finalidades del producto"
            className="m-0 flex list-none flex-wrap gap-2 p-0"
          >
            {product.purposes.map((purpose) => (
              <li
                key={purpose.code}
                className="bg-bg-subtle border-border-default rounded-full border px-3 py-1 text-sm"
              >
                {purpose.label}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {has("bank_rules.read") && (
        <RulesSection
          product={product}
          canCreate={has("bank_rules.create")}
          canUpdate={has("bank_rules.update")}
          canPublish={has("bank_rules.publish")}
        />
      )}

      {modal === "edit" && (
        <ProductFormModal bankId={product.bank.id} product={product} onClose={close} />
      )}
      {modal === "purposes" && <PurposesModal product={product} onClose={close} />}
      {modal === "status" && (
        <ReasonModal
          title={activate ? "Activar producto" : "Desactivar producto"}
          description={
            activate
              ? "Si está vigente y su banco está activo, vuelve a estar disponible para las solicitudes."
              : "Mientras esté inactivo, no aparece entre los productos disponibles para las solicitudes."
          }
          okText={activate ? "Activar" : "Desactivar"}
          reasonRequired={false}
          danger={!activate}
          loading={setActive.isPending}
          onConfirm={(reason) => setActive.mutateAsync({ active: activate, reason })}
          onDone={() => {
            toast.success({ title: activate ? "Producto activado" : "Producto desactivado" });
            close();
          }}
          onCancel={close}
        />
      )}
    </div>
  );
}
