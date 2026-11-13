"use client";

import { Button, Dropdown, type MenuProps } from "antd";
import { useState } from "react";

import { Money } from "@/components/ui/money";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  BuyerLinkModal,
  ReassignModal,
  TransitionModal,
  WithdrawModal,
} from "@/features/applications/action-modals";
import { bankLabel } from "@/features/applications/queries";
import {
  useEvaluateRules,
  type ApplicationDetail,
  type AvailableAction,
  type Completeness,
  type Financing,
  type Participant,
  type Property,
} from "@/features/applications/workspace-queries";
import { formatPercentDecimal } from "@/lib/format";
import { useToast } from "@/providers/toast";

/** Guarda de "lista para radicar" (API §16.3): su resultado es `completeness.ready_to_file`. */
const READY_TO_FILE_GUARD = "APPLICATION_READY_TO_FILE";
/** El desistimiento no es una transición: va por `/withdrawals` (API §16.3). */
const WITHDRAWN = "WITHDRAWN";
/** Razones de bloqueo que se ven bajo las acciones; el resto, en la tarjeta de completitud. */
const MAX_REASONS = 3;

export interface Permissions {
  has: (code: string) => boolean;
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={16} height={16} aria-hidden="true">
      <circle cx="4" cy="10" r="1.6" />
      <circle cx="10" cy="10" r="1.6" />
      <circle cx="16" cy="10" r="1.6" />
    </svg>
  );
}

type Dialog =
  | { kind: "transition"; action: AvailableAction }
  | { kind: "withdraw" }
  | { kind: "reassign" }
  | { kind: "link" }
  | null;

interface ActionsProps {
  detail: ApplicationDetail;
  version: number;
  completeness: Completeness | undefined;
  toReview: number;
  permissions: Permissions;
  onReview: () => void;
}

/**
 * Acciones del expediente. Las transiciones salen de `available_actions`: la primera es
 * la principal y las demás van en "Más acciones". Si "lista para radicar" no cumple su
 * guarda, queda deshabilitada con la razón visible y, si hay documentos por revisar, la
 * principal pasa a revisarlos (design/README.md, "una acción principal… que se pueda ejecutar").
 */
export function WorkspaceActions({
  detail,
  version,
  completeness,
  toReview,
  permissions,
  onReview,
}: ActionsProps) {
  const [dialog, setDialog] = useState<Dialog>(null);
  const toast = useToast();
  const evaluate = useEvaluateRules(detail.id);
  const closed = detail.closed_at !== null;

  const transitions = detail.available_actions.filter((a) => a.target_status !== WITHDRAWN);
  const canWithdraw =
    permissions.has("applications.withdraw") &&
    detail.available_actions.some((a) => a.target_status === WITHDRAWN);
  const notReady = completeness !== undefined && !completeness.ready_to_file;
  const blocked = notReady
    ? transitions.find((a) => a.guard_code === READY_TO_FILE_GUARD)
    : undefined;
  const runnable = transitions.filter((a) => a !== blocked);
  const reviewFirst = !!blocked && toReview > 0;
  const primary = reviewFirst ? null : runnable[0];
  const menuTransitions = reviewFirst ? runnable : runnable.slice(1);

  const problems = completeness?.ready_to_file_problems ?? [];
  const showReasons = notReady && transitions.length > 0 && problems.length > 0;
  const reasonId = `ready-reason-${detail.id}`;

  const runEvaluation = () =>
    evaluate.mutate(undefined, {
      onSuccess: (result) =>
        toast.success({
          title: "Reglas del banco evaluadas",
          message: result.eligible ? "La solicitud es elegible." : "La solicitud no es elegible.",
        }),
    });

  const items: MenuProps["items"] = [
    ...menuTransitions.map((action) => ({ key: `t:${action.code}`, label: action.label })),
    ...(permissions.has("applications.update") && detail.bank_product && !closed
      ? [{ key: "evaluate", label: "Evaluar reglas del banco" }]
      : []),
    ...(permissions.has("applications.assign") && permissions.has("users.read") && !closed
      ? [{ key: "reassign", label: "Reasignar asesor" }]
      : []),
    ...(canWithdraw
      ? [
          { type: "divider" as const },
          { key: "withdraw", label: "Registrar desistimiento", danger: true },
        ]
      : []),
  ];

  const onMenu: MenuProps["onClick"] = ({ key }) => {
    if (key === "evaluate") runEvaluation();
    else if (key === "reassign") setDialog({ kind: "reassign" });
    else if (key === "withdraw") setDialog({ kind: "withdraw" });
    else {
      const action = menuTransitions.find((a) => `t:${a.code}` === key);
      if (action) setDialog({ kind: "transition", action });
    }
  };

  return (
    <div className="grid w-full justify-items-stretch gap-1.5 min-[861px]:w-auto min-[861px]:justify-items-end">
      <div className="flex flex-wrap items-center gap-2 max-[860px]:[&>*]:flex-[1_1_auto]">
        {permissions.has("buyer_access.create") && !closed && (
          <Button onClick={() => setDialog({ kind: "link" })}>Enviar enlace al comprador</Button>
        )}
        {blocked && (
          <Button disabled aria-describedby={showReasons ? reasonId : undefined}>
            {blocked.label}
          </Button>
        )}
        {reviewFirst && (
          <Button type="primary" onClick={onReview}>
            {toReview === 1 ? "Revisar 1 documento" : `Revisar ${toReview} documentos`}
          </Button>
        )}
        {primary && (
          <Button type="primary" onClick={() => setDialog({ kind: "transition", action: primary })}>
            {primary.label}
          </Button>
        )}
        {items.length > 0 && (
          <Dropdown trigger={["click"]} menu={{ items, onClick: onMenu }} placement="bottomRight">
            <Button
              aria-label="Más acciones"
              icon={<MoreIcon />}
              loading={evaluate.isPending}
              className="max-[860px]:flex-none!"
            />
          </Dropdown>
        )}
      </div>
      {showReasons && (
        <div id={reasonId} className="text-text-secondary m-0 max-w-[560px] text-xs">
          <span>Para marcarla lista para radicar: </span>
          {problems.slice(0, MAX_REASONS).map((p, i) => (
            <span key={`${p.code}-${i}`}>{p.message} </span>
          ))}
          {problems.length > MAX_REASONS && (
            <span>
              {problems.length - MAX_REASONS === 1
                ? "Y 1 motivo más."
                : `Y ${problems.length - MAX_REASONS} motivos más.`}
            </span>
          )}
        </div>
      )}

      <TransitionModal
        applicationId={detail.id}
        open={dialog?.kind === "transition"}
        action={dialog?.kind === "transition" ? dialog.action : null}
        version={version}
        onClose={() => setDialog(null)}
      />
      <WithdrawModal
        applicationId={detail.id}
        open={dialog?.kind === "withdraw"}
        version={version}
        onClose={() => setDialog(null)}
      />
      <ReassignModal
        applicationId={detail.id}
        open={dialog?.kind === "reassign"}
        currentAdvisorId={detail.assigned_advisor.id}
        onClose={() => setDialog(null)}
      />
      <BuyerLinkModal
        applicationId={detail.id}
        open={dialog?.kind === "link"}
        onClose={() => setDialog(null)}
      />
    </div>
  );
}

/** "Sofía Herrera y Daniel Mejía · Vivienda nueva · Torres del Parque". */
export function WorkspaceSubtitle({
  detail,
  participants,
  property,
}: {
  detail: ApplicationDetail;
  participants: Participant[] | undefined;
  property: Property | null | undefined;
}) {
  const others = (participants ?? []).filter((p) => p.client.id !== detail.applicant.id);
  const names = others.map((p) => p.client.full_name);
  const project = property?.project?.name;
  return (
    <p className="text-text-secondary mt-1 mb-0">
      <b className="text-text-primary font-medium">{detail.applicant.full_name}</b>
      {names.length > 0 && <> y {names.join(", ")}</>}
      {detail.purpose && <> · {detail.purpose.label}</>}
      {project && <> · {project}</>}
    </p>
  );
}

function Kpi({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-secondary text-xs font-medium">{label}</dt>
      <dd className="m-0 mt-0.5 text-lg leading-snug font-semibold tabular-nums">
        {value}
        {note && <small className="text-text-tertiary block text-xs font-normal">{note}</small>}
      </dd>
    </div>
  );
}

const DASH = <span className="text-text-tertiary">—</span>;

/** Franja de datos clave: monto, valor, financiación, banco, plazo y origen. */
export function KeyFacts({
  detail,
  property,
  financing,
}: {
  detail: ApplicationDetail;
  property: Property | null | undefined;
  financing: Financing | null | undefined;
}) {
  const amount = detail.requested_amount_cop;
  const value = property?.estimated_value_cop;
  const ratio = amount !== null && amount !== undefined && value ? (amount / value) * 100 : null;
  const bank = detail.bank_product;
  const term = financing?.term_months;

  return (
    <dl className="border-border-default m-0 grid grid-cols-2 gap-4 border-t pt-4 min-[861px]:grid-cols-3 min-[1181px]:grid-cols-6">
      <Kpi label="Monto solicitado" value={<Money value={amount} />} />
      <Kpi label="Valor del inmueble" value={<Money value={value} />} />
      <Kpi
        label="Financiación"
        value={ratio === null ? DASH : formatPercentDecimal(ratio)}
        note={ratio === null ? undefined : "del valor"}
      />
      <Kpi
        label="Banco"
        value={bank ? bankLabel(bank.bank) : DASH}
        note={bank?.product_type.label}
      />
      <Kpi
        label="Plazo"
        value={term ? term : DASH}
        note={term ? (term === 1 ? "mes" : "meses") : undefined}
      />
      <Kpi label="Origen" value={detail.origin?.label ?? DASH} />
    </dl>
  );
}

export function WorkspaceTitle({ detail }: { detail: ApplicationDetail }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <h1 className="m-0 font-mono text-3xl font-medium">{detail.code}</h1>
      <StatusBadge kind="application" code={detail.status} label={detail.status_label} />
    </div>
  );
}
