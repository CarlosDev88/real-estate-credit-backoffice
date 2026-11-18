"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Input } from "antd";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { ActionModal } from "@/components/ui/action-modal";
import { DataList, Datum } from "@/components/ui/card";
import { FormField, useFormErrorHandler } from "@/components/ui/form-field";
import { Money } from "@/components/ui/money";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import {
  formatPct,
  ReviewBadge,
  SettlementStatusBadge,
  ShareStatusBadge,
} from "@/features/commissions/commission-badges";
import {
  bogotaDate,
  usePayShare,
  useSettlement,
  useVoidSettlement,
  type CommissionSettlement,
  type CommissionShare,
} from "@/features/commissions/queries";
import { isApiError } from "@/lib/api/errors";
import { useIdempotencyKey } from "@/lib/api/idempotency";
import { formatDateOnly, formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Límites del contrato (`SharePayRequest`, `SettlementVoidRequest`). */
export const REFERENCE_MAX = 100;
export const VOID_REASON_MAX = 255;

// ---------- pagar una parte ----------

const paySchema = (today: string) =>
  z.object({
    paid_at: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, { error: "Indica la fecha del pago." })
      .refine((v) => v <= today, { error: "La fecha del pago no puede ser futura." }),
    payment_reference: z
      .string()
      .trim()
      .min(1, { error: "Escribe la referencia del pago." })
      .max(REFERENCE_MAX, { error: `Máximo ${REFERENCE_MAX} caracteres.` }),
  });
type PayValues = z.infer<ReturnType<typeof paySchema>>;

export function PayShareModal({
  share,
  onClose,
}: {
  share: CommissionShare | null;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const pay = usePayShare();
  const today = bogotaDate(new Date());
  const idempotency = useIdempotencyKey(share?.id ?? "");
  const { control, handleSubmit, setError, reset, formState } = useForm<PayValues>({
    resolver: zodResolver(paySchema(today)),
    defaultValues: { paid_at: today, payment_reference: "" },
  });
  const onError = useFormErrorHandler<PayValues>(setError, ["paid_at", "payment_reference"]);

  useEffect(() => {
    if (share) reset({ paid_at: bogotaDate(new Date()), payment_reference: "" });
  }, [share, reset]);

  const submit = handleSubmit((values) => {
    if (!share) return;
    pay.mutate(
      {
        id: share.id,
        body: { paid_at: values.paid_at, payment_reference: values.payment_reference.trim() },
        key: idempotency.current(),
      },
      {
        onSuccess: () => {
          idempotency.reset();
          toast.success({ title: "Pago registrado", message: share.beneficiary.name });
          onClose();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={!!share}
      title="Registrar pago"
      description={
        share ? (
          <>
            Parte de {share.beneficiary_role_label.toLowerCase()} de{" "}
            <strong>{share.beneficiary.name}</strong>: <Money value={share.amount_cop} />. Queda
            como pagada con la fecha y la referencia.
          </>
        ) : undefined
      }
      okText="Registrar pago"
      loading={pay.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField
        id={`${ids}-paid-at`}
        label="Fecha del pago"
        error={formState.errors.paid_at?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="paid_at"
            render={({ field }) => <Input {...field} {...ctl} type="date" max={today} />}
          />
        )}
      </FormField>
      <FormField
        id={`${ids}-reference`}
        label="Referencia"
        help="Número de la transferencia o del comprobante."
        error={formState.errors.payment_reference?.message}
      >
        {(ctl) => (
          <Controller
            control={control}
            name="payment_reference"
            render={({ field }) => <Input {...field} {...ctl} maxLength={REFERENCE_MAX} />}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- anular ----------

const voidSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, { error: "Escribe el motivo." })
    .max(VOID_REASON_MAX, { error: `Máximo ${VOID_REASON_MAX} caracteres.` }),
});
type VoidValues = z.infer<typeof voidSchema>;

export function VoidSettlementModal({
  settlement,
  onClose,
}: {
  settlement: CommissionSettlement | null;
  onClose: () => void;
}) {
  const ids = useId();
  const toast = useToast();
  const voidIt = useVoidSettlement();
  const idempotency = useIdempotencyKey(settlement?.id ?? "");
  const { control, handleSubmit, setError, reset, formState } = useForm<VoidValues>({
    resolver: zodResolver(voidSchema),
    defaultValues: { reason: "" },
  });
  const onError = useFormErrorHandler<VoidValues>(setError, ["reason"]);

  useEffect(() => {
    if (settlement) reset({ reason: "" });
  }, [settlement, reset]);

  const submit = handleSubmit((values) => {
    if (!settlement) return;
    voidIt.mutate(
      { id: settlement.id, reason: values.reason.trim(), key: idempotency.current() },
      {
        onSuccess: () => {
          idempotency.reset();
          toast.success({ title: "Liquidación anulada", message: settlement.application.code });
          onClose();
        },
        onError,
      },
    );
  });

  return (
    <ActionModal
      open={!!settlement}
      title="Anular liquidación"
      description={
        settlement
          ? `La liquidación de ${settlement.application.code} y sus partes quedan anuladas. Después se puede volver a liquidar.`
          : undefined
      }
      okText="Anular liquidación"
      cancelText="Volver"
      danger
      loading={voidIt.isPending}
      onSubmit={submit}
      onCancel={onClose}
    >
      <FormField id={`${ids}-reason`} label="Motivo" error={formState.errors.reason?.message}>
        {(ctl) => (
          <Controller
            control={control}
            name="reason"
            render={({ field }) => (
              <Input.TextArea {...field} {...ctl} rows={3} maxLength={VOID_REASON_MAX} />
            )}
          />
        )}
      </FormField>
    </ActionModal>
  );
}

// ---------- detalle ----------

function ShareItem({
  share,
  canPay,
  onPay,
}: {
  share: CommissionShare;
  canPay: boolean;
  onPay: () => void;
}) {
  return (
    <li className="border-border-default grid gap-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-text-tertiary text-xs">{share.beneficiary_role_label}</div>
          <div className="font-medium">{share.beneficiary.name}</div>
        </div>
        <ShareStatusBadge code={share.status} label={share.status_label} />
      </div>
      <DataList layout="inline">
        <Datum label="Porción">{formatPct(share.share_pct)}</Datum>
        <Datum label="Monto">
          <Money value={share.amount_cop} />
        </Datum>
        {share.paid_at && <Datum label="Fecha del pago">{formatDateOnly(share.paid_at)}</Datum>}
        {share.payment_reference && <Datum label="Referencia">{share.payment_reference}</Datum>}
        {share.paid_by && <Datum label="Registró el pago">{share.paid_by.name}</Datum>}
      </DataList>
      {canPay && share.status === "PENDING" && (
        <div>
          <Button onClick={onPay}>Registrar pago</Button>
        </div>
      )}
    </li>
  );
}

function SettlementDetail({
  settlement,
  canManage,
  onPay,
}: {
  settlement: CommissionSettlement;
  canManage: boolean;
  onPay: (share: CommissionShare) => void;
}) {
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <SettlementStatusBadge code={settlement.status} label={settlement.status_label} />
        {settlement.needs_review && <ReviewBadge />}
      </div>
      {settlement.needs_review && (
        <Alert
          type="warning"
          showIcon
          title="Revisión pendiente"
          description="La liquidación quedó marcada para revisarla a mano antes de pagar o anular."
        />
      )}
      <DataList layout="inline">
        <Datum label="Solicitud">
          <Link href={`/solicitudes/${settlement.application.id}`} className="text-text-link">
            {settlement.application.code}
          </Link>
        </Datum>
        <Datum label="Desembolso">{formatDateOnly(settlement.disbursed_on)}</Datum>
        <Datum label="Origen">{settlement.lead_origin_label}</Datum>
        <Datum label="Base">
          <Money value={settlement.base_amount_cop} />
        </Datum>
        <Datum label="Tasa">{formatPct(settlement.rate_pct)}</Datum>
        <Datum label="Total">
          <Money value={settlement.total_amount_cop} />
        </Datum>
        <Datum label="Liquidada">{formatDateTime(settlement.created_at)}</Datum>
        {settlement.status === "VOIDED" && (
          <>
            <Datum label="Anulada">{formatDateTime(settlement.voided_at)}</Datum>
            <Datum label="Anuló">{settlement.voided_by?.name}</Datum>
            <Datum label="Motivo">{settlement.void_reason}</Datum>
          </>
        )}
      </DataList>
      <section aria-labelledby="settlement-shares" className="grid gap-2">
        <h3 id="settlement-shares" className="m-0 text-base font-semibold">
          Partes
        </h3>
        {settlement.shares.length === 0 ? (
          <p className="text-text-secondary m-0 text-sm">Esta liquidación no tiene partes.</p>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0">
            {settlement.shares.map((share) => (
              <ShareItem
                key={share.id}
                share={share}
                canPay={canManage && settlement.status === "ACTIVE"}
                onPay={() => onPay(share)}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Detalle de una liquidación en el panel lateral: datos, partes, "Registrar pago" en cada
 * parte pendiente y "Anular liquidación" (sin pagos) para quien tiene `commissions.manage`.
 */
export function SettlementPanel({
  id,
  initial,
  canManage,
  onClose,
}: {
  id: string | null;
  /** La fila del listado, si está en la página: se muestra sin esperar el detalle. */
  initial?: CommissionSettlement;
  canManage: boolean;
  onClose: () => void;
}) {
  const query = useSettlement(id, initial);
  const [paying, setPaying] = useState<CommissionShare | null>(null);
  const [voiding, setVoiding] = useState<CommissionSettlement | null>(null);
  const settlement = query.data;
  const hasPayments = settlement?.shares.some((s) => s.status === "PAID") ?? false;
  const canVoid = canManage && settlement?.status === "ACTIVE";

  let body;
  if (query.isPending) body = <LoadingState label="Cargando la liquidación" blocks={[96, 96]} />;
  else if (query.isError) {
    body =
      isApiError(query.error) && query.error.status === 404 ? (
        <p className="text-text-secondary m-0 text-sm">No encontramos esta liquidación.</p>
      ) : (
        <ErrorState
          variant="inline"
          title="No pudimos cargar la liquidación."
          onRetry={() => void query.refetch()}
        />
      );
  } else {
    body = <SettlementDetail settlement={query.data} canManage={canManage} onPay={setPaying} />;
  }

  return (
    <>
      <SidePanel
        open={!!id}
        onClose={onClose}
        eyebrow="Liquidación de comisión"
        title={settlement?.application.code ?? "Liquidación"}
        footer={
          canVoid ? (
            <div className="grid gap-2">
              {hasPayments && (
                <p className="text-text-secondary m-0 text-sm">
                  Tiene partes pagadas: no se puede anular.
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button onClick={onClose}>Cerrar</Button>
                <Button
                  danger
                  disabled={hasPayments}
                  onClick={() => settlement && setVoiding(settlement)}
                >
                  Anular liquidación
                </Button>
              </div>
            </div>
          ) : undefined
        }
      >
        {body}
      </SidePanel>
      <PayShareModal share={paying} onClose={() => setPaying(null)} />
      <VoidSettlementModal settlement={voiding} onClose={() => setVoiding(null)} />
    </>
  );
}
