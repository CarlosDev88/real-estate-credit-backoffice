"use client";

import { Alert, Button } from "antd";
import { useMemo, useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { useShellTrail } from "@/components/ui/app-shell";
import { Card, DataList, Datum } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PlusIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ActiveStatusBadge } from "@/features/admin-common/active-status";
import { ArrowDownIcon, ArrowUpIcon } from "@/features/admin-common/icons";
import { CatalogFormModal, ItemFormModal } from "@/features/admin-catalogs/catalog-modals";
import { CATALOGS_HREF, SystemBadge } from "@/features/admin-catalogs/catalogs-screen";
import { move, orderChanged, positionText } from "@/features/admin-catalogs/order";
import {
  MAX_ITEMS,
  useCatalogDetail,
  useCatalogItems,
  useReorderCatalogItems,
  useSetCatalogItemActive,
  type Catalog,
  type CatalogItem,
} from "@/features/admin-catalogs/queries";
import { useMe } from "@/features/auth/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateOnly, formatInteger } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

interface ItemsProps {
  catalog: Catalog;
  canCreate: boolean;
  canUpdate: boolean;
}

/**
 * Valores del catálogo en su orden. Subir y bajar mueve de a un puesto (con teclado y
 * lector de pantalla: se anuncia el puesto nuevo); "Guardar orden" manda todos los valores
 * (`PUT .../items/order`). Un catálogo del sistema queda en solo lectura.
 */
function CatalogItems({ catalog, canCreate, canUpdate }: ItemsProps) {
  const toast = useToast();
  const showError = useApiErrorToast();
  const items = useCatalogItems(catalog.id);
  const reorder = useReorderCatalogItems(catalog.id);
  const setActive = useSetCatalogItemActive(catalog.id);
  const [draft, setDraft] = useState<CatalogItem[] | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [editing, setEditing] = useState<CatalogItem | "new" | null>(null);
  const [toggling, setToggling] = useState<CatalogItem | null>(null);

  const original = useMemo(() => items.data?.items ?? [], [items.data]);
  const rows = draft ?? original;
  const manageable = catalog.is_manageable;
  const tooMany = (items.data?.total ?? 0) > MAX_ITEMS;
  const canReorder = manageable && canUpdate && !tooMany && rows.length > 1;
  const dirty = draft !== null && orderChanged(original, draft);

  const moveItem = (index: number, delta: -1 | 1) => {
    const next = move(rows, index, delta);
    setDraft(next);
    const item = rows[index]!;
    setAnnouncement(positionText(item.label, index + delta, next.length));
  };

  const save = () =>
    reorder.mutate(
      rows.map((item) => item.id),
      {
        onSuccess: () => {
          setDraft(null);
          toast.success({ title: "Orden guardado" });
        },
        onError: (error) => showError(error),
      },
    );

  const confirmToggle = () => {
    if (!toggling) return;
    setActive.mutate(
      { id: toggling.id, active: !toggling.is_active },
      {
        onSuccess: () => {
          toast.success({ title: toggling.is_active ? "Valor desactivado" : "Valor activado" });
          setToggling(null);
        },
        onError: (error) => {
          setToggling(null);
          showError(error);
        },
      },
    );
  };

  let body;
  if (items.isPending) {
    body = <LoadingState label="Cargando valores" blocks={[44, 44, 44]} />;
  } else if (items.isError) {
    body = (
      <ErrorState
        title="No pudimos cargar los valores"
        message={items.error.message}
        onRetry={() => void items.refetch()}
        retrying={items.isFetching}
      />
    );
  } else if (rows.length === 0) {
    body = <EmptyState size="sm" title="Este catálogo todavía no tiene valores" />;
  } else {
    body = (
      <ol aria-label="Valores del catálogo" className="m-0 grid list-none p-0">
        {rows.map((item, index) => (
          <li
            key={item.id}
            className="border-border-default flex flex-wrap items-center gap-x-3 gap-y-1 border-b py-2 text-sm last:border-b-0"
          >
            <span className="text-text-tertiary w-6 text-right tabular-nums" aria-hidden="true">
              {index + 1}
            </span>
            <div className="grid min-w-0 flex-1">
              <span className="truncate font-medium">{item.label}</span>
              <span className="text-text-tertiary font-mono text-xs">{item.code}</span>
            </div>
            {(item.valid_from || item.valid_to) && (
              <span className="text-text-tertiary text-xs">
                {formatDateOnly(item.valid_from) ?? "…"} – {formatDateOnly(item.valid_to) ?? "…"}
              </span>
            )}
            <ActiveStatusBadge status={item.is_active ? "ACTIVE" : "INACTIVE"} />
            {manageable && canUpdate && (
              <div className="flex gap-1">
                {canReorder && (
                  <>
                    <Button
                      size="small"
                      icon={<ArrowUpIcon />}
                      disabled={index === 0 || reorder.isPending}
                      onClick={() => moveItem(index, -1)}
                      aria-label={`Subir ${item.label}`}
                    />
                    <Button
                      size="small"
                      icon={<ArrowDownIcon />}
                      disabled={index === rows.length - 1 || reorder.isPending}
                      onClick={() => moveItem(index, 1)}
                      aria-label={`Bajar ${item.label}`}
                    />
                  </>
                )}
                <Button
                  size="small"
                  onClick={() => setEditing(item)}
                  aria-label={`Editar ${item.label}`}
                >
                  Editar
                </Button>
                <Button
                  size="small"
                  danger={item.is_active}
                  onClick={() => setToggling(item)}
                  aria-label={`${item.is_active ? "Desactivar" : "Activar"} ${item.label}`}
                >
                  {item.is_active ? "Desactivar" : "Activar"}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
    );
  }

  return (
    <section aria-labelledby="catalog-items" className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="catalog-items" className="m-0 flex-1 text-xl font-semibold">
          Valores
          {items.data && (
            <span className="text-text-tertiary ml-2 text-sm font-normal">
              {formatInteger(items.data.total)}
            </span>
          )}
        </h2>
        {manageable && canCreate && (
          <Button icon={<PlusIcon />} onClick={() => setEditing("new")} disabled={dirty}>
            Nuevo valor
          </Button>
        )}
      </div>
      {tooMany && (
        <Alert
          type="info"
          showIcon
          title={`Se muestran los primeros ${MAX_ITEMS} valores`}
          description="Con más valores, el orden no se cambia desde aquí."
        />
      )}
      {dirty && (
        <div
          role="region"
          aria-label="Orden sin guardar"
          className="bg-bg-subtle border-border-default flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm"
        >
          <span className="flex-1">
            Cambiaste el orden. Se aplica a todos los formularios al guardarlo.
          </span>
          <Button size="small" onClick={() => setDraft(null)} disabled={reorder.isPending}>
            Descartar
          </Button>
          <Button size="small" type="primary" onClick={save} loading={reorder.isPending}>
            Guardar orden
          </Button>
        </div>
      )}
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <div className="bg-bg-surface border-border-default rounded-lg border px-4">{body}</div>

      {editing && (
        <ItemFormModal
          catalogId={catalog.id}
          item={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ActionModal
        open={toggling !== null}
        title={
          toggling?.is_active ? `Desactivar ${toggling.label}` : `Activar ${toggling?.label ?? ""}`
        }
        description={
          toggling?.is_active
            ? "Deja de ofrecerse en los formularios. Los registros que ya lo usan lo conservan."
            : "Vuelve a ofrecerse en los formularios."
        }
        okText={toggling?.is_active ? "Desactivar" : "Activar"}
        danger={toggling?.is_active}
        loading={setActive.isPending}
        onSubmit={confirmToggle}
        onCancel={() => setToggling(null)}
      />
    </section>
  );
}

/** `/admin/catalogos/[id]`: datos del catálogo y sus valores, con su orden. */
export function CatalogScreen({ catalogId }: { catalogId: string }) {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const has = (code: string) => permissions.includes(code);
  const query = useCatalogDetail(catalogId);
  const [editing, setEditing] = useState(false);
  const catalog = query.data;
  useShellTrail(catalog?.name);

  if (query.isPending) return <LoadingState label="Cargando catálogo" blocks={[72, 120, 240]} />;
  if (query.isError || !catalog) {
    const gone = isApiError(query.error) && query.error.status === 404;
    return (
      <ErrorState
        variant="page"
        titleAs="h1"
        title={gone ? "Este catálogo no existe" : "No pudimos cargar el catálogo"}
        message={query.error?.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }

  const canUpdate = has("catalogs.update");
  return (
    <div className="grid content-start gap-6">
      <PageHeader
        back={{ href: CATALOGS_HREF, label: "Volver a catálogos" }}
        title={catalog.name}
        description={catalog.description || undefined}
        actions={
          catalog.is_manageable &&
          canUpdate && <Button onClick={() => setEditing(true)}>Editar catálogo</Button>
        }
      />
      {!catalog.is_manageable && (
        <Alert
          type="info"
          showIcon
          title="Catálogo del sistema: solo lectura"
          description="Sus valores los define la aplicación y no se cambian desde aquí."
        />
      )}
      <Card title="Datos del catálogo">
        <DataList columns={3}>
          <Datum label="Código">
            <span className="font-mono">{catalog.code}</span>
          </Datum>
          <Datum label="Visibilidad">{catalog.is_public ? "Público" : "Interno"}</Datum>
          <Datum label="Versión">
            {catalog.version} <SystemBadge catalog={catalog} />
          </Datum>
        </DataList>
      </Card>
      <CatalogItems catalog={catalog} canCreate={has("catalogs.create")} canUpdate={canUpdate} />
      {editing && <CatalogFormModal catalog={catalog} onClose={() => setEditing(false)} />}
    </div>
  );
}
