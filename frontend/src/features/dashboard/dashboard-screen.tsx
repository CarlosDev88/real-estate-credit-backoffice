"use client";

import { useMemo } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { useMe } from "@/features/auth/queries";
import {
  DashboardFiltersBar,
  periodLabel,
  type SelectFilterDef,
} from "@/features/dashboard/dashboard-filters";
import { useDashboardFilters } from "@/features/dashboard/dashboard-params";
import { BankResultsBlock, FunnelBlock, WorkloadBlock } from "@/features/dashboard/detail-blocks";
import {
  bankLabel,
  filterErrorsOf,
  useActiveBanks,
  useAdvisors,
  useCatalog,
  useDashboardBankResults,
  useDashboardFunnel,
  useDashboardSummary,
  useDashboardWorkload,
} from "@/features/dashboard/queries";
import { StatusSnapshot, SummaryTiles } from "@/features/dashboard/summary-blocks";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

/** Mismo corte que el shell y el listado: en 860 px o menos, filtros en hoja y tarjetas. */
const MOBILE_QUERY = "(max-width: 860px)";

/** Permiso de "Mi día" (la entrada del menú de la Parte 2, `GET /workday/applications`). */
const MY_DAY_PERMISSION = "workday.read";

function useSelectFilters(permissions: readonly string[]): SelectFilterDef[] {
  // El filtro de asesor es del administrador: el asesor solo puede mandarse a sí mismo y
  // el broker ninguno. Se ofrece a quien puede listar usuarios (`users.read`).
  const canListAdvisors = permissions.includes("users.read");
  const canReadBanks = permissions.includes("banks.read");
  const advisors = useAdvisors(canListAdvisors);
  const banks = useActiveBanks(canReadBanks);
  const purposes = useCatalog("loan_purpose");

  return useMemo(() => {
    const defs: SelectFilterDef[] = [];
    if (canListAdvisors) {
      defs.push({
        key: "advisor_id",
        label: "Asesor",
        allLabel: "todos",
        options: (advisors.data ?? []).map((u) => ({ value: u.id, label: u.name || u.email })),
        loading: advisors.isPending,
        width: 180,
      });
    }
    if (canReadBanks) {
      defs.push({
        key: "bank_id",
        label: "Banco",
        allLabel: "todos",
        options: (banks.data ?? []).map((bank) => ({ value: bank.id, label: bankLabel(bank) })),
        loading: banks.isPending,
        width: 150,
      });
    }
    defs.push({
      key: "purpose_code",
      label: "Finalidad",
      allLabel: "todas",
      options: purposes.items.map((item) => ({ value: item.code, label: item.label })),
      loading: purposes.isPending,
      width: 170,
    });
    return defs;
  }, [canListAdvisors, canReadBanks, advisors.data, advisors.isPending, banks, purposes]);
}

/** Dashboard de operación (`/dashboard`, vista 2): cifras, estados, embudo, carga y bancos. */
export function DashboardScreen() {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const { filters, update } = useDashboardFilters();
  const mobile = useMediaQuery(MOBILE_QUERY);
  const selects = useSelectFilters(permissions);

  const summary = useDashboardSummary(filters);
  const funnel = useDashboardFunnel(filters);
  const workload = useDashboardWorkload(filters);
  const banks = useDashboardBankResults(filters);

  const period = summary.data?.period ?? funnel.data?.period ?? banks.data?.period;
  const errors = filterErrorsOf([summary.error, funnel.error, workload.error, banks.error]);

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Dashboard"
        description={
          periodLabel(period) ? `Periodo: ${periodLabel(period)}` : "Periodo: mes en curso"
        }
      />

      <DashboardFiltersBar
        filters={filters}
        period={period}
        selects={selects}
        errors={errors}
        onChange={update}
        mobile={mobile}
      />

      <SummaryTiles
        query={summary}
        showTasks={permissions.includes("tasks.read")}
        linkTasks={permissions.includes(MY_DAY_PERMISSION)}
        // Los montos son del administrador y del asesor, los mismos que tienen tareas.
        showAmounts={permissions.includes("tasks.read")}
      />

      <div className="grid gap-4 min-[1100px]:grid-cols-2">
        <StatusSnapshot query={summary} />
        <FunnelBlock query={funnel} />
      </div>

      <WorkloadBlock query={workload} mobile={mobile} />
      <BankResultsBlock query={banks} mobile={mobile} />
    </div>
  );
}
