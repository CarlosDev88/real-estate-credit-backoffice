"use client";

import { Button } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataList, Datum } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ActiveStatusBadge } from "@/features/admin-common/active-status";
import { ReasonModal } from "@/features/admin-common/reason-modal";
import { BankFormModal } from "@/features/admin-banks/bank-form-modal";
import { productHref } from "@/features/admin-banks/list-params";
import { ProductFormModal } from "@/features/admin-banks/product-form-modal";
import { useBank, useSetBankActive } from "@/features/admin-banks/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

export interface BankPermissions {
  /** `banks.create`: productos nuevos. */
  canCreate: boolean;
  /** `banks.update`: editar, activar y desactivar. */
  canUpdate: boolean;
}

type Modal = "edit" | "status" | "product" | null;

/** Panel lateral del banco (`GET /banks/{id}`): datos y sus productos. */
export function BankPanel({
  bankId,
  permissions,
  onClose,
}: {
  bankId: string;
  permissions: BankPermissions;
  onClose: () => void;
}) {
  const router = useRouter();
  const toast = useToast();
  const query = useBank(bankId);
  const setActive = useSetBankActive(bankId);
  const [modal, setModal] = useState<Modal>(null);
  const bank = query.data;
  const activate = bank?.status === "INACTIVE";
  const close = () => setModal(null);

  let body;
  if (query.isPending) {
    body = <LoadingState label="Cargando banco" blocks={[24, 24, 24, 24, 80]} />;
  } else if (query.isError) {
    const gone = isApiError(query.error) && query.error.status === 404;
    body = (
      <ErrorState
        variant="page"
        title={gone ? "Este banco ya no existe" : "No pudimos cargar el banco"}
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  } else {
    const data = query.data;
    body = (
      <div className="grid gap-6">
        <DataList layout="inline">
          <Datum label="Código">
            <span className="font-mono">{data.code}</span>
          </Datum>
          <Datum label="Nombre">{data.name}</Datum>
          <Datum label="Nombre corto">{data.short_name}</Datum>
          <Datum label="NIT">{data.tax_id}</Datum>
          <Datum label="Estado">
            <ActiveStatusBadge status={data.status} />
          </Datum>
          <Datum label="Notas operativas">
            {data.operational_notes && (
              <span className="whitespace-pre-line">{data.operational_notes}</span>
            )}
          </Datum>
          <Datum label="Actualizado">{formatDateTime(data.updated_at)}</Datum>
        </DataList>

        <section aria-labelledby="bank-products" className="grid gap-2">
          <div className="flex items-center gap-2">
            <h3 id="bank-products" className="m-0 flex-1 text-base font-semibold">
              Productos
            </h3>
            {permissions.canCreate && (
              <Button size="small" onClick={() => setModal("product")}>
                Nuevo producto
              </Button>
            )}
          </div>
          {data.products.length === 0 ? (
            <EmptyState
              size="sm"
              title="Este banco todavía no tiene productos"
              description={
                permissions.canCreate
                  ? "Crea uno para definir montos, plazos, finalidades y reglas."
                  : undefined
              }
            />
          ) : (
            <ul aria-label="Productos" className="m-0 grid list-none p-0">
              {data.products.map((product) => (
                <li
                  key={product.id}
                  className="border-border-default flex items-center gap-2 border-b py-2 text-sm last:border-b-0"
                >
                  <div className="grid min-w-0">
                    <Link
                      href={productHref(product.id)}
                      className="text-text-link truncate font-medium no-underline hover:underline"
                    >
                      {product.name}
                    </Link>
                    <span className="text-text-tertiary font-mono text-xs">{product.code}</span>
                  </div>
                  <span className="ml-auto shrink-0">
                    <ActiveStatusBadge status={product.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    );
  }

  const footer = bank && permissions.canUpdate && (
    <div className="flex flex-wrap gap-2">
      <Button danger={!activate} onClick={() => setModal("status")}>
        {activate ? "Activar" : "Desactivar"}
      </Button>
      <div className="flex-1" />
      <Button type="primary" onClick={() => setModal("edit")}>
        Editar
      </Button>
    </div>
  );

  return (
    <>
      <SidePanel
        open
        onClose={onClose}
        eyebrow="Banco"
        title={bank?.name ?? "Banco"}
        footer={footer || undefined}
        width={560}
      >
        {body}
      </SidePanel>
      {bank && modal === "edit" && <BankFormModal bank={bank} onClose={close} />}
      {bank && modal === "product" && (
        <ProductFormModal
          bankId={bank.id}
          onClose={close}
          onCreated={(product) => router.push(productHref(product.id))}
        />
      )}
      {bank && modal === "status" && (
        <ReasonModal
          title={activate ? "Activar banco" : "Desactivar banco"}
          description={
            activate
              ? `Los productos activos y vigentes de ${bank.name} vuelven a estar disponibles.`
              : `Mientras esté inactivo, sus productos no aparecen entre los disponibles para las solicitudes.`
          }
          okText={activate ? "Activar" : "Desactivar"}
          reasonRequired={false}
          danger={!activate}
          loading={setActive.isPending}
          onConfirm={(reason) => setActive.mutateAsync({ active: activate, reason })}
          onDone={() => {
            toast.success({ title: activate ? "Banco activado" : "Banco desactivado" });
            close();
          }}
          onCancel={close}
        />
      )}
    </>
  );
}
