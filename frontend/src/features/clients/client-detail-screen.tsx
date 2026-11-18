"use client";

import { Button } from "antd";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { useShellTrail } from "@/components/ui/app-shell";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { ApplicationsTab } from "@/features/clients/applications-tab";
import { BackLink, WithClient } from "@/features/clients/client-screens";
import { DocumentCell } from "@/features/clients/components/client-cells";
import { useClientTab, type ClientTab } from "@/features/clients/detail-tabs";
import { OpportunitiesTab } from "@/features/clients/opportunities-tab";
import { OpportunityPanel, type PanelPermissions } from "@/features/clients/opportunity-panel";
import { CLIENTS_HREF, editClientHref, type ClientDetail } from "@/features/clients/queries";
import { SummaryTab } from "@/features/clients/summary-tab";

function usePermissions() {
  const me = useMe();
  const granted = me.data?.permissions;
  return useMemo(() => {
    const set = new Set(granted ?? []);
    return (code: string) => set.has(code);
  }, [granted]);
}

function ClientHeader({ client, canEdit }: { client: ClientDetail; canEdit: boolean }) {
  const router = useRouter();
  return (
    <header className="flex flex-wrap items-start gap-3">
      <div className="grid min-w-0 flex-1 gap-1">
        <h1 className="m-0 text-3xl font-semibold tracking-tight">{client.full_name}</h1>
        <div className="text-text-secondary flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <DocumentCell client={client} />
          {client.email && <span>{client.email}</span>}
          {client.phone && <span className="tabular-nums">{client.phone}</span>}
          {client.origin && <span>Origen: {client.origin.label}</span>}
        </div>
      </div>
      {canEdit && <Button onClick={() => router.push(editClientHref(client.id))}>Editar</Button>}
    </header>
  );
}

const TAB_LABELS: Record<ClientTab, string> = {
  resumen: "Resumen",
  oportunidades: "Oportunidades",
  solicitudes: "Solicitudes",
};

function ClientDetailView({ client }: { client: ClientDetail }) {
  useShellTrail(client.full_name);
  const has = usePermissions();
  const me = useMe();
  const { tab: requested, opportunityId, go } = useClientTab();
  const canReadApplications = has("applications.read");
  const canReadOpportunities = has("opportunities.read");
  const canEdit = has("clients.update");

  // Una pestaña sin permiso vuelve al resumen.
  const allowed: ClientTab[] = [
    "resumen",
    ...(canReadOpportunities ? (["oportunidades"] as const) : []),
    ...(canReadApplications ? (["solicitudes"] as const) : []),
  ];
  const tab = allowed.includes(requested) ? requested : "resumen";

  const panel: PanelPermissions = {
    canAssign: has("opportunities.assign") && has("users.read"),
    canCreateApplication: has("applications.create"),
    canListAdvisors: has("users.read"),
    selfAssignId: has("opportunities.assign") && !has("users.read") ? (me.data?.id ?? null) : null,
  };

  return (
    <div className="grid content-start gap-4">
      <BackLink href={CLIENTS_HREF}>Volver a clientes</BackLink>
      <ClientHeader client={client} canEdit={canEdit} />

      <ScrollTabs
        ariaLabel="Secciones del cliente"
        value={tab}
        onChange={(key) => go(key as ClientTab)}
        items={allowed.map((key) => ({ key, label: TAB_LABELS[key] }))}
      />

      {tab === "resumen" && (
        <div role="tabpanel" aria-label="Resumen">
          <SummaryTab client={client} canEdit={canEdit} />
        </div>
      )}
      {tab === "oportunidades" && (
        <div role="tabpanel" aria-label="Oportunidades">
          <OpportunitiesTab
            client={client}
            canCreate={has("opportunities.create")}
            onOpen={(id) => go("oportunidades", id)}
          />
          <OpportunityPanel
            clientId={client.id}
            opportunityId={opportunityId}
            permissions={panel}
            onClose={() => go("oportunidades")}
          />
        </div>
      )}
      {tab === "solicitudes" && (
        <div role="tabpanel" aria-label="Solicitudes">
          <ApplicationsTab clientId={client.id} />
        </div>
      )}
    </div>
  );
}

/** `/clientes/[id]` (REQ §6 vista 6): encabezado y pestañas en `?tab=`. */
export function ClientDetailScreen({ id }: { id: string }) {
  return <WithClient id={id}>{(client) => <ClientDetailView client={client} />}</WithClient>;
}
