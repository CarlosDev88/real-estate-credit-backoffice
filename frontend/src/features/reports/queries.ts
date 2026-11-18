"use client";

import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { reportQuery, type GroupBy, type ReportFilters } from "@/features/reports/reports-params";
import { filenameFrom, saveBlob } from "@/features/reports/save-file";
import { api, call } from "@/lib/api/client";
import type { components, operations } from "@/lib/api/schema";

export type ReportFunnel = components["schemas"]["ReportFunnel"];
export type ReportFunnelGroup = components["schemas"]["ReportFunnelGroup"];
export type ReportApplication = components["schemas"]["ReportApplication"];
export type ExportJob = components["schemas"]["ReportExportJob"];
type FunnelQuery = NonNullable<operations["reports_funnel"]["parameters"]["query"]>;
type ListQuery = NonNullable<operations["reports_applications_list"]["parameters"]["query"]>;
type CsvQuery = NonNullable<operations["reports_applications_csv"]["parameters"]["query"]>;
type ExportBody = components["schemas"]["ExportJobRequestRequest"];

/** Estados en los que una exportación todavía avanza: se consulta cada 3 s. */
export const ACTIVE_EXPORT = ["PENDING", "RUNNING"] as const;
export const EXPORT_POLL_MS = 3000;
export const EXPORTS_PAGE_SIZE = 10;

export const reportKeys = {
  all: ["reports"] as const,
  funnel: (filters: ReportFilters, groupBy: string) =>
    ["reports", "funnel", filters, groupBy] as const,
  applications: (filters: ReportFilters, page: number, pageSize: number) =>
    ["reports", "applications", filters, page, pageSize] as const,
  exports: ["reports", "export-jobs"] as const,
  exportJob: (id: string) => ["report-export-jobs", id] as const,
};

export function useReportFunnel(filters: ReportFilters, groupBy: GroupBy | "", enabled: boolean) {
  return useQuery({
    queryKey: reportKeys.funnel(filters, groupBy),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/reports/funnel", {
            params: {
              query: {
                ...reportQuery(filters),
                ...(groupBy ? { group_by: groupBy } : {}),
              } as FunnelQuery,
            },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useReportApplications(
  filters: ReportFilters,
  page: number,
  pageSize: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: reportKeys.applications(filters, page, pageSize),
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/reports/applications", {
            params: {
              query: { ...reportQuery(filters), page, page_size: pageSize } as ListQuery,
            },
          }),
        )
      ).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

// ---------- exportar ----------

/**
 * "Descargar CSV": `GET /reports/applications.csv` con los filtros. El archivo llega en la
 * respuesta y se guarda con el nombre de `Content-Disposition`. Un `422 EXPORT_TOO_LARGE`
 * lo maneja la vista (ofrece la exportación asíncrona).
 */
export function useDownloadCsv() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (filters: ReportFilters) => {
      const { data, response } = await call(
        api.GET("/api/v1/reports/applications.csv", {
          params: { query: reportQuery(filters) as CsvQuery },
          parseAs: "blob",
        }),
      );
      const name = filenameFrom(response.headers.get("Content-Disposition"), "solicitudes.csv");
      saveBlob(data as Blob, name);
      return name;
    },
  });
}

/** Mis exportaciones (`GET /reports/applications/export-jobs`), de la más nueva. */
export function useExportJobs(enabled: boolean) {
  return useQuery({
    queryKey: reportKeys.exports,
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/reports/applications/export-jobs", {
            params: { query: { page_size: EXPORTS_PAGE_SIZE } },
          }),
        )
      ).data,
    enabled,
  });
}

/**
 * Las exportaciones que avanzan se consultan una por una (`GET /report-export-jobs/{id}`)
 * cada 3 s, no el listado: `/reports/*` comparte un cupo de 20 consultas por minuto con
 * el dashboard, y el listado cada 3 s lo agotaría. Devuelve la lista con lo más reciente.
 */
export function useLiveExportJobs(jobs: ExportJob[]): ExportJob[] {
  const active = jobs.filter((job) => (ACTIVE_EXPORT as readonly string[]).includes(job.status));
  const polled = useQueries({
    queries: active.map((job) => ({
      queryKey: reportKeys.exportJob(job.id),
      queryFn: async () =>
        (
          await call(
            api.GET("/api/v1/report-export-jobs/{job_id}", {
              params: { path: { job_id: job.id } },
            }),
          )
        ).data,
      initialData: job,
      // El dato de la lista vale desde que se pidió o empezó: una recién creada se vuelve a
      // consultar a los 3 s; una vieja, al abrir el panel.
      initialDataUpdatedAt: Date.parse(job.started_at ?? job.created_at),
      refetchInterval: (query: { state: { data?: ExportJob } }) =>
        query.state.data && (ACTIVE_EXPORT as readonly string[]).includes(query.state.data.status)
          ? EXPORT_POLL_MS
          : false,
    })),
  });
  const byId = new Map(
    polled
      .map((q) => q.data)
      .filter((j): j is ExportJob => !!j)
      .map((j) => [j.id, j]),
  );
  return jobs.map((job) => byId.get(job.id) ?? job);
}

/** "Preparar exportación": `POST` con los filtros en el cuerpo y `Idempotency-Key`. */
export function useCreateExport() {
  const queryClient = useQueryClient();
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async ({ filters, key }: { filters: ReportFilters; key: string }) =>
      (
        await call(
          api.POST("/api/v1/reports/applications/export-jobs", {
            params: { header: { "Idempotency-Key": key } },
            body: reportQuery(filters) as ExportBody,
          }),
        )
      ).data,
    onSuccess: (job) => {
      // La nueva va primero, sin esperar otra consulta del listado. Si el listado todavía
      // no llegó (se abrió el panel junto con el pedido), se vuelve a pedir.
      const old = queryClient.getQueryData<{ items: ExportJob[]; total: number }>(
        reportKeys.exports,
      );
      if (!old || queryClient.isFetching({ queryKey: reportKeys.exports }) > 0) {
        void queryClient.invalidateQueries({ queryKey: reportKeys.exports });
        return;
      }
      queryClient.setQueryData(reportKeys.exports, {
        ...old,
        items: [job, ...old.items.filter((j) => j.id !== job.id)],
        total: old.total + 1,
      });
    },
  });
}

/** "Descargar" una exportación: pide la URL firmada cada vez (vence a los 5 minutos). */
export function useExportDownloadUrl() {
  return useMutation({
    meta: { handlesErrors: true },
    mutationFn: async (id: string) =>
      (
        await call(
          api.GET("/api/v1/report-export-jobs/{job_id}/download", {
            params: { path: { job_id: id } },
          }),
        )
      ).data,
  });
}
