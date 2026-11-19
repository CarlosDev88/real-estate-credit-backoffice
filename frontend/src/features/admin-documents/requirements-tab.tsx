"use client";

import { Button } from "antd";
import { useEffect, useMemo, useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useCatalog } from "@/features/admin-common/catalogs";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import { formatOrdering, parseOrdering } from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import {
  labelIn,
  PARTICIPANT_ROLE_LABELS,
  PARTICIPANT_ROLES,
  REQUIREMENT_STATUS_LABELS,
  REQUIREMENT_STATUSES,
  RequirementStatusBadge,
} from "@/features/admin-documents/labels";
import {
  defaultOrdering,
  GENERAL,
  REQUIREMENT_SORT_FIELDS,
  type DocumentsParams,
} from "@/features/admin-documents/list-params";
import {
  productOptionLabel,
  useDocumentTypeOptions,
  useProductOptions,
  useRequirement,
  useRequirements,
  useSetRequirementActive,
  type Requirement,
} from "@/features/admin-documents/queries";
import {
  PURPOSE_CATALOG,
  RequirementFormModal,
  scopeText,
} from "@/features/admin-documents/requirement-form-modal";
import type { DocumentPermissions } from "@/features/admin-documents/types-tab";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime, formatInteger } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

const STATUS_OPTIONS: FilterOption[] = REQUIREMENT_STATUSES.map((value) => ({
  value,
  label: REQUIREMENT_STATUS_LABELS[value]!,
}));
const ROLE_OPTIONS: FilterOption[] = PARTICIPANT_ROLES.map((value) => ({
  value,
  label: PARTICIPANT_ROLE_LABELS[value]!,
}));
const CLEARED: Partial<DocumentsParams> = {
  status: "",
  product: "",
  doc_type: "",
  purpose: "",
  role: "",
};

/** "Obligatorio · exonerable · 2 archivos": las condiciones de un requisito, en una línea. */
export function requirementTerms(item: {
  is_required: boolean;
  is_waivable: boolean;
  minimum_files: number;
  validity_days: number | null;
  alternative_group_code: string | null;
}): string {
  return [
    item.is_required ? "Obligatorio" : "Opcional",
    item.is_waivable ? "exonerable" : null,
    item.minimum_files > 1 ? `${item.minimum_files} archivos` : null,
    item.validity_days ? `vigencia ${formatInteger(item.validity_days)} días` : null,
    item.alternative_group_code ? `alternativa ${item.alternative_group_code}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function RequirementPanel({
  requirementId,
  permissions,
  onOpen,
  onClose,
}: {
  requirementId: string;
  permissions: DocumentPermissions;
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const showError = useApiErrorToast();
  const query = useRequirement(requirementId);
  const setActive = useSetRequirementActive(requirementId);
  const [modal, setModal] = useState<"edit" | "publish" | "deactivate" | null>(null);
  const requirement = query.data;
  const close = () => setModal(null);

  const runStatus = (active: boolean) =>
    setActive.mutate(active, {
      onSuccess: () => {
        toast.success({ title: active ? "Requisito publicado" : "Requisito desactivado" });
        close();
      },
      onError: (error) => {
        close();
        showError(error);
      },
    });

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando requisito" blocks={[24, 24, 24, 24]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Este requisito ya no existe" : "No pudimos cargar el requisito"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    const data = query.data;
    body = (
      <DataList layout="inline">
        <Datum label="Estado">
          <RequirementStatusBadge status={data.status} />
        </Datum>
        <Datum label="Versión">v{data.version}</Datum>
        <Datum label="Producto">
          {data.bank_product
            ? productOptionLabel(data.bank_product)
            : "General (todos los productos)"}
        </Datum>
        <Datum label="Finalidad">{data.purpose?.label ?? "Cualquiera"}</Datum>
        <Datum label="Rol del participante">
          {labelIn(PARTICIPANT_ROLE_LABELS, data.participant_role as string | null) || "Cualquiera"}
        </Datum>
        <Datum label="Perfil laboral">{data.employment_profile?.label ?? "Cualquiera"}</Datum>
        <Datum label="Condición del inmueble">
          {data.property_condition?.label ?? "Cualquiera"}
        </Datum>
        <Datum label="Condiciones">{requirementTerms(data)}</Datum>
        <Datum label="Orden en el checklist">{data.sort_order}</Datum>
        <Datum label="Vigente desde">{formatDateTime(data.valid_from)}</Datum>
        <Datum label="Vigente hasta">{formatDateTime(data.valid_to) ?? "Sin vencimiento"}</Datum>
        {!data.document_type.is_active && (
          <Datum label="Aviso">
            El tipo documental está inactivo: este requisito no se aplica ni se puede publicar.
          </Datum>
        )}
      </DataList>
    );
  }

  const publish = requirement && permissions.canPublish && requirement.status !== "ACTIVE";
  const deactivate = requirement && permissions.canPublish && requirement.status === "ACTIVE";
  const footer = requirement && (permissions.canUpdate || permissions.canPublish) && (
    <div className="flex flex-wrap gap-2">
      {deactivate && (
        <Button danger onClick={() => setModal("deactivate")}>
          Desactivar
        </Button>
      )}
      <div className="flex-1" />
      {permissions.canUpdate && (
        <Button type={publish ? "default" : "primary"} onClick={() => setModal("edit")}>
          {requirement.status === "DRAFT" ? "Editar" : "Nueva versión"}
        </Button>
      )}
      {publish && (
        <Button type="primary" onClick={() => setModal("publish")}>
          {requirement.status === "DRAFT" ? "Publicar" : "Activar"}
        </Button>
      )}
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow={requirement ? `Requisito · v${requirement.version}` : "Requisito"}
        title={requirement?.document_type.name ?? "Requisito"}
        footer={footer || undefined}
      >
        {body}
      </SidePanel>
      {requirement && modal === "edit" && (
        <RequirementFormModal
          requirement={requirement}
          onClose={close}
          onSaved={(id) => {
            if (id !== requirement.id) onOpen(id);
          }}
        />
      )}
      {requirement && modal === "publish" && (
        <ActionModal
          open
          title={`${requirement.status === "DRAFT" ? "Publicar" : "Activar"} requisito v${requirement.version}`}
          description="Se aplica a los checklists nuevos de su alcance. Si hay otra versión activa del mismo alcance, pasa a inactiva."
          okText={requirement.status === "DRAFT" ? "Publicar" : "Activar"}
          loading={setActive.isPending}
          onSubmit={() => runStatus(true)}
          onCancel={close}
        />
      )}
      {requirement && modal === "deactivate" && (
        <ActionModal
          open
          title={`Desactivar requisito v${requirement.version}`}
          description="Deja de pedirse en los checklists nuevos."
          okText="Desactivar"
          danger
          loading={setActive.isPending}
          onSubmit={() => runStatus(false)}
          onCancel={close}
        />
      )}
    </>
  );
}

const helper = dataColumns<Requirement>();
const makeColumns = (open: (requirement: Requirement) => void) =>
  helper.columns([
    helper.display({
      id: "document_type",
      header: "Documento",
      cell: ({ row }) => (
        <button
          type="button"
          onClick={() => open(row.original)}
          className="text-text-link max-w-[240px] cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium hover:underline"
        >
          {row.original.document_type.name}
        </button>
      ),
    }),
    helper.display({
      id: "scope",
      header: "Aplica a",
      cell: ({ row }) => (
        <span className="block max-w-[320px] truncate text-sm" title={scopeText(row.original)}>
          {scopeText(row.original)}
        </span>
      ),
    }),
    helper.display({
      id: "terms",
      header: "Condiciones",
      cell: ({ row }) => (
        <span className="text-text-secondary block max-w-[260px] truncate text-sm">
          {requirementTerms(row.original)}
        </span>
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
      cell: ({ row }) => <RequirementStatusBadge status={row.original.status} />,
    }),
    helper.accessor((row) => row.sort_order, {
      id: "sort_order",
      header: "Orden",
      cell: ({ row }) => <span className="text-sm tabular-nums">{row.original.sort_order}</span>,
    }),
  ]);

/** Pestaña "Requisitos": `GET /document-requirements` por producto, tipo, finalidad, rol y estado. */
export function RequirementsTab({
  params,
  update,
  permissions,
  mobile,
  creating,
  onCloseCreate,
}: {
  params: DocumentsParams;
  update: (patch: Partial<DocumentsParams>) => void;
  permissions: DocumentPermissions;
  mobile: boolean;
  creating: boolean;
  onCloseCreate: () => void;
}) {
  const list = useRequirements(params, true);
  const types = useDocumentTypeOptions();
  const products = useProductOptions();
  const purposes = useCatalog(PURPOSE_CATALOG);
  const open = (requirement: Requirement) => update({ abierto: requirement.id });
  const columns = useMemo(() => makeColumns((r) => update({ abierto: r.id })), [update]);
  const clear = () => update(CLEARED);
  const filtered = Object.keys(CLEARED).some((key) => params[key as keyof DocumentsParams] !== "");
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  const productOptions = useMemo<FilterOption[]>(
    () => [
      { value: GENERAL, label: "Generales (sin producto)" },
      ...(products.data ?? []).map((p) => ({ value: p.id, label: productOptionLabel(p) })),
    ],
    [products.data],
  );
  const typeOptions = useMemo<FilterOption[]>(
    () => (types.data ?? []).map((t) => ({ value: t.id, label: t.name })),
    [types.data],
  );
  const purposeOptions = useMemo<FilterOption[]>(
    () => purposes.items.map((item) => ({ value: item.code, label: item.label })),
    [purposes.items],
  );

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando requisitos" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los requisitos"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay requisitos con estos filtros"
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState title="Todavía no hay requisitos documentales" />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Requisitos"
        rows={rows}
        getRowId={(requirement) => requirement.id}
        onOpen={open}
        busy={busy}
        renderCard={(requirement) => (
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => open(requirement)}
                className="text-text-link min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium"
              >
                {requirement.document_type.name}
              </button>
              <span className="ml-auto shrink-0">
                <RequirementStatusBadge status={requirement.status} />
              </span>
            </div>
            <span className="text-text-secondary truncate text-sm">{scopeText(requirement)}</span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Requisitos"
        columns={columns}
        rows={rows}
        getRowId={(requirement) => requirement.id}
        sorting={parseOrdering(
          params.ordering,
          REQUIREMENT_SORT_FIELDS,
          defaultOrdering("requisitos"),
        )}
        sortableFields={REQUIREMENT_SORT_FIELDS}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        busy={busy}
        stickyColumn="document_type"
        minWidth={1000}
      />
    );
  }

  return (
    <>
      <section
        aria-label="Listado de requisitos"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          selects={[
            { key: "status", label: "Estado", value: params.status, options: STATUS_OPTIONS },
            {
              key: "product",
              label: "Producto",
              value: params.product,
              options: productOptions,
              loading: products.isPending,
              searchable: true,
            },
            {
              key: "doc_type",
              label: "Documento",
              value: params.doc_type,
              options: typeOptions,
              loading: types.isPending,
              searchable: true,
            },
            {
              key: "purpose",
              label: "Finalidad",
              value: params.purpose,
              options: purposeOptions,
              loading: purposes.isPending,
            },
            { key: "role", label: "Rol", value: params.role, options: ROLE_OPTIONS },
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
            itemsLabel="Requisitos"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>
      {params.abierto && (
        <RequirementPanel
          key={params.abierto}
          requirementId={params.abierto}
          permissions={permissions}
          onOpen={(id) => update({ abierto: id })}
          onClose={() => update({ abierto: "" })}
        />
      )}
      {creating && (
        <RequirementFormModal onClose={onCloseCreate} onSaved={(id) => update({ abierto: id })} />
      )}
    </>
  );
}
