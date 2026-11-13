"use client";

import { Tooltip } from "antd";

import { CompletenessBar } from "@/components/ui/completeness-bar";
import { StatusBadge } from "@/components/ui/status-badge";
import { bankLabel, type Application } from "@/features/applications/queries";
import { formatDate } from "@/lib/format";

// Celdas del listado, compartidas por la tabla (escritorio) y las tarjetas (móvil).

function WarningIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={14} height={14} aria-hidden="true">
      <path d="M10 2 1 18h18L10 2Zm-1 6h2v5H9V8Zm0 6h2v2H9v-2Z" />
    </svg>
  );
}

/** Ícono de aviso con tooltip; el texto también va oculto para lectores de pantalla. */
export function Flag({ text }: { text: string }) {
  return (
    <Tooltip title={text}>
      <span className="text-tone-warning-fg ml-1 inline-flex align-[-2px]" data-flag="">
        <WarningIcon />
        <span className="sr-only">{text}</span>
      </span>
    </Tooltip>
  );
}

function plural(n: number, one: string, many: string): string {
  return `+ ${n} ${n === 1 ? one : many}`;
}

/**
 * Participantes además del titular ("+ 1 co-solicitante"). La API solo da los conteos
 * (`participants_summary`); sin adicionales, `null`.
 */
export function participantsText(summary: Application["participants_summary"]): string | null {
  const parts = [
    summary.co_applicants > 0 && plural(summary.co_applicants, "co-solicitante", "co-solicitantes"),
    summary.solidary_debtors > 0 &&
      plural(summary.solidary_debtors, "deudor solidario", "deudores solidarios"),
  ].filter((p): p is string => Boolean(p));
  return parts.length ? parts.join(" · ") : null;
}

/** Texto del aviso de inactividad del comprador (`buyer_inactive`). */
export function inactivityText(lastActivityAt: string | null): string {
  const date = formatDate(lastActivityAt);
  return date ? `Sin actividad del comprador desde ${date}` : "El comprador aún no entra";
}

export const READY_TO_FILE_BLOCKED_TEXT = "Ya no cumple para radicar";

export function ApplicantCell({ application }: { application: Application }) {
  const extra = participantsText(application.participants_summary);
  return (
    <div className="min-w-0">
      <b className="block leading-[18px] font-medium">{application.applicant.full_name}</b>
      {extra && <span className="text-text-tertiary text-xs">{extra}</span>}
    </div>
  );
}

export function StatusCell({ application }: { application: Application }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap">
      <StatusBadge kind="application" code={application.status} label={application.status_label} />
      {application.buyer_inactive === true && (
        <Flag text={inactivityText(application.last_buyer_activity_at)} />
      )}
    </span>
  );
}

export function CompletenessCell({
  application,
  fill = false,
}: {
  application: Application;
  /** La barra ocupa el ancho disponible (tarjetas en móvil). */
  fill?: boolean;
}) {
  const pct = application.completeness_pct;
  return (
    <span className={`inline-flex items-center ${fill ? "flex-1" : ""}`}>
      {pct === null || pct === undefined ? (
        <span className="text-text-tertiary">—</span>
      ) : (
        <CompletenessBar percentage={pct} variant="mini" className={fill ? "w-auto! flex-1" : ""} />
      )}
      {application.ready_to_file_blocked === true && <Flag text={READY_TO_FILE_BLOCKED_TEXT} />}
    </span>
  );
}

export const NO_BANK_TEXT = "Sin banco";

/** Banco elegido: nombre corto, o `name`, o "Sin banco". */
export function bankText(application: Application): string | null {
  const bank = application.bank_product?.bank;
  return bank ? bankLabel(bank) : null;
}

export function BankCell({ application }: { application: Application }) {
  const bank = application.bank_product?.bank;
  if (!bank) return <span className="text-text-tertiary">{NO_BANK_TEXT}</span>;
  return (
    <span title={bank.name} className="block max-w-[150px] truncate">
      {bankLabel(bank)}
    </span>
  );
}

export function ProductTypeCell({ application }: { application: Application }) {
  const type = application.bank_product?.product_type.label;
  return (
    <div>
      {type ? (
        <span className="block leading-[18px]">{type}</span>
      ) : (
        <span className="text-text-tertiary block leading-[18px]">—</span>
      )}
      {application.purpose?.label && (
        <span className="text-text-tertiary text-xs">{application.purpose.label}</span>
      )}
    </div>
  );
}
