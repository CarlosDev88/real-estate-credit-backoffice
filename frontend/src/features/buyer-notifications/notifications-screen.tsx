"use client";

import { Button } from "antd";
import { useId, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { TONE_CLASS } from "@/components/ui/status-badge";
import { PortalPage } from "@/features/buyer-portal/portal-shell";
import {
  sortNotifications,
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  type BuyerNotification,
} from "@/features/buyer-notifications/queries";
import { formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      width={20}
      height={20}
      aria-hidden="true"
      focusable="false"
      className={`text-text-tertiary flex-none transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
    >
      <path d="m5.4 7 4.6 4.6L14.6 7 16 8.4l-6 6-6-6L5.4 7Z" />
    </svg>
  );
}

/**
 * Un aviso: el título abre el mensaje (botón con `aria-expanded`). Al abrir uno sin leer,
 * se marca como leído. "Nuevo" va en texto, no solo con el punto de color.
 */
function NotificationItem({
  notification,
  open,
  onToggle,
}: {
  notification: BuyerNotification;
  open: boolean;
  onToggle: () => void;
}) {
  const id = useId();
  const unread = !notification.read_at;
  return (
    <li className="bg-bg-surface border-border-default rounded-xl border">
      <h2 className="m-0 text-base font-normal">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={onToggle}
          className="focus-visible:outline-focus-ring flex min-h-14 w-full cursor-pointer items-start gap-3 rounded-xl border-0 bg-transparent px-4 py-3 text-left text-inherit focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span className="grid min-w-0 flex-1 gap-1">
            <span className="flex flex-wrap items-center gap-2">
              {unread && (
                <span
                  className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium ${TONE_CLASS.info}`}
                >
                  <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
                  Nuevo
                </span>
              )}
              <span className="text-text-tertiary text-sm">
                {notification.notification_type_label}
              </span>
            </span>
            <span className={`text-md ${unread ? "font-semibold" : "font-medium"}`}>
              {notification.title}
            </span>
            <span className="text-text-tertiary text-sm">
              {formatDateTime(notification.created_at)}
            </span>
          </span>
          <ChevronIcon open={open} />
        </button>
      </h2>
      <div id={id} hidden={!open} className="text-text-secondary px-4 pb-4 whitespace-pre-line">
        {notification.message}
      </div>
    </li>
  );
}

/** Avisos del portal del comprador (`/portal/avisos`): no leídos primero. */
export function BuyerNotificationsScreen() {
  const toast = useToast();
  const list = useNotifications();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const [openId, setOpenId] = useState<string | null>(null);

  // Los que se abren en esta visita siguen arriba aunque ya estén leídos: no saltan.
  const [openedHere, setOpenedHere] = useState<ReadonlySet<string>>(new Set());
  const items = sortNotifications(
    list.data?.pages.flatMap((p) => p.items) ?? [],
    (n) => !n.read_at || openedHere.has(n.id),
  );
  const unread = items.filter((n) => !n.read_at).length;

  const toggle = (notification: BuyerNotification) => {
    const opening = openId !== notification.id;
    setOpenId(opening ? notification.id : null);
    if (opening && !notification.read_at) {
      setOpenedHere((prev) => new Set(prev).add(notification.id));
      markRead.mutate(notification.id);
    }
  };

  const readAll = () =>
    markAll.mutate(undefined, {
      onSuccess: (count) =>
        toast.success({
          title:
            count === 1 ? "1 aviso marcado como leído" : `${count} avisos marcados como leídos`,
        }),
    });

  let body;
  if (list.isPending)
    body = <LoadingState variant="portal" label="Cargando tus avisos" blocks={[88, 88, 88]} />;
  else if (list.isError) {
    body = (
      <ErrorState
        variant="page"
        title="No pudimos cargar tus avisos"
        message={list.error.message}
        onRetry={() => void list.refetch()}
        retrying={list.isRefetching}
      />
    );
  } else if (items.length === 0) {
    body = (
      <p className="text-text-secondary m-0">
        Todavía no tienes avisos. Aquí te contaremos cada avance de tu solicitud.
      </p>
    );
  } else {
    body = (
      <>
        <ul aria-label="Avisos" className="m-0 grid list-none gap-3 p-0">
          {items.map((n) => (
            <NotificationItem
              key={n.id}
              notification={n}
              open={openId === n.id}
              onToggle={() => toggle(n)}
            />
          ))}
        </ul>
        {list.hasNextPage && (
          <Button
            size="large"
            block
            loading={list.isFetchingNextPage}
            onClick={() => void list.fetchNextPage()}
          >
            Ver avisos anteriores
          </Button>
        )}
      </>
    );
  }

  return (
    <PortalPage>
      <PageHeader
        variant="portal"
        title="Tus avisos"
        description={
          list.data
            ? unread === 0
              ? "Estás al día."
              : unread === 1
                ? "Tienes 1 aviso sin leer."
                : `Tienes ${unread} avisos sin leer.`
            : undefined
        }
        actions={
          unread > 0 ? (
            <Button size="large" onClick={readAll} loading={markAll.isPending}>
              Marcar todos como leídos
            </Button>
          ) : undefined
        }
      />
      {body}
    </PortalPage>
  );
}
