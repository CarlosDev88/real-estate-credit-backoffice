"use client";

import { Button } from "antd";

import { Card } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { ToneBadge } from "@/components/ui/status-badge";
import { ApiErrorAlert, PACKAGE_EXPIRED, PACKAGE_FAILED } from "@/features/filings/delivery-panel";
import { startDownload } from "@/features/filings/download";
import { packageSummary } from "@/features/filings/filing-modals";
import {
  isPackageRunning,
  PACKAGE_COMPLETED,
  usePackageDownload,
  usePackageJobs,
  type PackageJob,
} from "@/features/filings/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

/** Al descargar: el ZIP ya no está (API §19.2); se vuelve a pedir la lista. */
const EXPIRED_CODE = "PACKAGE_EXPIRED";

/**
 * Tono del estado del paquete. Es presentación: `design/status-tones` no tiene paquetes
 * (candidato a sumarlos a `design/tokens`); el texto es el `status_label` de la API.
 */
function toneOf(job: PackageJob) {
  if (isPackageRunning(job)) return "info" as const;
  if (job.status === PACKAGE_COMPLETED) return "success" as const;
  if (job.status === PACKAGE_FAILED) return "danger" as const;
  return "neutral" as const;
}

function PackageRow({
  job,
  onDownload,
  downloading,
}: {
  job: PackageJob;
  onDownload: (job: PackageJob) => void;
  downloading: boolean;
}) {
  const ready = job.status === PACKAGE_COMPLETED;
  const facts = [
    `Pedido el ${formatDateTime(job.created_at) ?? ""}`,
    job.requested_by ? `por ${job.requested_by.name}` : null,
    ready ? packageSummary(job) : null,
    ready && job.expires_at ? `se descarga hasta el ${formatDateTime(job.expires_at)}` : null,
    job.status === PACKAGE_FAILED && job.error_code ? `Código: ${job.error_code}` : null,
  ].filter(Boolean);
  return (
    <li className="border-border-default flex flex-wrap items-center gap-3 border-b py-3 last:border-b-0">
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <ToneBadge tone={toneOf(job)}>{job.status_label}</ToneBadge>
          {ready && job.output?.filename && (
            <span className="font-mono text-xs break-all">{job.output.filename}</span>
          )}
        </div>
        <span className="text-text-tertiary text-xs">{facts.join(" · ")}</span>
      </div>
      {ready && (
        <Button size="small" loading={downloading} onClick={() => onDownload(job)}>
          Descargar<span className="sr-only"> el paquete del {formatDateTime(job.created_at)}</span>
        </Button>
      )}
    </li>
  );
}

/**
 * "Paquetes" de la pestaña Radicación (`GET .../document-package-jobs`, `filings.prepare`):
 * todos los pedidos, del más nuevo al más antiguo, con su estado y la descarga del ZIP
 * mientras no venza.
 */
export function PackagesList({ applicationId }: { applicationId: string }) {
  const jobs = usePackageJobs(applicationId, true);
  const download = usePackageDownload();

  const getZip = (job: PackageJob) =>
    download.mutate(job.id, {
      onSuccess: ({ url }) => startDownload(url),
      onError: (error) => {
        if (isApiError(error) && error.code === EXPIRED_CODE) void jobs.refetch();
      },
    });

  if (jobs.isPending) return <LoadingState label="Cargando los paquetes" blocks={[64]} />;
  if (jobs.isError) {
    return (
      <Card title="Paquetes">
        <ErrorState
          variant="inline"
          title="No pudimos cargar los paquetes."
          onRetry={() => void jobs.refetch()}
        />
      </Card>
    );
  }
  // Sin paquetes no hay nada que listar (el panel de entrega explica cómo pedirlo).
  if (jobs.data.items.length === 0) return null;

  const total = jobs.data.total;
  return (
    <Card
      title="Paquetes"
      action={
        <span className="text-text-tertiary text-sm">
          {total === 1 ? "1 pedido" : `${total} pedidos`}
        </span>
      }
    >
      {download.isError && (
        <div className="mb-3">
          <ApiErrorAlert error={download.error} title="No se pudo descargar el paquete" />
        </div>
      )}
      <ul className="-my-3 m-0 list-none p-0" aria-label="Paquetes de documentos">
        {jobs.data.items.map((job) => (
          <PackageRow
            key={job.id}
            job={job}
            onDownload={getZip}
            downloading={download.isPending && download.variables === job.id}
          />
        ))}
      </ul>
      {jobs.data.items.some((j) => j.status === PACKAGE_EXPIRED) && (
        <p className="text-text-tertiary m-0 mt-3 text-xs">
          Un paquete vencido ya no se descarga: se prepara uno nuevo.
        </p>
      )}
    </Card>
  );
}
