"use client";

import { Alert, Button, Select } from "antd";
import { useEffect, useId, useState } from "react";

import { ActionModal } from "@/components/ui/action-modal";
import { FormField } from "@/components/ui/form-field";
import {
  useActiveSettlementApplicationIds,
  useDisbursedApplications,
  useSettleApplication,
  type CommissionSettlement,
} from "@/features/commissions/queries";
import { isApiError } from "@/lib/api/errors";
import { useIdempotencyKey } from "@/lib/api/idempotency";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

/** Solicitud ya elegida (desde la tarjeta "Comisión" del expediente). */
export interface SettleTarget {
  id: string;
  code: string;
}

interface SettleModalProps {
  open: boolean;
  onClose: () => void;
  /** Con solicitud elegida no se muestra el buscador. */
  target?: SettleTarget | null;
  /** Al liquidar (o al encontrar la vigente): abrir el detalle. */
  onSettled?: (settlement: CommissionSettlement) => void;
  /** Sin plan vigente (`422 COMMISSION_PLAN_NOT_FOUND`): ir a los planes, si se puede. */
  onGoToPlans?: () => void;
}

/**
 * "Liquidar a mano" una solicitud desembolsada que no tiene liquidación vigente
 * (`POST /applications/{id}/commission-settlement`). Si ya tenía una, la API la devuelve
 * sin crear otra y se avisa.
 */
export function SettleModal({ open, onClose, target, onSettled, onGoToPlans }: SettleModalProps) {
  const ids = useId();
  const toast = useToast();
  const showError = useApiErrorToast();
  const settle = useSettleApplication();
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const [selected, setSelected] = useState<string>("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [noPlan, setNoPlan] = useState<string | null>(null);
  const applicationId = target?.id ?? selected;
  const idempotency = useIdempotencyKey(applicationId);

  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), 300);
    return () => clearTimeout(id);
  }, [text]);

  // Al cerrar se vacía, para que la próxima vez abra sin la elección anterior.
  const close = () => {
    setSelected("");
    setText("");
    setFieldError(null);
    setNoPlan(null);
    onClose();
  };

  const options = useDisbursedApplications(term, open && !target);
  const settled = useActiveSettlementApplicationIds(open && !target);

  const submit = () => {
    setNoPlan(null);
    if (!applicationId) {
      setFieldError("Elige la solicitud.");
      return;
    }
    settle.mutate(
      { applicationId, key: idempotency.current() },
      {
        onSuccess: ({ settlement, created }) => {
          idempotency.reset();
          if (created) {
            toast.success({ title: "Comisión liquidada", message: settlement.application.code });
          } else {
            toast.info({
              title: "Ya tenía una liquidación vigente",
              message: `${settlement.application.code}: no se creó otra.`,
            });
          }
          close();
          onSettled?.(settlement);
        },
        onError: (error) => {
          if (isApiError(error) && error.code === "COMMISSION_PLAN_NOT_FOUND") {
            setNoPlan(error.message);
          } else showError(error);
        },
      },
    );
  };

  return (
    <ActionModal
      open={open}
      title="Liquidar a mano"
      description={
        target
          ? `Se liquida la comisión de ${target.code} con su último desembolso y el plan vigente del producto en esa fecha.`
          : "Elige una solicitud desembolsada. Se liquida con su último desembolso y el plan vigente del producto en esa fecha."
      }
      okText="Liquidar"
      loading={settle.isPending}
      onSubmit={submit}
      onCancel={close}
    >
      {!target && (
        <FormField id={`${ids}-application`} label="Solicitud" error={fieldError ?? undefined}>
          {(ctl) => (
            <Select
              {...ctl}
              showSearch={{ filterOption: false, onSearch: setText }}
              value={selected || undefined}
              onChange={(value: string) => {
                setSelected(value);
                setFieldError(null);
                setNoPlan(null);
              }}
              placeholder="Busca por código, nombre o cédula"
              notFoundContent={
                options.isFetching ? "Buscando…" : "No hay solicitudes desembolsadas con ese dato"
              }
              loading={options.isFetching}
              virtual={false}
              options={(options.data ?? []).map((a) => {
                const done = settled.data?.has(a.id) ?? false;
                return {
                  value: a.id,
                  disabled: done,
                  label: `${a.code} · ${a.applicant.full_name}${done ? " (ya liquidada)" : ""}`,
                };
              })}
            />
          )}
        </FormField>
      )}
      {noPlan && (
        <Alert
          type="warning"
          showIcon
          title="El producto no tiene un plan vigente en la fecha del desembolso"
          description={noPlan}
          action={
            onGoToPlans ? (
              <Button
                size="small"
                onClick={() => {
                  close();
                  onGoToPlans();
                }}
              >
                Ir a planes
              </Button>
            ) : undefined
          }
        />
      )}
    </ActionModal>
  );
}
