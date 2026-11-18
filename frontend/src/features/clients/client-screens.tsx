"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { EmptyState } from "@/components/ui/empty-state";
import { BackLink, PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useMe } from "@/features/auth/queries";
import {
  ClientForm,
  EMPTY_CLIENT,
  toCreateBody,
  toUpdateBody,
  valuesFromClient,
} from "@/features/clients/client-form";
import {
  clientHref,
  CLIENTS_HREF,
  useClient,
  useCreateClient,
  useUpdateClient,
  type ClientDetail,
} from "@/features/clients/queries";
import { isApiError } from "@/lib/api/errors";
import { useToast } from "@/providers/toast";

export function usePermission(code: string): boolean | undefined {
  const me = useMe();
  return me.data?.permissions.includes(code);
}

function NotFound() {
  return (
    <div className="grid content-start gap-4">
      <BackLink href={CLIENTS_HREF}>Volver a clientes</BackLink>
      <div className="bg-bg-surface border-border-default rounded-lg border">
        <EmptyState
          title="No encontramos este cliente o no tienes acceso"
          action={
            <Link href={CLIENTS_HREF} className="text-text-link underline">
              Ir al listado de clientes
            </Link>
          }
        />
      </div>
    </div>
  );
}

function NoPermission({ title, back }: { title: string; back: string }) {
  return (
    <div className="grid content-start gap-4">
      <BackLink href={back}>Volver</BackLink>
      <div className="bg-bg-surface border-border-default rounded-lg border">
        <EmptyState title={title} description="Pide el permiso a un administrador." />
      </div>
    </div>
  );
}

/** Esqueleto, 404 o error con "Reintentar" del detalle de un cliente; si no, `children`. */
export function WithClient({
  id,
  children,
}: {
  id: string;
  children: (client: ClientDetail) => ReactNode;
}) {
  const query = useClient(id);
  if (query.isPending) return <LoadingState label="Cargando el cliente" blocks={[96]} />;
  if (query.isError) {
    if (isApiError(query.error) && query.error.status === 404) return <NotFound />;
    return (
      <div className="grid content-start gap-4">
        <BackLink href={CLIENTS_HREF}>Volver a clientes</BackLink>
        <ErrorState
          title="No pudimos cargar el cliente"
          message={query.error.message}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      </div>
    );
  }
  return <>{children(query.data)}</>;
}

function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return <PageHeader title={title} description={subtitle} />;
}

/** `/clientes/nuevo` (REQ §6 vista 5): al crear, va al detalle. */
export function NewClientScreen() {
  useShellTrail("Nuevo cliente");
  const router = useRouter();
  const toast = useToast();
  const create = useCreateClient();
  const allowed = usePermission("clients.create");

  if (allowed === undefined) return <LoadingState label="Cargando" blocks={[96]} />;
  if (!allowed) {
    return <NoPermission title="No tienes permiso para crear clientes" back={CLIENTS_HREF} />;
  }

  return (
    <div className="grid max-w-3xl content-start gap-4">
      <BackLink href={CLIENTS_HREF}>Volver a clientes</BackLink>
      <PageTitle
        title="Nuevo cliente"
        subtitle="Con el cliente creado podrás registrar sus oportunidades y solicitudes."
      />
      <ClientForm
        mode="create"
        initial={EMPTY_CLIENT}
        cancelHref={CLIENTS_HREF}
        submitting={create.isPending}
        onSubmit={async (values) => {
          const client = await create.mutateAsync(toCreateBody(values));
          toast.success({ title: "Cliente creado", message: client.full_name });
          router.push(clientHref(client.id));
        }}
      />
    </div>
  );
}

function EditClient({ client }: { client: ClientDetail }) {
  useShellTrail(client.full_name);
  const router = useRouter();
  const toast = useToast();
  const update = useUpdateClient(client.id);
  const back = clientHref(client.id);

  return (
    <div className="grid max-w-3xl content-start gap-4">
      <BackLink href={back}>Volver al cliente</BackLink>
      <PageTitle title="Editar cliente" subtitle={client.full_name} />
      <ClientForm
        mode="edit"
        initial={valuesFromClient(client)}
        current={{ document_type: client.document_type, origin: client.origin }}
        cancelHref={back}
        submitting={update.isPending}
        onSubmit={async (values, dirty) => {
          await update.mutateAsync(toUpdateBody(values, dirty));
          toast.success({ title: "Cambios guardados" });
          router.push(back);
        }}
      />
    </div>
  );
}

/** `/clientes/[id]/editar`: `PATCH /clients/{id}` con los campos cambiados. */
export function EditClientScreen({ id }: { id: string }) {
  const allowed = usePermission("clients.update");
  if (allowed === undefined) return <LoadingState label="Cargando" blocks={[96]} />;
  if (!allowed) {
    return <NoPermission title="No tienes permiso para editar clientes" back={clientHref(id)} />;
  }
  return <WithClient id={id}>{(client) => <EditClient client={client} />}</WithClient>;
}
