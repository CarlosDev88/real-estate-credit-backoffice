"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "antd";
import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { TONE_CLASS } from "@/components/ui/status-badge";
import { toneFor } from "@design/status-tones";
import { BarList } from "@/features/dashboard/bar-list";
import { BlockState, EmptyNote } from "@/features/dashboard/block-state";
import type { DashboardSummary } from "@/features/dashboard/queries";
import { formatCOP, formatInteger } from "@/lib/format";

// ---------- cifras ----------

interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Una línea debajo: de qué es la cifra ("en el periodo", "hoy"). */
  hint?: string;
  /** La tarjeta entera es un enlace (por ejemplo, a "Mi día" con un filtro). */
  href?: string;
}

/** Tarjeta de una cifra: etiqueta, número y para qué periodo. Candidata a la librería. */
export function StatTile({ label, value, hint, href }: StatTileProps) {
  const body = (
    <>
      <span className="text-text-secondary block text-xs font-medium">{label}</span>
      <span className="mt-1 block text-2xl leading-tight font-semibold tracking-tight tabular-nums">
        {value}
      </span>
      {hint && <span className="text-text-tertiary mt-0.5 block text-xs">{hint}</span>}
    </>
  );
  const box = "bg-bg-surface border-border-default block rounded-lg border px-4 py-3";
  if (!href) return <div className={box}>{body}</div>;
  return (
    <Link
      href={href}
      className={`${box} hover:border-border-strong hover:bg-brand-subtle focus-visible:outline-focus-ring text-inherit no-underline focus-visible:outline-2 focus-visible:outline-offset-2`}
    >
      {body}
    </Link>
  );
}

const count = (n: number) => formatInteger(n) || "0";
const money = (value: string) => formatCOP(Number(value)) ?? "—";

/** Rutas de "Mi día" con el filtro de tareas (`due` de `GET /tasks`). */
export const MY_DAY_OVERDUE = "/mi-dia?due=overdue";
export const MY_DAY_TODAY = "/mi-dia?due=today";

export function SummaryTiles({
  query,
  showTasks,
  linkTasks,
}: {
  query: UseQueryResult<DashboardSummary>;
  /** Las tareas son del asesor y del administrador (el broker siempre recibe 0). */
  showTasks: boolean;
  /** Las tarjetas de tareas enlazan a "Mi día" si el usuario puede abrirlo. */
  linkTasks: boolean;
}) {
  return (
    <section aria-label="Cifras del periodo">
      <BlockState
        query={query}
        errorTitle="No pudimos cargar las cifras."
        loadingLabel="Cargando cifras"
        loadingBlocks={[84]}
      >
        {(data) => (
          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3 min-[1100px]:grid-cols-4">
              <StatTile
                label="Clientes creados"
                value={count(data.clients_created)}
                hint="en el periodo"
              />
              <StatTile
                label="Solicitudes creadas"
                value={count(data.applications_created)}
                hint="en el periodo"
              />
              {showTasks && (
                <>
                  <StatTile
                    label="Tareas vencidas"
                    value={count(data.tasks.overdue)}
                    hint="pendientes de días anteriores"
                    href={linkTasks ? MY_DAY_OVERDUE : undefined}
                  />
                  <StatTile
                    label="Tareas para hoy"
                    value={count(data.tasks.due_today)}
                    hint="pendientes con fecha de hoy"
                    href={linkTasks ? MY_DAY_TODAY : undefined}
                  />
                </>
              )}
            </div>
            {data.amounts && (
              <div className="grid gap-3 min-[600px]:grid-cols-3">
                <StatTile
                  label="Monto solicitado"
                  value={money(data.amounts.requested_total)}
                  hint="de las solicitudes creadas en el periodo"
                />
                <StatTile
                  label="Monto aprobado"
                  value={money(data.amounts.approved_total)}
                  hint="última aprobación de cada solicitud"
                />
                <StatTile
                  label="Monto desembolsado"
                  value={money(data.amounts.disbursed_total)}
                  hint="último desembolso de cada solicitud"
                />
              </div>
            )}
          </div>
        )}
      </BlockState>
    </section>
  );
}

// ---------- foto por estado ----------

function ToneDot({ code }: { code: string }) {
  const tone = toneFor("application", code);
  return (
    <span
      aria-hidden="true"
      data-tone={tone}
      className={`size-2 flex-none rounded-full border-0 bg-current ${TONE_CLASS[tone].split(" ")[0]}`}
    />
  );
}

export function StatusSnapshot({ query }: { query: UseQueryResult<DashboardSummary> }) {
  const [showAll, setShowAll] = useState(false);
  const snapshot = query.data?.snapshot ?? [];
  const zeros = snapshot.filter((s) => s.count === 0).length;

  return (
    <Card
      title="Solicitudes por estado"
      action={
        zeros > 0 ? (
          <Button
            type="link"
            size="small"
            aria-pressed={showAll}
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll ? "Ocultar los que están en 0" : `Mostrar todos (${snapshot.length})`}
          </Button>
        ) : undefined
      }
    >
      <p className="text-text-tertiary m-0 mb-4 text-xs">Hoy, sin el filtro de fechas.</p>
      <BlockState
        query={query}
        errorTitle="No pudimos cargar las solicitudes por estado."
        loadingLabel="Cargando solicitudes por estado"
      >
        {(data) => {
          const rows = showAll ? data.snapshot : data.snapshot.filter((s) => s.count > 0);
          if (rows.length === 0) {
            return <EmptyNote>No hay solicitudes en ningún estado.</EmptyNote>;
          }
          return (
            <BarList
              ariaLabel="Solicitudes por estado"
              items={rows.map((s) => ({
                key: s.status,
                label: s.status_label,
                value: s.count,
                display: count(s.count),
                fill: toneFor("application", s.status),
                marker: <ToneDot code={s.status} />,
              }))}
            />
          );
        }}
      </BlockState>
    </Card>
  );
}
