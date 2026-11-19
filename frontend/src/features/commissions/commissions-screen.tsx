"use client";

import { Button } from "antd";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { useMe } from "@/features/auth/queries";
import { useCommissionParams, type CommissionTab } from "@/features/commissions/commissions-params";
import { PlansTab } from "@/features/commissions/plans-tab";
import { SettleModal } from "@/features/commissions/settle-modal";
import { SettlementsTab } from "@/features/commissions/settlements-tab";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const MOBILE_QUERY = "(max-width: 860px)";

/**
 * Comisiones (`/comisiones`, con `commissions.read`): "Liquidaciones" y, con
 * `commission_plans.read`, "Planes". Pestaña, filtros, página y el detalle abierto van en
 * la URL.
 */
export function CommissionsScreen() {
  const me = useMe();
  const permissions = useMemo(() => new Set(me.data?.permissions ?? []), [me.data]);
  const canPlans = permissions.has("commission_plans.read");
  const canManage = permissions.has("commissions.manage");
  const { params, updateSettlements, updatePlans, setTab, openSettlement } = useCommissionParams();
  const tab: CommissionTab = params.tab === "planes" && !canPlans ? "liquidaciones" : params.tab;
  const mobile = useMediaQuery(MOBILE_QUERY);
  const [settleOpen, setSettleOpen] = useState(false);

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Comisiones"
        description="Liquidaciones de los desembolsos, pagos a asesores y brokers, y planes por producto."
        actions={
          canManage && tab === "liquidaciones" ? (
            <Button type="primary" onClick={() => setSettleOpen(true)}>
              Liquidar a mano
            </Button>
          ) : undefined
        }
      />

      {canPlans && (
        <ScrollTabs
          ariaLabel="Comisiones"
          items={[
            { key: "liquidaciones", label: "Liquidaciones" },
            { key: "planes", label: "Planes" },
          ]}
          value={tab}
          onChange={(key) => setTab(key as CommissionTab)}
        />
      )}

      {tab === "liquidaciones" ? (
        <SettlementsTab
          params={params.settlements}
          openId={params.open}
          permissions={permissions}
          mobile={mobile}
          onChange={updateSettlements}
          onOpen={openSettlement}
        />
      ) : (
        <PlansTab
          params={params.plans}
          canManage={permissions.has("commission_plans.manage")}
          canReadProducts={permissions.has("banks.read")}
          mobile={mobile}
          onChange={updatePlans}
        />
      )}

      {canManage && (
        <SettleModal
          open={settleOpen}
          onClose={() => setSettleOpen(false)}
          onSettled={(settlement) => openSettlement(settlement.id)}
          onGoToPlans={canPlans ? () => setTab("planes") : undefined}
        />
      )}
    </div>
  );
}
