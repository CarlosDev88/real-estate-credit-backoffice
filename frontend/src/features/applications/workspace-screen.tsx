"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { CommissionCard } from "@/features/commissions/commission-card";
import { DISBURSED } from "@/features/commissions/queries";
import { DocumentsTab } from "@/features/document-review/documents-tab";
import { FilingsTab } from "@/features/filings/filings-tab";
import { useFilings } from "@/features/filings/queries";
import { Card } from "@/components/ui/card";
import { BackLink } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { Stepper } from "@/components/ui/stepper";
import { FinancingEditPanel } from "@/features/applications/financing-edit";
import { AddParticipantModal, ParticipantPanel } from "@/features/applications/participant-edit";
import { PropertyEditPanel } from "@/features/applications/property-edit";
import { HistoryPanel } from "@/features/applications/status-history";
import {
  BuyerAccessCard,
  CompletenessCard,
  EvaluationCard,
  FinancingCard,
  ParticipantsCard,
  PropertyCard,
  RecentChangesCard,
  ToReviewCard,
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

export const TABS = ["resumen", "documentos", "radicacion", "historial"] as const;
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

function BackToList() {
  return <BackLink href="/solicitudes">Volver a solicitudes</BackLink>;
}

function Loading({ label }: { label: string }) {
  return <LoadingState label={label} blocks={[96]} />;
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
        <ErrorState
          variant="inline"
          title="No pudimos cargar esta sección."
          onRetry={() => void query.refetch()}
        />
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
      <BackToList />
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
        <BackToList />
        <ErrorState
          title="No pudimos cargar la solicitud"
          message={query.error.message}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      </div>
    );
  }
  return <Workspace detail={query.data.detail} version={query.data.version} />;
}

function Workspace({ detail, version }: { detail: ApplicationDetail; version: number }) {
  const id = detail.id;
  const permissions = usePermissions();
  const { tab: requested, slot, go } = useWorkspaceTab();
  // La pestaña Radicación solo existe con `filings.read`; su conteo son las radicaciones.
  const canReadFilings = permissions.has("filings.read");
  const filings = useFilings(id, canReadFilings);
  const tab = requested === "radicacion" && !canReadFilings ? "resumen" : requested;

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
  // Edición del expediente (F7, Parte 3): con `applications.update`. El bloqueo después de
  // `FILED` lo responde la API y se muestra en el panel.
  const canEdit = permissions.has("applications.update");
  const [editing, setEditing] = useState<"property" | "financing" | "add-participant" | null>(null);
  const [participantId, setParticipantId] = useState<string | null>(null);
  const openParticipant = participants.participants?.find((p) => p.id === participantId) ?? null;

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
      <BackToList />

      <section
        aria-labelledby="workspace-title"
        className="bg-bg-surface border-border-default grid gap-4 rounded-lg border p-4 min-[861px]:p-5"
      >
        {/* Como en el mockup: título y subtítulo, y debajo las acciones con su razón. */}
        <div className="grid gap-3">
          <div id="workspace-title" className="min-w-0">
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
        <Stepper stages={detail.progress_stages} ariaLabel="Etapas de la solicitud" />
      </section>

      <ScrollTabs
        ariaLabel="Secciones de la solicitud"
        value={tab}
        onChange={(key) => go(key as typeof tab)}
        items={[
          { key: "resumen", label: "Resumen" },
          // Mockup `solicitud.html`: "Documentos 6 pendientes", en tono de advertencia.
          {
            key: "documentos",
            label: "Documentos",
            ...(pending
              ? { countLabel: `${pending} ${pending === 1 ? "pendiente" : "pendientes"}` }
              : {}),
            countTone: "warning" as const,
          },
          ...(canReadFilings
            ? [{ key: "radicacion", label: "Radicación", count: filings.data?.total }]
            : []),
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
          {/* Parte 1 de la F7: estado de la liquidación de comisión del desembolso. */}
          {detail.status === DISBURSED && permissions.has("commissions.read") && (
            <CommissionCard
              application={{
                id,
                bankId: detail.bank_product?.bank.id ?? null,
                createdAt: detail.created_at,
                stageStartedAt: detail.current_stage_started_at,
              }}
              code={detail.code}
              canManage={permissions.has("commissions.manage")}
            />
          )}
          <Section
            query={{
              data: participants.participants,
              isPending: participants.isPending,
              isError: participants.isError,
              refetch: participants.refetch,
            }}
            title="Participantes"
          >
            {(data) => (
              <ParticipantsCard
                participants={data}
                profiles={participants.profiles}
                onAdd={canEdit ? () => setEditing("add-participant") : undefined}
                onOpen={canEdit ? (p) => setParticipantId(p.id) : undefined}
              />
            )}
          </Section>
          <Section query={property} title="Inmueble">
            {(data) => (
              <PropertyCard
                property={data}
                onEdit={canEdit ? () => setEditing("property") : undefined}
              />
            )}
          </Section>
          <Section query={financing} title="Financiación">
            {(data) => (
              <FinancingCard
                financing={data}
                onEdit={canEdit ? () => setEditing("financing") : undefined}
              />
            )}
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
                onSeeAll={() => go("historial")}
              />
            )}
          </Section>
        </section>
      )}

      {canEdit && (
        <>
          <PropertyEditPanel
            detail={detail}
            version={version}
            property={property.data ?? null}
            open={editing === "property"}
            onClose={() => setEditing(null)}
          />
          <FinancingEditPanel
            detail={detail}
            version={version}
            financing={financing.data ?? null}
            open={editing === "financing"}
            onClose={() => setEditing(null)}
          />
          <AddParticipantModal
            applicationId={id}
            participants={participants.participants ?? []}
            open={editing === "add-participant"}
            onClose={() => setEditing(null)}
          />
          <ParticipantPanel
            applicationId={id}
            version={version}
            participant={openParticipant}
            profile={openParticipant ? participants.profiles.get(openParticipant.id) : undefined}
            onClose={() => setParticipantId(null)}
          />
        </>
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

      {tab === "radicacion" && (
        <section role="tabpanel" aria-label="Radicación">
          <FilingsTab
            detail={detail}
            version={version}
            permissions={permissions}
            onOpenDocument={(slotId) => go("documentos", { [SLOT_PARAM]: slotId })}
          />
        </section>
      )}

      {tab === "historial" && (
        <section
          role="tabpanel"
          aria-label="Historial"
          className="bg-bg-surface border-border-default rounded-lg border p-5"
        >
          <HistoryPanel applicationId={id} />
        </section>
      )}
    </div>
  );
}
