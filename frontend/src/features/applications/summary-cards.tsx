"use client";

import { Button } from "antd";
import type { ReactNode } from "react";

import { CompletenessBar } from "@/components/ui/completeness-bar";
import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { TONE_CLASS } from "@/components/ui/status-badge";
import { toneFor, type Tone } from "@design/status-tones";
import { bankLabel } from "@/features/applications/queries";
import { HistoryEntry, type StatusLabels } from "@/features/applications/status-history";
import type {
  ApplicationDetail,
  BankRuleEvaluation,
  BuyerAccessLink,
  Completeness,
  ConsentRecord,
  DocumentSlot,
  FinancialProfile,
  Participant,
  Property,
  StatusHistoryEntry,
} from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";

// ---------- piezas comunes ----------

export function Card({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className="bg-bg-surface border-border-default rounded-lg border">
      <div className="flex items-center gap-2 px-5 pt-4">
        <h2 className="m-0 text-lg leading-snug font-semibold">{title}</h2>
        <div className="flex-1" />
        {aside}
      </div>
      <div className="px-5 pt-4 pb-5">{children}</div>
    </article>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className="text-text-tertiary m-0 text-sm">{children}</p>;
}

/** Lista de definición del mockup (`.dl`): etiqueta a la izquierda, valor a la derecha. */
export function DefinitionList({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="m-0 grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-x-4 gap-y-2 text-sm min-[861px]:grid-cols-[minmax(140px,220px)_1fr]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-text-tertiary">{label}</dt>
          <dd className="m-0 font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const DASH = <span className="text-text-tertiary">—</span>;

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={16} height={16} aria-hidden="true">
      <path d="M10 1a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-1.2 13L4.5 9.7l1.4-1.4 2.9 2.9 5.3-5.3 1.4 1.4-6.7 6.7Z" />
    </svg>
  );
}

function WarnIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" width={16} height={16} aria-hidden="true">
      <path d="M10 2 1 18h18L10 2Zm-1 6h2v5H9V8Zm0 6h2v2H9v-2Z" />
    </svg>
  );
}

/** Línea con ícono de cumplido o pendiente; el estado también va en texto oculto. */
function Check({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <span className={`mt-0.5 flex-none ${ok ? "text-tone-success-fg" : "text-tone-warning-fg"}`}>
        {ok ? <CheckIcon /> : <WarnIcon />}
      </span>
      <span>
        <span className="sr-only">{ok ? "Cumplido: " : "Pendiente: "}</span>
        {children}
      </span>
    </li>
  );
}

function ToneBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      data-tone={tone}
      className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-xs font-medium whitespace-nowrap ${TONE_CLASS[tone]}`}
    >
      <span aria-hidden="true" className="size-1.5 flex-none rounded-full bg-current" />
      {children}
    </span>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts.slice(0, 1);
  return letters.map((p) => p?.charAt(0).toUpperCase() ?? "").join("");
}

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="bg-bg-muted text-text-secondary grid size-8 flex-none place-items-center rounded-full text-xs font-semibold"
    >
      {initials(name)}
    </span>
  );
}

// ---------- completitud ----------

/** Total, datos y documentos, y la lista de lo que falta con los mensajes de la API. */
export function CompletenessCard({ completeness }: { completeness: Completeness }) {
  const { documents } = completeness;
  return (
    <Card title="Completitud del expediente">
      <CompletenessBar
        percentage={completeness.percentage}
        dataPercentage={completeness.data_percentage}
        documentsPercentage={completeness.documents_percentage}
        documentsCompleted={documents.completed_total}
        documentsRequired={documents.required_total}
      />
      <ul className="m-0 mt-4 grid list-none gap-1.5 p-0 text-sm">
        {completeness.items.map((item, i) => (
          <Check key={`${item.code}-${item.participant_id ?? i}`} ok={item.complete}>
            {item.message}
          </Check>
        ))}
        {documents.message && <Check ok={documents.verified}>{documents.message}</Check>}
      </ul>
    </Card>
  );
}

// ---------- por revisar ----------

export function ToReviewCard({
  slots,
  total,
  onReview,
  onSeeAll,
}: {
  slots: DocumentSlot[];
  total: number;
  onReview: (slot: DocumentSlot) => void;
  onSeeAll: () => void;
}) {
  return (
    <Card
      title="Por revisar"
      aside={
        <Button type="link" size="small" onClick={onSeeAll}>
          Ver todos los documentos
        </Button>
      }
    >
      {total === 0 ? (
        <Muted>No hay documentos cargados esperando revisión.</Muted>
      ) : (
        <ul className="m-0 grid list-none gap-2 p-0">
          {slots.map((slot) => (
            <li
              key={slot.id}
              className="border-border-default grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg border px-4 py-2.5"
            >
              <div className="min-w-0">
                <div className="font-medium">{slot.label}</div>
                <div className="text-text-tertiary truncate text-xs">
                  {[slot.participant?.full_name, slot.current_file?.client_filename]
                    .filter(Boolean)
                    .join(" · ")}
                  {slot.current_file && (
                    <>
                      {" · "}
                      <RelativeTime value={slot.current_file.created_at} />
                    </>
                  )}
                </div>
              </div>
              <Button size="small" onClick={() => onReview(slot)}>
                Revisar<span className="sr-only"> {slot.label}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------- evaluación del banco ----------

function RuleRow({ rule }: { rule: BankRuleEvaluation["blocking"][number] }) {
  const tone = toneFor("ruleOutcome", rule.outcome);
  return (
    <li className="bg-bg-subtle flex items-start gap-3 rounded-md px-3 py-2.5 text-sm">
      <span className={`mt-0.5 flex-none ${TONE_CLASS[tone].split(" ")[0]}`}>
        <WarnIcon />
      </span>
      <span>{rule.message}</span>
    </li>
  );
}

export function EvaluationCard({
  evaluation,
  detail,
}: {
  evaluation: BankRuleEvaluation | null;
  detail: ApplicationDetail;
}) {
  const bank = detail.bank_product;
  if (!evaluation) {
    return (
      <Card title="Evaluación del banco">
        <Muted>
          {bank
            ? "Todavía no se evalúan las reglas del banco para esta solicitud."
            : "La solicitud todavía no tiene banco elegido."}
        </Muted>
      </Card>
    );
  }
  return (
    <Card
      title="Evaluación del banco"
      aside={
        <ToneBadge tone={evaluation.eligible ? "success" : "danger"}>
          {evaluation.eligible ? "Elegible" : "No elegible"}
        </ToneBadge>
      }
    >
      <div>
        {bank && (
          <b className="font-medium">
            {bankLabel(bank.bank)} · {bank.product_type.label}
          </b>
        )}
        <div className="text-text-tertiary text-sm">
          Evaluada <RelativeTime value={evaluation.evaluated_at} /> ·{" "}
          {evaluation.is_current
            ? "vigente para la versión actual"
            : "vencida: la solicitud cambió después"}
        </div>
      </div>
      {evaluation.blocking.length === 0 && evaluation.warnings.length === 0 ? (
        <p className="text-text-secondary m-0 mt-4 text-sm">
          Cumple todas las reglas del producto.
        </p>
      ) : (
        <div className="mt-4 grid gap-3">
          {evaluation.blocking.length > 0 && (
            <section aria-label="Reglas que bloquean">
              <h3 className="text-text-secondary m-0 mb-2 text-xs font-medium">Bloquean</h3>
              <ul className="m-0 grid list-none gap-2 p-0">
                {evaluation.blocking.map((rule, i) => (
                  <RuleRow key={`${rule.rule_code}-${i}`} rule={rule} />
                ))}
              </ul>
            </section>
          )}
          {evaluation.warnings.length > 0 && (
            <section aria-label="Avisos">
              <h3 className="text-text-secondary m-0 mb-2 text-xs font-medium">
                Avisos (no bloquean)
              </h3>
              <ul className="m-0 grid list-none gap-2 p-0">
                {evaluation.warnings.map((rule, i) => (
                  <RuleRow key={`${rule.rule_code}-${i}`} rule={rule} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Card>
  );
}

// ---------- participantes ----------

function sum(values: number[]): number {
  return values.reduce((a, b) => a + b, 0);
}

export function ParticipantsCard({
  participants,
  profiles,
}: {
  participants: Participant[];
  profiles: Map<string, FinancialProfile>;
}) {
  const all = participants.map((p) => profiles.get(p.id)).filter((p): p is FinancialProfile => !!p);
  return (
    <Card title="Participantes">
      <ul className="m-0 grid list-none gap-3 p-0">
        {participants.map((participant) => {
          const profile = profiles.get(participant.id);
          const facts = profile
            ? [
                profile.employment_profile.label,
                profile.data_confirmed_at ? "Perfil confirmado" : "Perfil sin confirmar",
              ]
            : ["Sin perfil financiero"];
          return (
            <li key={participant.id} className="flex items-center gap-3">
              <Avatar name={participant.client.full_name} />
              <div className="min-w-0">
                <b className="block font-medium">{participant.client.full_name}</b>
                <span className="text-text-tertiary text-xs">{facts.join(" · ")}</span>
              </div>
              {profile && (
                <div className="ml-auto text-right text-sm">
                  <b className="block">
                    <Money value={profile.monthly_income_cop} />
                  </b>
                  <span className="text-text-tertiary text-xs">ingreso mensual</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="border-border-default mt-3 border-t pt-3">
        <DefinitionList
          rows={[
            [
              "Ingreso del hogar",
              all.length ? <Money value={sum(all.map((p) => p.monthly_income_cop))} /> : DASH,
            ],
            [
              "Gastos del hogar",
              all.length ? <Money value={sum(all.map((p) => p.monthly_expenses_cop))} /> : DASH,
            ],
          ]}
        />
      </div>
    </Card>
  );
}

// ---------- inmueble ----------

export function PropertyCard({ property }: { property: Property | null }) {
  return (
    <Card title="Inmueble">
      {property ? (
        <DefinitionList
          rows={[
            ["Proyecto", property.project?.name ?? DASH],
            ["Unidad", property.unit_reference || DASH],
            ["Ciudad", property.city.label],
            ["Condición", `${property.condition.label} · ${property.property_type.label}`],
            ["Valor comercial", <Money key="v" value={property.estimated_value_cop} />],
          ]}
        />
      ) : (
        <Muted>Todavía no se registra el inmueble.</Muted>
      )}
    </Card>
  );
}

// ---------- acceso del comprador ----------

/** Consentimientos vigentes: el registro más reciente de cada definición es una aceptación. */
export function acceptedConsents(records: ConsentRecord[]): ConsentRecord[] {
  const latest = new Map<string, ConsentRecord>();
  for (const record of records) {
    const current = latest.get(record.consent_definition.id);
    if (!current || record.created_at > current.created_at) {
      latest.set(record.consent_definition.id, record);
    }
  }
  return [...latest.values()].filter((r) => r.action === "ACCEPTED");
}

export function BuyerAccessCard({
  link,
  consents,
  lastActivityAt,
}: {
  /** `undefined`: sin permiso para ver los enlaces. */
  link: BuyerAccessLink | null | undefined;
  /** `undefined`: sin permiso para ver los consentimientos. */
  consents: ConsentRecord[] | undefined;
  lastActivityAt: string | null;
}) {
  const rows: [string, ReactNode][] = [];
  if (link !== undefined) {
    if (link === null) {
      rows.push([
        "Enlace",
        <span key="l" className="text-text-tertiary">
          Todavía no se envía
        </span>,
      ]);
    } else {
      rows.push(["Enlace enviado", formatDateTime(link.created_at)]);
      if (link.consumed_at) rows.push(["Usado", formatDateTime(link.consumed_at)]);
      else if (link.revoked_at) rows.push(["Revocado", formatDateTime(link.revoked_at)]);
      else rows.push(["Vence", formatDateTime(link.expires_at)]);
      const session = link.session;
      rows.push([
        "Sesión",
        session?.is_active ? (
          `Activa hasta ${formatDateTime(session.expires_at) ?? ""}`
        ) : (
          <span key="s" className="text-text-tertiary">
            Sin sesión activa
          </span>
        ),
      ]);
    }
  }
  if (consents !== undefined) {
    const accepted = acceptedConsents(consents);
    rows.push([
      "Consentimientos",
      accepted.length ? (
        <ul key="c" className="m-0 list-none p-0">
          {accepted.map((r) => (
            <li key={r.id}>{r.consent_definition.title}</li>
          ))}
        </ul>
      ) : (
        <span key="c" className="text-text-tertiary">
          Ninguno aceptado
        </span>
      ),
    ]);
  }
  rows.push([
    "Última actividad",
    lastActivityAt ? (
      <RelativeTime key="a" value={lastActivityAt} />
    ) : (
      <span key="a" className="text-text-tertiary">
        El comprador aún no entra
      </span>
    ),
  ]);
  return (
    <Card title="Acceso del comprador">
      <DefinitionList rows={rows} />
    </Card>
  );
}

// ---------- últimos cambios de estado ----------

export function RecentChangesCard({
  entries,
  labels,
  onSeeAll,
}: {
  entries: StatusHistoryEntry[];
  labels: StatusLabels;
  onSeeAll: () => void;
}) {
  return (
    <Card
      title="Últimos cambios de estado"
      aside={
        <Button type="link" size="small" onClick={onSeeAll}>
          Ver historial
        </Button>
      }
    >
      {entries.length === 0 ? (
        <Muted>Sin cambios de estado.</Muted>
      ) : (
        <ul className="m-0 grid list-none gap-4 p-0">
          {entries.map((entry, i) => (
            <HistoryEntry
              key={entry.id}
              entry={entry}
              labels={labels}
              last={i === entries.length - 1}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}
