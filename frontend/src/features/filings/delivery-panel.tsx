"use client";

import { Alert, Button } from "antd";
import { useState } from "react";

import type { ApplicationDetail } from "@/features/applications/workspace-queries";
import { startDownload } from "@/features/filings/download";
import { packageSummary, RegisterFilingModal } from "@/features/filings/filing-modals";
import {
  isPackageRunning,
  PACKAGE_COMPLETED,
  usePackageDownload,
  usePackageJob,
  useRequestPackage,
  type PackageJob,
} from "@/features/filings/queries";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

const PACKAGE_FAILED = "FAILED";
const PACKAGE_EXPIRED = "EXPIRED";
/** Al descargar: el ZIP ya no está (API §19.2); se vuelve a leer el trabajo. */
const EXPIRED_CODE = "PACKAGE_EXPIRED";

export interface DeliveryPermissions {
  /** `filings.prepare`: pedir y descargar el paquete. */
  prepare: boolean;
  /** `filings.create`: registrar la radicación. También decide la acción principal. */
  create: boolean;
}

/** Mensaje de la API y sus detalles (por ejemplo, los documentos que faltan). */
function ApiErrorAlert({ error, title }: { error: unknown; title: string }) {
  const message = isApiError(error) ? error.message : "Ocurrió un error inesperado.";
  const details = isApiError(error) ? error.details.map((d) => d.message).filter(Boolean) : [];
  return (
    <Alert
      type="error"
      showIcon
      title={title}
      description={
        <>
          <p className="m-0">{message}</p>
          {details.length > 0 && (
            <ul className="m-0 mt-1 pl-5">
              {details.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}
        </>
      }
    />
  );
}

function PackageState({ job }: { job: PackageJob }) {
  if (isPackageRunning(job)) {
    return (
      <p role="status" className="text-text-secondary m-0 flex items-center gap-2 text-sm">
        <span
          aria-hidden="true"
          className="border-border-strong size-3.5 animate-spin rounded-full border-2 border-t-transparent"
        />
        Preparando el paquete. Se actualiza solo; puede tardar unos segundos.
      </p>
    );
  }
  if (job.status === PACKAGE_COMPLETED) {
    return (
      <div role="status" className="grid gap-0.5 text-sm">
        <span className="font-medium">
          Paquete listo: <span className="font-mono text-xs break-all">{job.output?.filename}</span>
        </span>
        <span className="text-text-tertiary text-xs">
          {packageSummary(job)}
          {job.expires_at && ` · se puede descargar hasta el ${formatDateTime(job.expires_at)}`}
        </span>
      </div>
    );
  }
  if (job.status === PACKAGE_EXPIRED) {
    return (
      <Alert type="warning" showIcon title="El paquete venció" description="Prepara uno nuevo." />
    );
  }
  if (job.status === PACKAGE_FAILED) {
    return (
      <Alert
        type="error"
        showIcon
        title="No se pudo armar el paquete"
        description={`Prepara uno nuevo.${job.error_code ? ` Código: ${job.error_code}.` : ""}`}
      />
    );
  }
  return null;
}

/**
 * "Entregar al banco" (solicitud lista para radicar): preparar el paquete, descargarlo y
 * registrar la radicación. El trabajo del paquete vive en la pestaña: si se vuelve a
 * pedir, la API devuelve el mismo mientras la huella documental no cambie.
 */
export function DeliveryPanel({
  detail,
  version,
  can,
}: {
  detail: ApplicationDetail;
  version: number;
  can: DeliveryPermissions;
}) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState(false);
  const [registering, setRegistering] = useState(false);
  const job = usePackageJob(jobId);
  const request = useRequestPackage(detail.id);
  const download = usePackageDownload();

  const current = jobId ? job.data : undefined;
  const ready = current?.status === PACKAGE_COMPLETED;
  const canRequest = can.prepare && !isPackageRunning(current) && !ready;
  // Una sola acción principal: preparar, luego descargar y al final registrar.
  const primary = !can.create ? null : !ready ? "prepare" : downloaded ? "register" : "download";

  const prepare = () => {
    download.reset();
    request.mutate(undefined, {
      onSuccess: (created) => {
        setJobId(created.id);
        setDownloaded(false);
      },
    });
  };

  const getZip = () => {
    if (!current) return;
    download.mutate(current.id, {
      onSuccess: ({ url }) => {
        startDownload(url);
        setDownloaded(true);
      },
      onError: (error) => {
        if (isApiError(error) && error.code === EXPIRED_CODE) void job.refetch();
      },
    });
  };

  return (
    <article
      aria-labelledby="delivery-title"
      className="bg-bg-surface border-border-default grid gap-4 rounded-lg border p-5"
    >
      <div className="grid gap-1">
        <h2 id="delivery-title" className="m-0 text-lg leading-snug font-semibold">
          Entregar al banco
        </h2>
        <p className="text-text-secondary m-0 text-sm">
          Prepara el paquete con los documentos aprobados, descárgalo, entrégalo por el canal del
          banco y registra la radicación.
        </p>
      </div>

      {current && <PackageState job={current} />}
      {request.isError && (
        <ApiErrorAlert error={request.error} title="No se pudo preparar el paquete" />
      )}
      {download.isError && (
        <ApiErrorAlert error={download.error} title="No se pudo descargar el paquete" />
      )}
      {job.isError && <ApiErrorAlert error={job.error} title="No pudimos consultar el paquete" />}

      <div className="flex flex-wrap items-center gap-2 max-[860px]:[&>*]:flex-[1_1_auto]">
        {canRequest && (
          <Button
            type={primary === "prepare" ? "primary" : "default"}
            loading={request.isPending}
            onClick={prepare}
          >
            {current ? "Preparar otro paquete" : "Preparar paquete"}
          </Button>
        )}
        {ready && can.prepare && (
          <Button
            type={primary === "download" ? "primary" : "default"}
            loading={download.isPending}
            onClick={getZip}
          >
            Descargar ZIP
          </Button>
        )}
        {can.create && (
          <Button
            type={primary === "register" ? "primary" : "default"}
            disabled={!ready || !detail.bank_product}
            aria-describedby={!ready ? "delivery-register-reason" : undefined}
            onClick={() => setRegistering(true)}
          >
            Registrar radicación
          </Button>
        )}
      </div>
      {can.create && !ready && (
        <p id="delivery-register-reason" className="text-text-tertiary m-0 -mt-2 text-xs">
          Para registrar la radicación, primero prepara el paquete.
        </p>
      )}

      <RegisterFilingModal
        detail={detail}
        version={version}
        job={ready ? current : null}
        open={registering}
        onClose={() => setRegistering(false)}
        onFiled={() => {
          setJobId(null);
          setDownloaded(false);
        }}
      />
    </article>
  );
}
