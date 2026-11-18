"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "antd";

import { DataList, Datum } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { periodLabel } from "@/features/dashboard/dashboard-filters";
import { startDownload } from "@/features/filings/download";
import {
  ACTIVE_EXPORT,
  reportKeys,
  useExportDownloadUrl,
  useLiveExportJobs,
  type ExportJob,
} from "@/features/reports/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime, formatInteger } from "@/lib/format";
import { useApiErrorToast } from "@/providers/api-error-toast";

const isActive = (job: ExportJob) => (ACTIVE_EXPORT as readonly string[]).includes(job.status);

function JobItem({
  job,
  onDownload,
  downloading,
}: {
  job: ExportJob;
  onDownload: (job: ExportJob) => void;
  downloading: boolean;
}) {
  const period = periodLabel({ date_from: job.filters.date_from, date_to: job.filters.date_to });
  return (
    <li className="border-border-default grid gap-2 border-b py-3 last:border-b-0">
      <div className="flex items-center gap-2">
        <b className="font-medium">{job.report_type_label}</b>
        {/* El estado en texto, y el "en proceso" se anuncia al cambiar. */}
        <span aria-live="polite" className="text-text-secondary text-sm">
          · {job.status_label}
        </span>
        {job.status === "COMPLETED" && (
          <Button
            size="small"
            className="ml-auto"
            loading={downloading}
            onClick={() => onDownload(job)}
          >
            Descargar
            <span className="sr-only"> la exportación del {formatDateTime(job.created_at)}</span>
          </Button>
        )}
      </div>
      <DataList layout="inline">
        <Datum label="Periodo">{period}</Datum>
        {job.filters.status.length > 0 && (
          <Datum label="Estados">
            {job.filters.status.length === 1 ? "1 estado" : `${job.filters.status.length} estados`}
          </Datum>
        )}
        <Datum label="Filas">
          {job.row_count === null ? null : formatInteger(job.row_count) || "0"}
        </Datum>
        <Datum label="Pedida">{formatDateTime(job.created_at)}</Datum>
        <Datum label="Vence">{formatDateTime(job.expires_at)}</Datum>
      </DataList>
      {job.status === "FAILED" && (
        <p className="text-text-secondary m-0 text-sm">No se pudo generar: prepara otra.</p>
      )}
    </li>
  );
}

interface ExportsPanelProps {
  open: boolean;
  onClose: () => void;
  query: UseQueryResult<{ items: ExportJob[]; total: number }>;
  onPrepare: () => void;
  preparing: boolean;
  /** Mensaje del último intento de "Preparar exportación" (por ejemplo, `429 TOO_MANY_EXPORTS`). */
  prepareError: string | null;
}

/** "Mis exportaciones": preparar una con los filtros actuales y descargar las terminadas. */
export function ExportsPanel({
  open,
  onClose,
  query,
  onPrepare,
  preparing,
  prepareError,
}: ExportsPanelProps) {
  const queryClient = useQueryClient();
  const showError = useApiErrorToast();
  const download = useExportDownloadUrl();
  const jobs = useLiveExportJobs(query.data?.items ?? []);

  const onDownload = (job: ExportJob) =>
    download.mutate(job.id, {
      onSuccess: (data) => startDownload(data.url),
      onError: (error) => {
        showError(error);
        // `409` (aún no está lista) o `410` (venció): la lista está vieja.
        if (isApiError(error) && (error.status === 409 || error.status === 410)) {
          void queryClient.invalidateQueries({ queryKey: reportKeys.exports });
          void queryClient.invalidateQueries({ queryKey: reportKeys.exportJob(job.id) });
        }
      },
    });

  let body;
  if (query.isPending) body = <LoadingState label="Cargando tus exportaciones" blocks={[72, 72]} />;
  else if (query.isError) {
    body = (
      <ErrorState
        title="No pudimos cargar tus exportaciones"
        message={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isRefetching}
      />
    );
  } else if (jobs.length === 0) {
    body = (
      <EmptyState
        title="Todavía no tienes exportaciones"
        description="Prepara una para descargar un reporte grande."
      />
    );
  } else {
    body = (
      <ul aria-label="Mis exportaciones" className="m-0 list-none p-0">
        {jobs.map((job) => (
          <JobItem
            key={job.id}
            job={job}
            onDownload={onDownload}
            downloading={download.isPending && download.variables === job.id}
          />
        ))}
      </ul>
    );
  }

  const anyActive = jobs.some(isActive);

  return (
    <SidePanel open={open} onClose={onClose} title="Mis exportaciones" width={480}>
      <div className="grid gap-4">
        <div className="grid gap-2">
          <p className="text-text-secondary m-0 text-sm">
            Se arma en segundo plano con los filtros de la vista y queda disponible 24 horas.
          </p>
          <div>
            <Button
              type="primary"
              loading={preparing}
              onClick={onPrepare}
              aria-describedby={prepareError ? "prepare-export-error" : undefined}
            >
              Preparar exportación
            </Button>
          </div>
          {prepareError && (
            <p id="prepare-export-error" role="alert" className="text-tone-danger-fg m-0 text-sm">
              {prepareError}
            </p>
          )}
          {anyActive && (
            <p role="status" className="text-text-tertiary m-0 text-xs">
              Revisamos el avance cada 3 segundos.
            </p>
          )}
        </div>
        {body}
      </div>
    </SidePanel>
  );
}
