"use client";

import { Button } from "antd";
import Link from "next/link";
import { useState } from "react";

import { Card, DataList, Datum } from "@/components/ui/card";
import { Money } from "@/components/ui/money";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import {
  formatPct,
  ReviewBadge,
  SettlementStatusBadge,
  ShareStatusBadge,
} from "@/features/commissions/commission-badges";
import { useApplicationSettlement } from "@/features/commissions/queries";
import { SettleModal } from "@/features/commissions/settle-modal";
import { formatDateOnly } from "@/lib/format";

/**
 * Tarjeta "Comisión" del expediente desembolsado (con `commissions.read`): estado de la
 * liquidación y de cada parte, con enlace al detalle en `/comisiones`. Sin liquidación
 * vigente, quien tiene `commissions.manage` puede liquidar a mano.
 */
export function CommissionCard({
  applicationId,
  code,
  canManage,
}: {
  applicationId: string;
  code: string;
  canManage: boolean;
}) {
  const query = useApplicationSettlement(applicationId, true);
  const [settleOpen, setSettleOpen] = useState(false);
  const settlement = query.data;
  const canSettle = canManage && query.isSuccess && settlement?.status !== "ACTIVE";

  let body;
  if (query.isPending) body = <LoadingState label="Cargando la comisión" blocks={[64]} />;
  else if (query.isError) {
    body = (
      <ErrorState
        variant="inline"
        title="No pudimos cargar la comisión."
        onRetry={() => void query.refetch()}
      />
    );
  } else if (!settlement) {
    body = (
      <p className="text-text-secondary m-0 text-sm">
        Esta solicitud todavía no tiene liquidación de comisión.
      </p>
    );
  } else {
    body = (
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <SettlementStatusBadge code={settlement.status} label={settlement.status_label} />
          {settlement.needs_review && <ReviewBadge />}
        </div>
        <DataList layout="inline">
          <Datum label="Desembolso">{formatDateOnly(settlement.disbursed_on)}</Datum>
          <Datum label="Tasa">{formatPct(settlement.rate_pct)}</Datum>
          <Datum label="Total">
            <Money value={settlement.total_amount_cop} />
          </Datum>
          {settlement.shares.map((share) => (
            <Datum
              key={share.id}
              label={`${share.beneficiary_role_label} · ${share.beneficiary.name}`}
            >
              <span className="inline-flex flex-wrap items-center gap-2">
                <Money value={share.amount_cop} />
                <ShareStatusBadge code={share.status} label={share.status_label} />
              </span>
            </Datum>
          ))}
        </DataList>
      </div>
    );
  }

  return (
    <Card
      title="Comisión"
      action={
        <>
          {settlement && (
            <Link
              href={`/comisiones?liquidacion=${settlement.id}`}
              className="text-text-link text-sm"
            >
              Ver liquidación
            </Link>
          )}
          {canSettle && (
            <Button size="small" onClick={() => setSettleOpen(true)}>
              Liquidar
            </Button>
          )}
        </>
      }
    >
      {body}
      {canManage && (
        <SettleModal
          open={settleOpen}
          onClose={() => setSettleOpen(false)}
          target={{ id: applicationId, code }}
        />
      )}
    </Card>
  );
}
