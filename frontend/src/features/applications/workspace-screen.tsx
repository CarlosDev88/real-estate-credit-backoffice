"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { EmptyState } from "@/components/ui/empty-state";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { DISBURSED } from "@/features/commissions/queries";
import { useFilings } from "@/features/filings/queries";
import { Card } from "@/components/ui/card";
import { BackLink } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { Stepper } from "@/components/ui/stepper";
import { useBootstrap } from "@/features/applications/queries";
import { useIdlePreload, useMountedOnce } from "@/lib/hooks/use-lazy";
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

// ---------- carga diferida (PERF-01) ----------
// Las pestañas que no son Resumen, los paneles de edición y la tarjeta de comisión no
// entran en la primera carga: se piden al usarlos y se precargan cuando el navegador
// queda libre (`useIdlePreload`).

const loadDocumentsTab = () => import("@/features/document-review/documents-tab");
const loadFilingsTab = () => import("@/features/filings/filings-tab");
const loadCommissionCard = () => import("@/features/commissions/commission-card");
const loadFinancingEdit = () => import("@/features/applications/financing-edit");
const loadParticipantEdit = () => import("@/features/applications/participant-edit");
const loadPropertyEdit = () => import("@/features/applications/property-edit");
const loadHistoryPanel = () => import("@/features/applications/status-history");

const TAB_PRELOADS = [loadDocumentsTab, loadFilingsTab, loadHistoryPanel] as const;
const EDIT_PRELOADS = [loadFinancingEdit, loadParticipantEdit, loadPropertyEdit] as const;

const DocumentsTab = dynamic(() => loadDocumentsTab().then((m) => m.DocumentsTab), {
  loading: () => <Loading label="Cargando los documentos" />,
});
const FilingsTab = dynamic(() => loadFilingsTab().then((m) => m.FilingsTab), {
  loading: () => <Loading label="Cargando la radicación" />,
});
const HistoryPanel = dynamic(() => loadHistoryPanel().then((m) => m.HistoryPanel), {
  loading: () => <Loading label="Cargando el historial" />,
});
const CommissionCard = dynamic(() => loadCommissionCard().then((m) => m.CommissionCard), {
  loading: () => <Loading label="Cargando la comisión" />,
});
const FinancingEditPanel = dynamic(() => loadFinancingEdit().then((m) => m.FinancingEditPanel));
const AddParticipantModal = dynamic(() => loadParticipantEdit().then((m) => m.AddParticipantModal));
const ParticipantPanel = dynamic(() => loadParticipantEdit().then((m) => m.ParticipantPanel));
const PropertyEditPanel = dynamic(() => loadPropertyEdit().then((m) => m.PropertyEditPanel));

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
  return (
    <>
      {/* Primero el detalle: el título y el subtítulo (el LCP) dependen de él. */}
      <WorkspaceContent id={id} />
      <WorkspacePrefetch id={id} />
    </>
  );
}

/**
 * Pide las secciones del expediente a la vez que el detalle: solo dependen del id (PERF-01).
 * Sin esto salían recién al llegar el detalle, una etapa más en la cadena. Usa las mismas
 * claves de caché que `Workspace`, que las encuentra en curso o ya resueltas. Va aparte para
 * que sus cambios de estado no vuelvan a pintar el expediente.
 */
function WorkspacePrefetch({ id }: { id: string }) {
  const permissions = usePermissions();
  // En orden: lo que pinta el subtítulo (participantes, inmueble) sale antes que el resto.
  useParticipants(id);
  useProperty(id);
  useBootstrap();
  useCompleteness(id);
  useFilings(id, permissions.has("filings.read"));
  useFinancing(id);
  useLatestEvaluation(id);
  useSlotsToReview(id);
  useLatestBuyerLink(id, permissions.has("buyer_access.read"));
  useConsents(id, permissions.has("consents.read"));
  useStatusHistory(id, 1);
  return null;
}

function WorkspaceContent({ id }: { id: string }) {
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

type Editing = "property" | "financing" | "add-participant" | null;
type Go = ReturnType<typeof useWorkspaceTab>["go"];

/**
 * El expediente con sus datos. Cada parte se suscribe solo a las consultas que usa
 * (encabezado, pestañas, cada tarjeta y los paneles): al llegar una respuesta se vuelve a
 * pintar esa parte, no el expediente entero (PERF-01; eran 12 repintados completos).
 */
function Workspace({ detail, version }: { detail: ApplicationDetail; version: number }) {
  const id = detail.id;
  const permissions = usePermissions();
  const { tab: requested, slot, go } = useWorkspaceTab();
  // La pestaña Radicación solo existe con `filings.read`; su conteo son las radicaciones.
  const canReadFilings = permissions.has("filings.read");
  const tab = requested === "radicacion" && !canReadFilings ? "resumen" : requested;
  // Edición del expediente (F7, Parte 3): con `applications.update`. El bloqueo después de
  // `FILED` lo responde la API y se muestra en el panel.
  const canEdit = permissions.has("applications.update");
  const [editing, setEditing] = useState<Editing>(null);
  const [participantId, setParticipantId] = useState<string | null>(null);
  useIdlePreload(TAB_PRELOADS);
  useIdlePreload(EDIT_PRELOADS, canEdit);

  const review = useCallback(
    (slot?: DocumentSlot) => go("documentos", slot ? { [SLOT_PARAM]: slot.id } : {}),
    [go],
  );

  return (
    <div className="grid max-w-[1148px] content-start gap-5">
      <BackToList />

      <WorkspaceHeader
        detail={detail}
        version={version}
        permissions={permissions}
        onReview={review}
      />

      <WorkspaceTabs id={id} tab={tab} canReadFilings={canReadFilings} go={go} />

      {tab === "resumen" && (
        <SummaryPanel
          detail={detail}
          permissions={permissions}
          canEdit={canEdit}
          go={go}
          onReview={review}
          onEdit={setEditing}
          onOpenParticipant={setParticipantId}
        />
      )}

      {canEdit && (
        <EditPanels
          detail={detail}
          version={version}
          editing={editing}
          participantId={participantId}
          onCloseEditing={() => setEditing(null)}
          onCloseParticipant={() => setParticipantId(null)}
        />
      )}

      {tab === "documentos" && (
        <section role="tabpanel" aria-label="Documentos">
          <DocumentsPanel id={id} permissions={permissions} slot={slot} go={go} />
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

/** Título, subtítulo, acciones, datos clave y etapas. */
function WorkspaceHeader({
  detail,
  version,
  permissions,
  onReview,
}: {
  detail: ApplicationDetail;
  version: number;
  permissions: Permissions;
  onReview: (slot?: DocumentSlot) => void;
}) {
  const id = detail.id;
  const completeness = useCompleteness(id);
  const participants = useParticipants(id);
  const property = useProperty(id);
  const financing = useFinancing(id);
  const toReview = useSlotsToReview(id);
  const firstToReview = toReview.data?.slots[0];

  return (
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
          onReview={() => onReview(firstToReview)}
        />
      </div>
      <KeyFacts detail={detail} property={property.data} financing={financing.data} />
      <Stepper stages={detail.progress_stages} ariaLabel="Etapas de la solicitud" />
    </section>
  );
}

function WorkspaceTabs({
  id,
  tab,
  canReadFilings,
  go,
}: {
  id: string;
  tab: WorkspaceTab;
  canReadFilings: boolean;
  go: Go;
}) {
  const filings = useFilings(id, canReadFilings);
  const completeness = useCompleteness(id);
  const pending = completeness.data
    ? Math.max(
        0,
        completeness.data.documents.required_total - completeness.data.documents.completed_total,
      )
    : null;

  return (
    <ScrollTabs
      ariaLabel="Secciones de la solicitud"
      value={tab}
      onChange={(key) => go(key as WorkspaceTab)}
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
  );
}

/** Pestaña Resumen: cada tarjeta pide (y escucha) solo su consulta. */
function SummaryPanel({
  detail,
  permissions,
  canEdit,
  go,
  onReview,
  onEdit,
  onOpenParticipant,
}: {
  detail: ApplicationDetail;
  permissions: Permissions;
  canEdit: boolean;
  go: Go;
  onReview: (slot?: DocumentSlot) => void;
  onEdit: (editing: Editing) => void;
  onOpenParticipant: (participantId: string) => void;
}) {
  const id = detail.id;
  const canReadLinks = permissions.has("buyer_access.read");
  const canReadConsents = permissions.has("consents.read");
  return (
    <section role="tabpanel" aria-label="Resumen" className="grid max-w-[1100px] gap-5">
      <CompletenessSection id={id} />
      <ToReviewSection id={id} onReview={onReview} onSeeAll={() => go("documentos")} />
      <EvaluationSection detail={detail} />
      {/* Parte 1 de la F7: estado de la liquidación de comisión del desembolso. */}
      {detail.status === DISBURSED && permissions.has("commissions.read") && (
        <CommissionCard
          applicationId={id}
          code={detail.code}
          canManage={permissions.has("commissions.manage")}
        />
      )}
      <ParticipantsSection
        id={id}
        onAdd={canEdit ? () => onEdit("add-participant") : undefined}
        onOpen={canEdit ? (p) => onOpenParticipant(p.id) : undefined}
      />
      <PropertySection id={id} onEdit={canEdit ? () => onEdit("property") : undefined} />
      <FinancingSection id={id} onEdit={canEdit ? () => onEdit("financing") : undefined} />
      {(canReadLinks || canReadConsents) && (
        <BuyerAccessSection
          detail={detail}
          canReadLinks={canReadLinks}
          canReadConsents={canReadConsents}
        />
      )}
      <RecentSection id={id} onSeeAll={() => go("historial")} />
    </section>
  );
}

function CompletenessSection({ id }: { id: string }) {
  const completeness = useCompleteness(id);
  return (
    <Section query={completeness} title="Completitud del expediente">
      {(data) => <CompletenessCard completeness={data} />}
    </Section>
  );
}

function ToReviewSection({
  id,
  onReview,
  onSeeAll,
}: {
  id: string;
  onReview: (slot?: DocumentSlot) => void;
  onSeeAll: () => void;
}) {
  const toReview = useSlotsToReview(id);
  return (
    <Section query={toReview} title="Por revisar">
      {(data) => (
        <ToReviewCard
          slots={data.slots}
          total={data.total}
          onReview={onReview}
          onSeeAll={onSeeAll}
        />
      )}
    </Section>
  );
}

function EvaluationSection({ detail }: { detail: ApplicationDetail }) {
  const evaluation = useLatestEvaluation(detail.id);
  return (
    <Section query={evaluation} title="Evaluación del banco">
      {(data) => <EvaluationCard evaluation={data} detail={detail} />}
    </Section>
  );
}

type ParticipantsCardProps = Parameters<typeof ParticipantsCard>[0];

function ParticipantsSection({
  id,
  onAdd,
  onOpen,
}: {
  id: string;
  onAdd?: ParticipantsCardProps["onAdd"];
  onOpen?: ParticipantsCardProps["onOpen"];
}) {
  const participants = useParticipants(id);
  return (
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
          onAdd={onAdd}
          onOpen={onOpen}
        />
      )}
    </Section>
  );
}

function PropertySection({ id, onEdit }: { id: string; onEdit?: () => void }) {
  const property = useProperty(id);
  return (
    <Section query={property} title="Inmueble">
      {(data) => <PropertyCard property={data} onEdit={onEdit} />}
    </Section>
  );
}

function FinancingSection({ id, onEdit }: { id: string; onEdit?: () => void }) {
  const financing = useFinancing(id);
  return (
    <Section query={financing} title="Financiación">
      {(data) => <FinancingCard financing={data} onEdit={onEdit} />}
    </Section>
  );
}

function BuyerAccessSection({
  detail,
  canReadLinks,
  canReadConsents,
}: {
  detail: ApplicationDetail;
  canReadLinks: boolean;
  canReadConsents: boolean;
}) {
  const link = useLatestBuyerLink(detail.id, canReadLinks);
  const consents = useConsents(detail.id, canReadConsents);
  return (
    <BuyerAccessCard
      link={canReadLinks ? (link.data ?? (link.isPending ? undefined : null)) : undefined}
      consents={canReadConsents ? (consents.data ?? []) : undefined}
      lastActivityAt={detail.last_buyer_activity_at}
    />
  );
}

function RecentSection({ id, onSeeAll }: { id: string; onSeeAll: () => void }) {
  const recent = useStatusHistory(id, 1);
  return (
    <Section query={recent} title="Últimos cambios de estado">
      {(data) => <RecentChangesCard entries={data.items.slice(0, 3)} onSeeAll={onSeeAll} />}
    </Section>
  );
}

/** Paneles de edición: cada uno se monta la primera vez que se abre y queda montado. */
function EditPanels({
  detail,
  version,
  editing,
  participantId,
  onCloseEditing,
  onCloseParticipant,
}: {
  detail: ApplicationDetail;
  version: number;
  editing: Editing;
  participantId: string | null;
  onCloseEditing: () => void;
  onCloseParticipant: () => void;
}) {
  const id = detail.id;
  const participants = useParticipants(id);
  const property = useProperty(id);
  const financing = useFinancing(id);
  const openParticipant = participants.participants?.find((p) => p.id === participantId) ?? null;
  const propertyMounted = useMountedOnce(editing === "property");
  const financingMounted = useMountedOnce(editing === "financing");
  const addMounted = useMountedOnce(editing === "add-participant");
  const participantMounted = useMountedOnce(participantId !== null);

  return (
    <>
      {propertyMounted && (
        <PropertyEditPanel
          detail={detail}
          version={version}
          property={property.data ?? null}
          open={editing === "property"}
          onClose={onCloseEditing}
        />
      )}
      {financingMounted && (
        <FinancingEditPanel
          detail={detail}
          version={version}
          financing={financing.data ?? null}
          open={editing === "financing"}
          onClose={onCloseEditing}
        />
      )}
      {addMounted && (
        <AddParticipantModal
          applicationId={id}
          participants={participants.participants ?? []}
          open={editing === "add-participant"}
          onClose={onCloseEditing}
        />
      )}
      {participantMounted && (
        <ParticipantPanel
          applicationId={id}
          version={version}
          participant={openParticipant}
          profile={openParticipant ? participants.profiles.get(openParticipant.id) : undefined}
          onClose={onCloseParticipant}
        />
      )}
    </>
  );
}

function DocumentsPanel({
  id,
  permissions,
  slot,
  go,
}: {
  id: string;
  permissions: Permissions;
  slot: string | null;
  go: Go;
}) {
  const participants = useParticipants(id);
  return (
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
  );
}
