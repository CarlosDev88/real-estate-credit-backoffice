"use client";

import { App, Button } from "antd";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { PORTAL_HOME, PortalPage } from "@/features/buyer-portal/portal-shell";
import { useConsentAction, useConsents, type BuyerConsent } from "@/features/buyer-portal/queries";
import { formatDateTime } from "@/lib/format";
import { useToast } from "@/providers/toast";

function ConsentCard({
  consent,
  disabled,
  pendingId,
  onAccept,
  onWithdraw,
}: {
  consent: BuyerConsent;
  disabled: boolean;
  pendingId: string | null;
  onAccept: (consent: BuyerConsent) => void;
  onWithdraw: (consent: BuyerConsent) => void;
}) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const titleId = useId();
  const accepted = consent.status === "ACCEPTED";
  const busy = pendingId === consent.id;

  return (
    <article
      aria-labelledby={titleId}
      className={`bg-bg-surface grid gap-3 rounded-xl border p-4 ${
        !accepted && consent.required ? "border-tone-warning-border" : "border-border-default"
      }`}
    >
      <div className="grid gap-1">
        <h2 id={titleId} className="m-0 text-lg font-semibold">
          {consent.title}
        </h2>
        <p className="text-text-tertiary m-0 flex flex-wrap gap-x-2 text-sm">
          <span>{consent.required ? "Obligatorio" : "Opcional"}</span>
          {accepted && consent.accepted_at && (
            <>
              <span aria-hidden="true">·</span>
              <span className="text-tone-success-fg font-medium">
                Aceptado el {formatDateTime(consent.accepted_at)}
              </span>
            </>
          )}
        </p>
      </div>

      <div>
        <Button
          type="link"
          className="px-0!"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Ocultar el texto" : "Leer el texto completo"}
        </Button>
        <div
          id={bodyId}
          hidden={!open}
          className="bg-bg-subtle text-text-secondary mt-2 max-h-80 overflow-y-auto rounded-lg p-3 text-sm whitespace-pre-line"
        >
          {consent.body}
        </div>
      </div>

      {!accepted && (
        <Button
          type={consent.required ? "primary" : "default"}
          size="large"
          disabled={disabled}
          loading={busy}
          onClick={() => onAccept(consent)}
        >
          Acepto
        </Button>
      )}
      {accepted && !consent.required && (
        <Button size="large" disabled={disabled} loading={busy} onClick={() => onWithdraw(consent)}>
          Retirar mi consentimiento
        </Button>
      )}
    </article>
  );
}

/**
 * Consentimientos del comprador (`GET`/`POST /consents`). Mientras falte un obligatorio,
 * el resto del portal redirige aquí.
 */
export function ConsentsScreen() {
  const { applicationId, session, refreshSession } = usePortal();
  const consents = useConsents(applicationId);
  const action = useConsentAction(applicationId);
  const { modal } = App.useApp();
  const toast = useToast();
  const router = useRouter();
  // Una solicitud cerrada no admite consentimientos (`409 APPLICATION_CLOSED`).
  const closed = session.application.is_closed;

  const accept = (consent: BuyerConsent) =>
    action.mutate(
      { consent_definition_id: consent.id, action: "ACCEPTED" },
      { onSuccess: () => toast.success({ title: `Aceptaste: ${consent.title}` }) },
    );

  const withdraw = (consent: BuyerConsent) =>
    void modal.confirm({
      title: "¿Retirar tu consentimiento?",
      content: `Vas a retirar "${consent.title}". Puedes volver a aceptarlo cuando quieras.`,
      okText: "Retirar",
      cancelText: "Cancelar",
      onOk: () =>
        action.mutateAsync(
          { consent_definition_id: consent.id, action: "WITHDRAWN" },
          { onSuccess: () => toast.success({ title: `Retiraste: ${consent.title}` }) },
        ),
    });

  const pendingRequired = consents.data?.pending_required.length ?? 0;
  const canContinue = !!consents.data && pendingRequired === 0;

  return (
    <PortalPage>
      <PageHeader
        variant="portal"
        title="Antes de empezar"
        description="Lee y acepta los consentimientos para seguir con tu solicitud."
      />

      {consents.isPending && <LoadingState variant="portal" blocks={[128, 128]} />}

      {consents.isError && (
        <ErrorState
          variant="page"
          title="No pudimos cargar los consentimientos"
          message={consents.error.message}
          onRetry={() => void consents.refetch()}
          retrying={consents.isFetching}
        />
      )}

      {consents.data && (
        <div className="grid gap-3">
          {consents.data.items.map((consent) => (
            <ConsentCard
              key={consent.id}
              consent={consent}
              disabled={closed || action.isPending}
              pendingId={
                action.isPending ? (action.variables?.consent_definition_id ?? null) : null
              }
              onAccept={accept}
              onWithdraw={withdraw}
            />
          ))}
        </div>
      )}

      {consents.data && (
        <div className="grid gap-2">
          <Button
            type="primary"
            size="large"
            disabled={!canContinue}
            aria-describedby={canContinue ? undefined : "consents-pending"}
            onClick={() =>
              // Con la sesión al día, la guarda ya no manda de vuelta aquí.
              void refreshSession().then(() => router.push(PORTAL_HOME))
            }
          >
            Continuar
          </Button>
          {!canContinue && (
            <p id="consents-pending" className="text-text-secondary m-0 text-center text-sm">
              Acepta los consentimientos obligatorios para continuar.
            </p>
          )}
        </div>
      )}
    </PortalPage>
  );
}
