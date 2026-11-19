"use client";

import { Button } from "antd";
import type { ReactNode } from "react";

import { Card, DataList, Datum } from "@/components/ui/card";
import { CompletenessBar, CompletenessTotal } from "@/components/ui/completeness-bar";
import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { TONE_CLASS, ToneBadge } from "@/components/ui/status-badge";
import { toneFor } from "@design/status-tones";
import { bankLabel } from "@/features/applications/queries";
import { HistoryEntry } from "@/features/applications/status-history";
import type {
  ApplicationDetail,
  BankRuleEvaluation,
  BuyerAccessLink,
  Completeness,
  ConsentRecord,
  DocumentSlot,
  FinancialProfile,
  Financing,
  Participant,
  Property,
  StatusHistoryEntry,
} from "@/features/applications/workspace-queries";
import { formatDateTime } from "@/lib/format";

// ---------- piezas comunes ----------

export function Muted({ children }: { children: ReactNode }) {
  return <p className="text-text-tertiary m-0 text-sm">{children}</p>;
}

/** Filas `[etiqueta, valor]` en la lista de datos en línea de la librería (mockup `.dl`). */
function DefinitionList({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <DataList layout="inline">
      {rows.map(([label, value]) => (
        <Datum key={label} label={label}>
          {value}
        </Datum>
      ))}
    </DataList>
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
    // Como el mockup: el total en el encabezado y datos y documentos lado a lado.
    <Card
      title="Completitud del expediente"
      action={<CompletenessTotal percentage={completeness.percentage} />}
    >
      <CompletenessBar
        percentage={completeness.percentage}
        dataPercentage={completeness.data_percentage}
        documentsPercentage={completeness.documents_percentage}
        documentsCompleted={documents.completed_total}
        documentsRequired={documents.required_total}
        layout="split"
        showTotal={false}
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
      action={
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
      <span>
        {rule.message}
        <small className="text-text-tertiary block text-xs">{rule.outcome_label}</small>
      </span>
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
      action={
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

/** Botón de texto a la derecha del título de una tarjeta ("Editar", "Agregar"). */
function CardAction({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button type="link" size="small" onClick={onClick}>
      {label}
    </Button>
  );
}

export function ParticipantsCard({
  participants,
  profiles,
  onAdd,
  onOpen,
}: {
  participants: Participant[];
  profiles: Map<string, FinancialProfile>;
  /** Con `applications.update`: agregar un participante. */
  onAdd?: () => void;
  /** Con `applications.update`: abrir el panel de edición del participante. */
  onOpen?: (participant: Participant) => void;
}) {
  const all = participants.map((p) => profiles.get(p.id)).filter((p): p is FinancialProfile => !!p);
  return (
    <Card
      title="Participantes"
      action={onAdd ? <CardAction label="Agregar participante" onClick={onAdd} /> : undefined}
    >
      <ul className="m-0 grid list-none gap-3 p-0">
        {participants.map((participant) => {
          const profile = profiles.get(participant.id);
          const facts = [
            participant.role_label,
            ...(profile
              ? [
                  profile.employment_profile.label,
                  profile.data_confirmed_at ? "Perfil confirmado" : "Perfil sin confirmar",
                ]
              : ["Sin perfil financiero"]),
          ];
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
              {onOpen && (
                <Button
                  size="small"
                  className={profile ? "" : "ml-auto"}
                  onClick={() => onOpen(participant)}
                  aria-label={`Editar a ${participant.client.full_name}`}
                >
                  Editar
                </Button>
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

export function PropertyCard({
  property,
  onEdit,
}: {
  property: Property | null;
  /** Con `applications.update`: editar (o registrar) el inmueble. */
  onEdit?: () => void;
}) {
  return (
    <Card
      title="Inmueble"
      action={
        onEdit ? (
          <CardAction label={property ? "Editar" : "Registrar"} onClick={onEdit} />
        ) : undefined
      }
    >
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

// ---------- financiación ----------

export function FinancingCard({
  financing,
  onEdit,
}: {
  financing: Financing | null;
  /** Con `applications.update`: editar (o registrar) la financiación. */
  onEdit?: () => void;
}) {
  const rows: [string, ReactNode][] = financing
    ? [
        ["Modalidad", financing.financing_mode.label],
        [
          "Producto",
          financing.bank_product
            ? `${bankLabel(financing.bank_product.bank)} · ${financing.bank_product.name}`
            : DASH,
        ],
        ["Monto solicitado", <Money key="r" value={financing.requested_amount_cop} />],
        ["Plazo", financing.term_months ? `${financing.term_months} meses` : DASH],
        ["Recursos propios", <Money key="o" value={financing.own_resources_cop} />],
        [
          "Cesantías",
          financing.uses_severance_funds ? (
            <Money key="s" value={financing.severance_funds_cop} />
          ) : (
            "No usa"
          ),
        ],
        ...(financing.external_approved_amount_cop !== null
          ? ([
              [
                "Aprobado por otra entidad",
                <Money key="e" value={financing.external_approved_amount_cop} />,
              ],
            ] as [string, ReactNode][])
          : []),
      ]
    : [];
  return (
    <Card
      title="Financiación"
      action={
        onEdit ? (
          <CardAction label={financing ? "Editar" : "Registrar"} onClick={onEdit} />
        ) : undefined
      }
    >
      {financing ? (
        <DefinitionList rows={rows} />
      ) : (
        <Muted>Todavía no se registra la financiación.</Muted>
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
  onSeeAll,
}: {
  entries: StatusHistoryEntry[];
  onSeeAll: () => void;
}) {
  return (
    <Card
      title="Últimos cambios de estado"
      action={
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
            <HistoryEntry key={entry.id} entry={entry} last={i === entries.length - 1} />
          ))}
        </ul>
      )}
    </Card>
  );
}
