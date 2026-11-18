"use client";

import { Alert, Button, Select } from "antd";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/card";
import { ListPagination } from "@/components/ui/list-pagination";
import { PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { useMe } from "@/features/auth/queries";
import { FilterErrorNote } from "@/features/dashboard/block-state";
import {
  DashboardFiltersBar,
  periodLabel,
  type ExtraFilters,
  type SelectFilterDef,
} from "@/features/dashboard/dashboard-filters";
import { FunnelTable } from "@/features/dashboard/funnel-table";
import {
  bankLabel,
  filterErrorsOf,
  isFilterError,
  useActiveBanks,
  useAdvisors,
  useCatalog,
} from "@/features/dashboard/queries";
import { ExportsPanel } from "@/features/reports/exports-panel";
import {
  useCreateExport,
  useDownloadCsv,
  useExportJobs,
  useReportApplications,
  useReportFunnel,
} from "@/features/reports/queries";
import { ApplicationsReport, GroupedFunnelTable } from "@/features/reports/report-tables";
import {
  CLEARED,
  filtersOf,
  PAGE_SIZES,
  REPORT_FILTER_KEYS,
  useReportParams,
  type GroupBy,
  type ReportTab,
} from "@/features/reports/reports-params";
import { isApiError } from "@/lib/api/errors";
import { useIdempotencyKey } from "@/lib/api/idempotency";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { useApiErrorToast } from "@/providers/api-error-toast";
import { useToast } from "@/providers/toast";

const MOBILE_QUERY = "(max-width: 860px)";

/** Opciones de "Agrupar por" (`group_by` de la API) y el encabezado de la tabla. */
const GROUP_OPTIONS: { value: GroupBy; label: string; header: string }[] = [
  { value: "advisor", label: "asesor", header: "Asesor" },
  { value: "bank", label: "banco", header: "Banco" },
  { value: "purpose", label: "finalidad", header: "Finalidad" },
];

const TABS: { key: ReportTab; label: string }[] = [
  { key: "embudo", label: "Embudo" },
  { key: "solicitudes", label: "Solicitudes" },
];

function useSelectFilters(permissions: readonly string[]): SelectFilterDef[] {
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
        options: (banks.data ?? []).map((b) => ({ value: b.id, label: bankLabel(b) })),
        loading: banks.isPending,
        width: 150,
      });
    }
    defs.push({
      key: "purpose_code",
      label: "Finalidad",
      allLabel: "todas",
      options: purposes.items.map((p) => ({ value: p.code, label: p.label })),
      loading: purposes.isPending,
      width: 170,
    });
    return defs;
  }, [canListAdvisors, canReadBanks, advisors.data, advisors.isPending, banks, purposes]);
}

/** Reportes (`/reportes`, vista 10): embudo, solicitudes y exportación. */
export function ReportsScreen() {
  const me = useMe();
  const permissions = useMemo(() => me.data?.permissions ?? [], [me.data]);
  const canExport = permissions.includes("reports.export");
  const { params, update } = useReportParams();
  const filters = useMemo(() => filtersOf(params), [params]);
  const mobile = useMediaQuery(MOBILE_QUERY);
  const selects = useSelectFilters(permissions);
  const statuses = useCatalog("application_status");
  const toast = useToast();
  const showError = useApiErrorToast();

  const funnel = useReportFunnel(filters, params.group_by, params.tab === "embudo");
  const applications = useReportApplications(
    filters,
    params.page,
    params.page_size,
    params.tab === "solicitudes",
  );

  // ---------- exportar ----------
  const [panelOpen, setPanelOpen] = useState(false);
  const [tooLarge, setTooLarge] = useState<string | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const csv = useDownloadCsv();
  const exportsList = useExportJobs(canExport && panelOpen);
  const createExport = useCreateExport();
  // Una clave por intento: la misma si se reintenta con los mismos filtros.
  const idempotency = useIdempotencyKey(JSON.stringify(filters));

  const downloadCsv = () => {
    setTooLarge(null);
    csv.mutate(filters, {
      onSuccess: (name) => toast.success({ title: "Descarga iniciada", message: name }),
      onError: (error) => {
        if (isApiError(error) && error.code === "EXPORT_TOO_LARGE") setTooLarge(error.message);
        else showError(error);
      },
    });
  };

  const prepare = () => {
    setPrepareError(null);
    setPanelOpen(true);
    createExport.mutate(
      { filters, key: idempotency.current() },
      {
        onSuccess: (job) => {
          idempotency.reset();
          setTooLarge(null);
          toast.success({ title: "Exportación pedida", message: job.status_label });
        },
        onError: (error) => {
          if (isApiError(error) && error.status === 429) setPrepareError(error.message);
          else if (isApiError(error) && isFilterError(error, REPORT_FILTER_KEYS)) {
            setPrepareError(error.message);
          } else showError(error);
        },
      },
    );
  };

  // ---------- filtros ----------
  const errors = filterErrorsOf([funnel.error, applications.error], REPORT_FILTER_KEYS);
  const statusLabel = (code: string) => statuses.items.find((s) => s.code === code)?.label ?? code;
  const groupOption = GROUP_OPTIONS.find((g) => g.value === params.group_by);

  const extra: ExtraFilters = {
    labels: { status: "Estado", group_by: "Agrupar por" },
    active: params.status.length > 0 || params.group_by !== "",
    chips: [
      ...(params.status.length
        ? [
            {
              key: "status",
              label: "Estado",
              value:
                params.status.length <= 2
                  ? params.status.map(statusLabel).join(", ")
                  : `${params.status.length} estados`,
            },
          ]
        : []),
      ...(groupOption && params.tab === "embudo"
        ? [{ key: "group_by", label: "Agrupar por", value: groupOption.label }]
        : []),
    ],
    onRemoveChip: (key) => update(key === "status" ? { status: [] } : { group_by: "" }),
    render: (block, control) => (
      <>
        <Select
          mode="multiple"
          aria-label="Filtrar por estado"
          placeholder="Estado: todos"
          value={params.status}
          onChange={(status: string[]) => update({ status })}
          options={statuses.items.map((s) => ({ value: s.code, label: s.label }))}
          loading={statuses.isPending}
          maxTagCount="responsive"
          allowClear
          virtual={false}
          popupMatchSelectWidth={false}
          size={block ? "large" : "middle"}
          style={block ? { width: "100%" } : { width: 240 }}
          {...control("status")}
        />
        {params.tab === "embudo" && (
          <Select
            aria-label="Agrupar por"
            value={params.group_by}
            onChange={(group_by: GroupBy | "") => update({ group_by })}
            options={[
              { value: "", label: "sin agrupar" },
              ...GROUP_OPTIONS.map((g) => ({ value: g.value, label: g.label })),
            ]}
            labelRender={() => `Agrupar por: ${groupOption?.label ?? "sin agrupar"}`}
            virtual={false}
            popupMatchSelectWidth={false}
            size={block ? "large" : "middle"}
            style={block ? { width: "100%" } : { width: 240 }}
            {...control("group_by")}
          />
        )}
      </>
    ),
  };

  const period = funnel.data?.period;

  // ---------- contenido ----------
  let content;
  if (params.tab === "embudo") {
    if (funnel.isPending) content = <LoadingState label="Cargando el embudo" blocks={[240]} />;
    else if (funnel.isError) {
      content = isFilterError(funnel.error, REPORT_FILTER_KEYS) ? (
        <FilterErrorNote />
      ) : (
        <ErrorState
          title="No pudimos cargar el embudo"
          message={funnel.error.message}
          onRetry={() => void funnel.refetch()}
          retrying={funnel.isRefetching}
        />
      );
    } else if ((funnel.data.stages[0]?.count ?? 0) === 0) {
      content = <EmptyState size="sm" title="No se crearon solicitudes con estos filtros" />;
    } else if (funnel.data.group_by && groupOption) {
      content = (
        <div className="-mx-5 -mb-5">
          <GroupedFunnelTable funnel={funnel.data} groupLabel={groupOption.header} />
        </div>
      );
    } else {
      content = <FunnelTable stages={funnel.data.stages} caption="Embudo de solicitudes" />;
    }
  } else if (applications.isPending) {
    content = <LoadingState label="Cargando las solicitudes" blocks={[52, 52, 52, 52]} />;
  } else if (applications.isError) {
    content = isFilterError(applications.error, REPORT_FILTER_KEYS) ? (
      <FilterErrorNote />
    ) : (
      <ErrorState
        title="No pudimos cargar las solicitudes"
        message={applications.error.message}
        onRetry={() => void applications.refetch()}
        retrying={applications.isRefetching}
      />
    );
  } else if (applications.data.items.length === 0) {
    content = <EmptyState size="sm" title="No hay solicitudes con estos filtros" />;
  } else {
    content = (
      <div className="-mx-5 -mb-5">
        <ApplicationsReport
          rows={applications.data.items}
          busy={applications.isFetching && applications.isPlaceholderData}
          mobile={mobile}
        />
        <ListPagination
          page={params.page}
          pageSize={params.page_size}
          total={applications.data.total}
          itemsLabel="Solicitudes"
          onPage={(page) => update({ page })}
          onPageSize={(page_size) => update({ page_size })}
          compact={mobile}
          pageSizes={PAGE_SIZES}
        />
      </div>
    );
  }

  return (
    <div className="grid content-start gap-4">
      <PageHeader
        title="Reportes"
        description={
          periodLabel(period)
            ? `Periodo: ${periodLabel(period)}`
            : "Solicitudes creadas en el periodo"
        }
        actions={
          canExport ? (
            <>
              <Button type="primary" loading={csv.isPending} onClick={downloadCsv}>
                Descargar CSV
              </Button>
              <Button onClick={() => setPanelOpen(true)}>Mis exportaciones</Button>
            </>
          ) : undefined
        }
      />

      {tooLarge && (
        <Alert
          type="warning"
          showIcon
          title="El reporte es muy grande para descargarlo directo"
          description={tooLarge}
          action={
            <Button size="small" type="primary" onClick={prepare} loading={createExport.isPending}>
              Preparar exportación
            </Button>
          }
          closable={{ "aria-label": "Cerrar aviso" }}
          onClose={() => setTooLarge(null)}
        />
      )}

      <DashboardFiltersBar
        filters={params}
        period={period}
        selects={selects}
        errors={errors}
        onChange={update}
        onClear={() => update(CLEARED)}
        extra={extra}
        mobile={mobile}
      />

      <ScrollTabs
        ariaLabel="Reportes"
        items={TABS}
        value={params.tab}
        onChange={(tab) => update({ tab: tab as ReportTab })}
      />

      <Card title={params.tab === "embudo" ? "Embudo" : "Solicitudes"}>
        {params.tab === "embudo" && (
          <p className="text-text-tertiary m-0 mb-4 text-xs">
            {params.group_by
              ? "Una fila por grupo. Debajo de cada número, la conversión contra las creadas del grupo."
              : "Solicitudes creadas en el periodo y hasta qué etapa llegaron."}
          </p>
        )}
        {content}
      </Card>

      {canExport && (
        <ExportsPanel
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
          query={exportsList}
          onPrepare={prepare}
          preparing={createExport.isPending}
          prepareError={prepareError}
        />
      )}
    </div>
  );
}
