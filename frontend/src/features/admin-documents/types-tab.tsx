"use client";

import { Button } from "antd";
import { useEffect, useMemo, useState } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { CardList, DataTable, dataColumns } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ActiveStatusBadge } from "@/features/admin-common/active-status";
import { AdminListFilters, type FilterOption } from "@/features/admin-common/list-filters";
import { formatOrdering, parseOrdering } from "@/features/admin-common/list-params";
import { ListSkeleton } from "@/features/admin-common/list-skeleton";
import { ReasonModal } from "@/features/admin-common/reason-modal";
import { HOLDER_SCOPE_LABELS, labelIn, mimeText } from "@/features/admin-documents/labels";
import {
  defaultOrdering,
  TYPE_SORT_FIELDS,
  type DocumentsParams,
} from "@/features/admin-documents/list-params";
import {
  useDocumentType,
  useDocumentTypes,
  useSetDocumentTypeActive,
  type DocumentType,
} from "@/features/admin-documents/queries";
import { TypeFormModal } from "@/features/admin-documents/type-form-modal";
import { isApiError } from "@/lib/api/errors";
import { formatBytes, formatDateTime, formatInteger } from "@/lib/format";
import { useToast } from "@/providers/toast";

const ACTIVE_OPTIONS: FilterOption[] = [
  { value: "true", label: "Activo" },
  { value: "false", label: "Inactivo" },
];
const statusOf = (type: Pick<DocumentType, "is_active">) =>
  type.is_active ? "ACTIVE" : "INACTIVE";

export interface DocumentPermissions {
  canCreate: boolean;
  canUpdate: boolean;
  canPublish: boolean;
}

function TypePanel({
  typeId,
  permissions,
  onClose,
}: {
  typeId: string;
  permissions: DocumentPermissions;
  onClose: () => void;
}) {
  const toast = useToast();
  const query = useDocumentType(typeId);
  const setActive = useSetDocumentTypeActive(typeId);
  const [modal, setModal] = useState<"edit" | "status" | null>(null);
  const type = query.data;
  const activate = type ? !type.is_active : false;
  const close = () => setModal(null);

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando tipo documental" blocks={[24, 24, 24, 24]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Este tipo documental ya no existe" : "No pudimos cargar el tipo documental"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    const data = query.data;
    body = (
      <DataList layout="inline">
        <Datum label="Código">
          <span className="font-mono">{data.code}</span>
        </Datum>
        <Datum label="Estado">
          <ActiveStatusBadge status={statusOf(data)} />
        </Datum>
        <Datum label="Descripción">{data.description}</Datum>
        <Datum label="Formatos">{mimeText(data.allowed_mime_types)}</Datum>
        <Datum label="Tamaño máximo">{formatBytes(data.max_size_bytes)}</Datum>
        <Datum label="Vigencia sugerida">
          {data.default_validity_days ? `${formatInteger(data.default_validity_days)} días` : null}
        </Datum>
        <Datum label="Se pide">{labelIn(HOLDER_SCOPE_LABELS, data.holder_scope)}</Datum>
        <Datum label="Varias cargas">{data.is_repeatable ? "Sí" : "No"}</Datum>
        <Datum label="Actualizado">{formatDateTime(data.updated_at)}</Datum>
      </DataList>
    );
  }

  const footer = type && (permissions.canUpdate || permissions.canPublish) && (
    <div className="flex flex-wrap gap-2">
      {permissions.canPublish && (
        <Button danger={!activate} onClick={() => setModal("status")}>
          {activate ? "Activar" : "Desactivar"}
        </Button>
      )}
      <div className="flex-1" />
      {permissions.canUpdate && (
        <Button type="primary" onClick={() => setModal("edit")}>
          Editar
        </Button>
      )}
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Tipo documental"
        title={type?.name ?? "Tipo documental"}
        footer={footer || undefined}
      >
        {body}
      </SidePanel>
      {type && modal === "edit" && <TypeFormModal type={type} onClose={close} />}
      {type && modal === "status" && (
        <ReasonModal
          title={activate ? "Activar tipo documental" : "Desactivar tipo documental"}
          description={
            activate
              ? "Sus requisitos publicados vuelven a aplicarse a los casos nuevos."
              : "Sus requisitos dejan de aplicarse a casos nuevos y no se pueden publicar mientras esté inactivo. Los expedientes ya armados no cambian."
          }
          okText={activate ? "Activar" : "Desactivar"}
          reasonRequired={false}
          danger={!activate}
          loading={setActive.isPending}
          onConfirm={(reason) => setActive.mutateAsync({ active: activate, reason })}
          onDone={() => {
            toast.success({
              title: activate ? "Tipo documental activado" : "Tipo documental desactivado",
            });
            close();
          }}
          onCancel={close}
        />
      )}
    </>
  );
}

const helper = dataColumns<DocumentType>();
const makeColumns = (open: (type: DocumentType) => void) =>
  helper.columns([
    helper.accessor((row) => row.name, {
      id: "name",
      header: "Tipo documental",
      cell: ({ row }) => (
        <button
          type="button"
          onClick={() => open(row.original)}
          className="text-text-link max-w-[280px] cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium hover:underline"
        >
          {row.original.name}
        </button>
      ),
    }),
    helper.accessor((row) => row.code, {
      id: "code",
      header: "Código",
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.code}</span>,
    }),
    helper.display({
      id: "formats",
      header: "Formatos",
      cell: ({ row }) => (
        <span className="text-sm">{mimeText(row.original.allowed_mime_types)}</span>
      ),
    }),
    helper.display({
      id: "size",
      header: "Tamaño máximo",
      cell: ({ row }) => (
        <span className="text-sm tabular-nums">{formatBytes(row.original.max_size_bytes)}</span>
      ),
    }),
    helper.display({
      id: "scope",
      header: "Se pide",
      cell: ({ row }) => (
        <span className="text-sm">{labelIn(HOLDER_SCOPE_LABELS, row.original.holder_scope)}</span>
      ),
    }),
    helper.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => <ActiveStatusBadge status={statusOf(row.original)} />,
    }),
  ]);

/** Pestaña "Tipos": `GET /document-types` con búsqueda y estado; el detalle va en un panel. */
export function TypesTab({
  params,
  update,
  permissions,
  mobile,
  creating,
  onCreated,
  onCloseCreate,
}: {
  params: DocumentsParams;
  update: (patch: Partial<DocumentsParams>) => void;
  permissions: DocumentPermissions;
  mobile: boolean;
  creating: boolean;
  onCreated: (type: DocumentType) => void;
  onCloseCreate: () => void;
}) {
  const list = useDocumentTypes(params, true);
  const open = (type: DocumentType) => update({ abierto: type.id });
  const columns = useMemo(() => makeColumns((type) => update({ abierto: type.id })), [update]);
  const clear = () => update({ search: "", active: "" });
  const filtered = params.search !== "" || params.active !== "";
  const rows = list.data?.items ?? [];
  const busy = list.isFetching && list.isPlaceholderData;

  const pageGone = isApiError(list.error) && list.error.status === 404 && params.page > 1;
  useEffect(() => {
    if (pageGone) update({ page: 1 });
  }, [pageGone, update]);

  let body;
  if (list.isPending) {
    body = <ListSkeleton label="Cargando tipos documentales" />;
  } else if (list.isError) {
    body = (
      <div className="p-3">
        <ErrorState
          title="No pudimos cargar los tipos documentales"
          message={list.error.message}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  } else if (rows.length === 0) {
    body = filtered ? (
      <EmptyState
        title="No hay tipos documentales con estos filtros"
        action={
          <Button size="small" onClick={clear}>
            Limpiar filtros
          </Button>
        }
      />
    ) : (
      <EmptyState title="Todavía no hay tipos documentales" />
    );
  } else if (mobile) {
    body = (
      <CardList
        ariaLabel="Tipos documentales"
        rows={rows}
        getRowId={(type) => type.id}
        onOpen={open}
        busy={busy}
        renderCard={(type) => (
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => open(type)}
                className="text-text-link min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium"
              >
                {type.name}
              </button>
              <span className="ml-auto shrink-0">
                <ActiveStatusBadge status={statusOf(type)} />
              </span>
            </div>
            <span className="text-text-secondary text-sm">
              {mimeText(type.allowed_mime_types)} · {formatBytes(type.max_size_bytes)}
            </span>
          </>
        )}
      />
    );
  } else {
    body = (
      <DataTable
        ariaLabel="Tipos documentales"
        columns={columns}
        rows={rows}
        getRowId={(type) => type.id}
        sorting={parseOrdering(params.ordering, TYPE_SORT_FIELDS, defaultOrdering("tipos"))}
        sortableFields={TYPE_SORT_FIELDS}
        onSort={(sorting) => update({ ordering: formatOrdering(sorting) })}
        onOpen={open}
        busy={busy}
        stickyColumn="name"
        minWidth={860}
      />
    );
  }

  return (
    <>
      <section
        aria-label="Listado de tipos documentales"
        className="bg-bg-surface border-border-default overflow-hidden rounded-lg border"
      >
        <AdminListFilters
          search={{
            value: params.search,
            placeholder: "Nombre o código",
            ariaLabel: "Buscar tipos documentales por nombre o código",
          }}
          onSearch={(search) => update({ search })}
          selects={[
            { key: "active", label: "Estado", value: params.active, options: ACTIVE_OPTIONS },
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
            itemsLabel="Tipos"
            onPage={(page) => update({ page })}
            onPageSize={(page_size) => update({ page_size })}
            compact={mobile}
          />
        )}
      </section>
      {params.abierto && (
        <TypePanel
          key={params.abierto}
          typeId={params.abierto}
          permissions={permissions}
          onClose={() => update({ abierto: "" })}
        />
      )}
      {creating && <TypeFormModal onClose={onCloseCreate} onCreated={onCreated} />}
    </>
  );
}
