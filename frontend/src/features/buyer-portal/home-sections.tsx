"use client";

import { toneFor } from "@design/status-tones";
import { Button } from "antd";
import Link from "next/link";
import type { ReactNode } from "react";

import { Money } from "@/components/ui/money";
import { TONE_CLASS } from "@/components/ui/status-badge";
import { Stepper } from "@/components/ui/stepper";
import { ExpiryNotice } from "@/features/buyer-portal/expiry";
import {
  bankName,
  formatTerm,
  whatsappUrl,
  workloadText,
} from "@/features/buyer-portal/home-format";
import { PORTAL_DOCUMENTS, initials } from "@/features/buyer-portal/portal-shell";
import type { BuyerApplicationDetail, BuyerDocumentSlot } from "@/features/buyer-portal/queries";
import { formatDateTime } from "@/lib/format";

/** Rutas de las secciones de la solicitud (Parte 3 de la spec). */
export const PORTAL_ROUTES = {
  profile: "/portal/datos",
  income: "/portal/ingresos",
  property: "/portal/inmueble",
  financing: "/portal/financiacion",
  documents: PORTAL_DOCUMENTS,
} as const;

/** Máximo de pendientes en el inicio; el resto, en "Ver todos mis documentos". */
export const TODO_LIMIT = 3;

const svg = { viewBox: "0 0 20 20", fill: "currentColor", "aria-hidden": true } as const;
const ICONS = {
  check: <path d="M8 13.2 4.8 10l-1.4 1.4L8 16l9-9-1.4-1.4L8 13.2Z" />,
  alert: <path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1 4h2v6H9V5Zm0 8h2v2H9v-2Z" />,
  plus: <path d="M9 3h2v6h6v2h-6v6H9v-6H3V9h6V3Z" />,
  person: <path d="M10 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0H3Z" />,
  money: <path d="M3 5h14v10H3V5Zm2 2v6h10V7H5Zm5 1a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z" />,
  people: (
    <path d="M7 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm6 1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM1 16a6 6 0 0 1 12 0H1Zm13 0a7 7 0 0 0-2-5 5 5 0 0 1 7 5h-5Z" />
  ),
  house: <path d="M10 2 2 8v10h5v-6h6v6h5V8l-8-6Z" />,
  bank: <path d="M10 2 2 6v2h16V6l-8-4ZM4 9v6H3v2h14v-2h-1V9h-2v6h-2V9H9v6H7V9H4Z" />,
  document: <path d="M5 2h7l4 4v12H5V2Zm2 7v2h7V9H7Zm0 4v2h7v-2H7Z" />,
  chevron: <path d="m7.4 4 6 6-6 6L6 14.6l4.6-4.6L6 5.4 7.4 4Z" />,
  mail: <path d="M2 4h16v12H2V4Zm2 2v.5l6 4 6-4V6H4Zm12 2.9-6 4-6-4V14h12V8.9Z" />,
  chat: (
    <path d="M10 2a8 8 0 0 0-6.9 12L2 18l4.1-1.1A8 8 0 1 0 10 2Zm0 2a6 6 0 1 1-3.1 11.1l-.3-.2-2 .6.6-1.9-.2-.3A6 6 0 0 1 10 4Z" />
  ),
  bell: (
    <path d="M10 2a5 5 0 0 0-5 5v3l-2 3v1h14v-1l-2-3V7a5 5 0 0 0-5-5Zm-2 14a2 2 0 0 0 4 0H8Z" />
  ),
};

function Icon({ name, size = 18 }: { name: keyof typeof ICONS; size?: number }) {
  return (
    <svg {...svg} width={size} height={size} className="flex-none">
      {ICONS[name]}
    </svg>
  );
}

function SectionTitle({
  id,
  children,
  count,
}: {
  id: string;
  children: ReactNode;
  count?: number;
}) {
  return (
    <div className="mb-3 flex items-baseline gap-2">
      <h2 id={id} className="m-0 text-xl font-semibold">
        {children}
      </h2>
      {count !== undefined && <span className="text-text-tertiary tabular-nums">{count}</span>}
    </div>
  );
}

// ---------- estado ----------

export function StatusCard({
  detail,
  slots,
}: {
  detail: BuyerApplicationDetail;
  slots: BuyerDocumentSlot[];
}) {
  const { progress } = detail;
  const total = progress.documents_required_total;
  const done = progress.documents_completed_total;
  const mine = slots.filter((s) => s.needs_action).length;
  const inReview = slots.filter((s) => s.public_status === "IN_REVIEW").length;
  const workload = workloadText(mine, inReview);
  const ratio = total > 0 ? Math.min(1, done / total) : 0;

  return (
    <section
      aria-labelledby="status-title"
      className="bg-bg-sidebar text-text-on-sidebar rounded-xl px-4 py-5"
    >
      <h2
        id="status-title"
        className="text-text-on-sidebar-strong m-0 mb-1 text-xl leading-snug font-semibold"
      >
        {detail.public_status_label}
      </h2>
      {detail.next_action && <p className="text-md m-0">{detail.next_action}</p>}

      {total > 0 && (
        <div className="mt-4 grid gap-1.5">
          <div className="text-md flex">
            <span>Documentos listos</span>
            <span className="flex-1" />
            <b className="text-text-on-sidebar-strong tabular-nums">
              {done} de {total}
            </b>
          </div>
          <div
            role="img"
            aria-label={`${done} de ${total} documentos listos`}
            className="bg-sidebar-item-active h-2 overflow-hidden rounded-full"
          >
            <i
              className="bg-text-on-sidebar-strong block h-full w-full origin-left rounded-full"
              style={{ transform: `scaleX(${ratio})` }}
            />
          </div>
          {workload && <small className="text-sm">{workload}</small>}
        </div>
      )}

      {detail.stages.length > 0 && (
        <div className="mt-5">
          <Stepper stages={detail.stages} ariaLabel="Etapas" orientation="vertical" />
        </div>
      )}

      <ExpiryNotice className="border-sidebar-divider mt-4 border-t pt-3" />
    </section>
  );
}

// ---------- respuesta del banco ----------

export function BankUpdateCard({
  update,
}: {
  update: NonNullable<BuyerApplicationDetail["latest_bank_update"]>;
}) {
  return (
    <section
      aria-labelledby="bank-title"
      className="bg-bg-surface border-border-default grid gap-2 rounded-xl border px-4 py-5"
    >
      <p className="text-text-tertiary m-0 flex items-center gap-2 text-sm">
        <Icon name="bell" size={16} />
        Respuesta del banco · {formatDateTime(update.received_at)}
      </p>
      <h2 id="bank-title" className="m-0 text-xl font-semibold">
        {update.response_type_label}
      </h2>
      {update.public_message && (
        <p className="text-text-secondary text-md m-0 whitespace-pre-line">
          {update.public_message}
        </p>
      )}
    </section>
  );
}

// ---------- lo que necesitamos de ti ----------

function TodoItem({
  slot,
  primary,
  onUpload,
}: {
  slot: BuyerDocumentSlot;
  primary: boolean;
  onUpload: (slot: BuyerDocumentSlot) => void;
}) {
  const tone = toneFor("documentSlot", slot.status);
  const rejection = slot.rejection;
  const message = [rejection?.reason?.label, rejection?.buyer_comment].filter(Boolean).join(": ");
  return (
    <article
      className={`bg-bg-surface grid gap-3 rounded-xl border p-4 ${
        tone === "danger" ? "border-tone-danger-border" : "border-border-default"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`grid size-10 flex-none place-items-center rounded-lg ${TONE_CLASS[tone]}`}
        >
          <Icon name={tone === "danger" ? "alert" : "plus"} size={20} />
        </span>
        <div className="min-w-0">
          <b className="text-md block font-semibold">{slot.label}</b>
          <span className="text-text-tertiary block text-sm">
            {slot.public_status_label}
            {slot.participant &&
              ` · ${slot.participant.full_name} · ${slot.participant.role_label}`}
          </span>
        </div>
      </div>
      {message && (
        <p className={`m-0 rounded-md px-3 py-2 text-sm ${TONE_CLASS.danger}`}>{message}</p>
      )}
      <Button
        type={primary ? "primary" : "default"}
        size="large"
        block
        onClick={() => onUpload(slot)}
      >
        {slot.current_file ? "Reemplazar documento" : "Subir documento"}
      </Button>
    </article>
  );
}

export function TodoSection({
  slots,
  onUpload,
}: {
  slots: BuyerDocumentSlot[];
  onUpload: (slot: BuyerDocumentSlot) => void;
}) {
  const pending = slots.filter((s) => s.needs_action);
  return (
    <section aria-labelledby="todo-title">
      <SectionTitle id="todo-title" count={pending.length}>
        Lo que necesitamos de ti
      </SectionTitle>
      <div className="grid gap-3">
        {pending.length === 0 && (
          <p className="text-text-secondary text-md m-0">
            Por ahora no necesitamos ningún documento de ti.
          </p>
        )}
        {pending.slice(0, TODO_LIMIT).map((slot, index) => (
          <TodoItem key={slot.id} slot={slot} primary={index === 0} onUpload={onUpload} />
        ))}
        <Link
          href={PORTAL_ROUTES.documents}
          className="text-text-link text-md inline-flex min-h-11 items-center justify-self-center font-medium"
        >
          Ver todos mis documentos
        </Link>
      </div>
    </section>
  );
}

// ---------- tu solicitud ----------

function SectionRow({
  href,
  icon,
  title,
  subtitle,
  extra,
}: {
  href: string;
  icon: keyof typeof ICONS;
  title: string;
  subtitle: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="border-border-default hover:bg-bg-subtle flex min-h-16 items-center gap-3 border-b p-4 text-inherit no-underline last:border-b-0"
    >
      <span className="bg-bg-muted text-text-secondary grid size-9 flex-none place-items-center rounded-md">
        <Icon name={icon} />
      </span>
      <span className="min-w-0">
        <b className="text-md block font-medium">{title}</b>
        <small className="text-text-tertiary block text-sm">{subtitle}</small>
      </span>
      <span className="text-text-tertiary ml-auto flex items-center gap-2">
        {extra}
        <Icon name="chevron" />
      </span>
    </Link>
  );
}

const NO_DATA = "Sin datos todavía";

export function ApplicationSection({
  detail,
  monthlyIncome,
  pendingDocuments,
}: {
  detail: BuyerApplicationDetail;
  /** `null` mientras carga o sin perfiles. */
  monthlyIncome: number | null;
  pendingDocuments: number;
}) {
  const { property, financing, progress } = detail;
  const [primary, ...others] = detail.participants;
  const missing = progress.items.filter((item) => !item.complete);

  const propertyText = property
    ? [property.project?.name ?? property.address, property.unit_reference]
        .filter(Boolean)
        .join(" · ") || NO_DATA
    : NO_DATA;

  let financingText: ReactNode = NO_DATA;
  if (financing) {
    const term = formatTerm(financing.term_months);
    financingText = (
      <>
        {financing.bank_product && `${bankName(financing.bank_product.bank)} · `}
        <Money value={financing.requested_amount_cop} />
        {term && ` a ${term}`}
      </>
    );
  }

  return (
    <section aria-labelledby="sections-title">
      <SectionTitle id="sections-title">Tu solicitud</SectionTitle>
      {missing.length > 0 && (
        <div className="mb-3">
          <p className="text-text-secondary m-0 mb-1 text-sm font-medium">Lo que falta</p>
          <ul className="text-text-secondary m-0 grid gap-1 pl-5 text-sm">
            {missing.map((item) => (
              <li key={`${item.code}-${item.participant_id ?? ""}`}>{item.message}</li>
            ))}
          </ul>
        </div>
      )}
      <nav
        aria-label="Secciones de tu solicitud"
        className="bg-bg-surface border-border-default overflow-hidden rounded-xl border"
      >
        <SectionRow
          href={PORTAL_ROUTES.profile}
          icon="person"
          title="Tus datos personales"
          subtitle={primary?.full_name ?? NO_DATA}
        />
        <SectionRow
          href={PORTAL_ROUTES.income}
          icon="money"
          title="Ingresos y gastos"
          subtitle={
            monthlyIncome === null ? (
              NO_DATA
            ) : (
              <>
                <Money value={monthlyIncome} /> al mes
              </>
            )
          }
        />
        {others.map((participant) => (
          <SectionRow
            key={participant.id}
            href={`${PORTAL_ROUTES.income}#participante-${participant.id}`}
            icon="people"
            title={participant.role_label}
            subtitle={participant.full_name}
          />
        ))}
        <SectionRow
          href={PORTAL_ROUTES.property}
          icon="house"
          title="El inmueble"
          subtitle={propertyText}
        />
        <SectionRow
          href={PORTAL_ROUTES.financing}
          icon="bank"
          title="Financiación"
          subtitle={financingText}
        />
        <SectionRow
          href={PORTAL_ROUTES.documents}
          icon="document"
          title="Documentos"
          subtitle={`${progress.documents_completed_total} de ${progress.documents_required_total} listos`}
          extra={
            pendingDocuments > 0 ? (
              <span
                className={`rounded-full border px-2 text-xs font-medium whitespace-nowrap ${TONE_CLASS.warning}`}
              >
                {pendingDocuments} {pendingDocuments === 1 ? "pendiente" : "pendientes"}
              </span>
            ) : undefined
          }
        />
      </nav>
    </section>
  );
}

// ---------- asesor ----------

export function AdvisorCard({
  advisor,
}: {
  advisor: NonNullable<BuyerApplicationDetail["advisor"]>;
}) {
  const whatsapp = whatsappUrl(advisor.phone);
  return (
    <section
      aria-labelledby="advisor-title"
      className="bg-bg-surface border-border-default rounded-xl border px-4 py-5"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="bg-accent-subtle text-tone-accent-fg text-md grid size-12 flex-none place-items-center rounded-full font-semibold"
        >
          {initials(advisor.full_name)}
        </span>
        <div>
          <b id="advisor-title" className="block">
            {advisor.full_name}
          </b>
          <span className="text-text-tertiary text-sm">Tu asesor de crédito</span>
        </div>
      </div>
      <div className={`mt-4 grid gap-2 ${whatsapp ? "grid-cols-2" : "grid-cols-1"}`}>
        {whatsapp && (
          <Button
            size="large"
            href={whatsapp}
            target="_blank"
            rel="noopener noreferrer"
            icon={<Icon name="chat" />}
          >
            WhatsApp
          </Button>
        )}
        <Button size="large" href={`mailto:${advisor.email}`} icon={<Icon name="mail" />}>
          Correo
        </Button>
      </div>
    </section>
  );
}
