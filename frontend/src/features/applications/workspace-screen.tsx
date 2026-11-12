"use client";

import { Alert, Button } from "antd";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { ReactNode } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { DocumentsTab } from "@/features/document-review/documents-tab";
import { HistoryPanel, useStatusLabels } from "@/features/applications/status-history";
import {
  BuyerAccessCard,
  CompletenessCard,
  EvaluationCard,
  Muted,
  ParticipantsCard,
  PropertyCard,
  RecentChangesCard,
  ToReviewCard,
  Card,
} from "@/features/applications/summary-cards";
import {
  KeyFacts,
  WorkspaceActions,
  WorkspaceSubtitle,
  WorkspaceTitle,
  type Permissions,
} from "@/features/applications/workspace-header";
import {
  useApplicationDetail,
  useCompleteness,
  useConsents,
  useFinancing,
  useLatestBuyerLink,
  useLatestEvaluation,
  useParticipants,
  useProperty,
  useSlotsToReview,
  useStatusHistory,
  type ApplicationDetail,
  type DocumentSlot,
} from "@/features/applications/workspace-queries";
import { isApiError } from "@/lib/api/errors";

export const TABS = ["resumen", "documentos", "historial"] as const;
export type WorkspaceTab = (typeof TABS)[number];
const DEFAULT_TAB: WorkspaceTab = "resumen";
/** Parámetro con el slot que abre el panel de revisión (pestaña Documentos). */
export const SLOT_PARAM = "slot";

/** Pestaña activa en `?tab=` (la de por defecto no se escribe). */
export function useWorkspaceTab() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = searchParams.get("tab");
  const tab: WorkspaceTab = (TABS as readonly string[]).includes(raw ?? "")
    ? (raw as WorkspaceTab)
    : DEFAULT_TAB;

  const go = useCallback(
    (next: WorkspaceTab, extra: Record<string, string> = {}) => {
      const query = new URLSearchParams();
      if (next !== DEFAULT_TAB) query.set("tab", next);
      for (const [key, value] of Object.entries(extra)) query.set(key, value);
      const qs = query.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );
  const slot = tab === "documentos" ? searchParams.get(SLOT_PARAM) : null;
  return { tab, slot, go };
}

function BackLink() {
  return (
    <Link
      href="/solicitudes"
      className="text-text-secondary hover:text-text-primary inline-flex w-fit items-center gap-1 text-sm no-underline"
    >
      <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="m12.6 4 1.4 1.4L9.4 10l4.6 4.6-1.4 1.4-6-6 6-6Z" />
      </svg>
      Volver a solicitudes
    </Link>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="bg-bg-surface border-border-default h-24 animate-pulse rounded-lg border"
    />
  );
}

/** Tarjeta que depende de una consulta: esqueleto, error en línea con "Reintentar" o contenido. */
function Section<T>({
  query,
  title,
  children,
}: {
  query: { data: T | undefined; isPending: boolean; isError: boolean; refetch: () => unknown };
  title: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Loading label={`Cargando ${title.toLowerCase()}`} />;
  if (query.isError || query.data === undefined) {
    return (
      <Card title={title}>
        <div className="flex items-center gap-2" role="alert">
          <Muted>No pudimos cargar esta sección.</Muted>
          <Button size="small" onClick={() => void query.refetch()}>
            Reintentar
          </Button>
        </div>
      </Card>
    );
  }
  return <>{children(query.data)}</>;
}

function usePermissions(): Permissions {
  const me = useMe();
  const granted = me.data?.permissions;
  return useMemo(() => {
    const set = new Set(granted ?? []);
    return { has: (code: string) => set.has(code) };
  }, [granted]);
}

function NotFound() {
  return (
    <div className="grid content-start gap-4">
      <BackLink />
      <div className="bg-bg-surface border-border-default rounded-lg border">
        <EmptyState
          title="No encontramos esta solicitud o no tienes acceso"
          action={
            <Link href="/solicitudes" className="text-text-link underline">
              Ir al listado de solicitudes
            </Link>
          }
        />
      </div>
    </div>
  );
}

/** Expediente de una solicitud (`/solicitudes/[id]`, mockup `solicitud.html`). */
export function WorkspaceScreen({ id }: { id: string }) {
  const query = useApplicationDetail(id);
  useShellTrail(query.data?.detail.code);

  if (query.isPending) return <Loading label="Cargando la solicitud" />;
  if (query.isError) {
    if (isApiError(query.error) && query.error.status === 404) return <NotFound />;
    return (
      <div className="grid content-start gap-4">
        <BackLink />
        <Alert
          type="error"
          showIcon
          title="No pudimos cargar la solicitud"
          description={query.error.message}
          action={
            <Button size="small" onClick={() => void query.refetch()}>
              Reintentar
            </Button>
          }
        />
      </div>
    );
  }
  return <Workspace detail={query.data.detail} version={query.data.version} />;
}

function Workspace({ detail, version }: { detail: ApplicationDetail; version: number }) {
  const id = detail.id;
  const permissions = usePermissions();
  const { tab, slot, go } = useWorkspaceTab();

  const completeness = useCompleteness(id);
  const participants = useParticipants(id);
  const property = useProperty(id);
  const financing = useFinancing(id);
  const evaluation = useLatestEvaluation(id);
  const toReview = useSlotsToReview(id);
  const canReadLinks = permissions.has("buyer_access.read");
  const canReadConsents = permissions.has("consents.read");
  const link = useLatestBuyerLink(id, canReadLinks);
  const consents = useConsents(id, canReadConsents);
  const recent = useStatusHistory(id, 1);
  const labels = useStatusLabels(detail.status, detail.status_label);

  const pending = completeness.data
    ? Math.max(
        0,
        completeness.data.documents.required_total - completeness.data.documents.completed_total,
      )
    : null;

  const review = (slot?: DocumentSlot) => go("documentos", slot ? { [SLOT_PARAM]: slot.id } : {});
  const firstToReview = toReview.data?.slots[0];

  return (
    <div className="grid max-w-[1148px] content-start gap-5">
      <BackLink />

      <section
        aria-labelledby="workspace-title"
        className="bg-bg-surface border-border-default grid gap-4 rounded-lg border p-4 min-[861px]:p-5"
      >
        <div className="flex flex-wrap items-start gap-3">
          <div id="workspace-title" className="min-w-0 flex-1">
            <WorkspaceTitle detail={detail} />
            <WorkspaceSubtitle
              detail={detail}
              participants={participants.participants}
              property={property.data}
            />
          </div>
          <WorkspaceActions
            detail={detail}
            version={version}
            completeness={completeness.data}
            toReview={toReview.data?.total ?? 0}
            permissions={permissions}
            onReview={() => review(firstToReview)}
          />
        </div>
        <KeyFacts detail={detail} property={property.data} financing={financing.data} />
      </section>

      <ScrollTabs
        ariaLabel="Secciones de la solicitud"
        value={tab}
        onChange={(key) => go(key as typeof tab)}
        items={[
          { key: "resumen", label: "Resumen" },
          { key: "documentos", label: "Documentos", count: pending ?? undefined },
          { key: "historial", label: "Historial" },
        ]}
      />

      {tab === "resumen" && (
        <section role="tabpanel" aria-label="Resumen" className="grid max-w-[1100px] gap-5">
          <Section query={completeness} title="Completitud del expediente">
            {(data) => <CompletenessCard completeness={data} />}
          </Section>
          <Section query={toReview} title="Por revisar">
            {(data) => (
              <ToReviewCard
                slots={data.slots}
                total={data.total}
                onReview={review}
                onSeeAll={() => go("documentos")}
              />
            )}
          </Section>
          <Section query={evaluation} title="Evaluación del banco">
            {(data) => <EvaluationCard evaluation={data} detail={detail} />}
          </Section>
          <Section
            query={{
              data: participants.participants,
              isPending: participants.isPending,
              isError: participants.isError,
              refetch: participants.refetch,
            }}
            title="Participantes"
          >
            {(data) => <ParticipantsCard participants={data} profiles={participants.profiles} />}
          </Section>
          <Section query={property} title="Inmueble">
            {(data) => <PropertyCard property={data} />}
          </Section>
          {(canReadLinks || canReadConsents) && (
            <BuyerAccessCard
              link={canReadLinks ? (link.data ?? (link.isPending ? undefined : null)) : undefined}
              consents={canReadConsents ? (consents.data ?? []) : undefined}
              lastActivityAt={detail.last_buyer_activity_at}
            />
          )}
          <Section query={recent} title="Últimos cambios de estado">
            {(data) => (
              <RecentChangesCard
                entries={data.items.slice(0, 3)}
                labels={labels}
                onSeeAll={() => go("historial")}
              />
            )}
          </Section>
        </section>
      )}

      {tab === "documentos" && (
        <section role="tabpanel" aria-label="Documentos">
          <DocumentsTab
            applicationId={id}
            participants={participants.participants ?? []}
            profiles={participants.profiles}
            can={{
              review: permissions.has("documents.review"),
              waive: permissions.has("documents.waive"),
              download: permissions.has("documents.download"),
            }}
            openSlotId={slot}
            onOpenSlot={(slotId) => go("documentos", slotId ? { [SLOT_PARAM]: slotId } : {})}
          />
        </section>
      )}

      {tab === "historial" && (
        <section
          role="tabpanel"
          aria-label="Historial"
          className="bg-bg-surface border-border-default rounded-lg border p-5"
        >
          <HistoryPanel applicationId={id} labels={labels} />
        </section>
      )}
    </div>
  );
}
