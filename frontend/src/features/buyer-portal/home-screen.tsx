"use client";

import { Button } from "antd";
import dynamic from "next/dynamic";
import { useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/state-views";
import { firstName, bankName, inSentence } from "@/features/buyer-portal/home-format";
import {
  AdvisorCard,
  ApplicationSection,
  BankUpdateCard,
  StatusCard,
  TodoSection,
} from "@/features/buyer-portal/home-sections";
import { usePortal } from "@/features/buyer-portal/portal-context";
import { PortalPage } from "@/features/buyer-portal/portal-shell";
import {
  useBuyerDetail,
  useBuyerSlots,
  useMonthlyIncome,
  type BuyerDocumentSlot,
} from "@/features/buyer-portal/queries";
import { useIdlePreload, useMountedOnce } from "@/lib/hooks/use-lazy";

// Fuera de la primera carga: el formulario de retiro (Zod, react-hook-form, Select) y la
// hoja de carga de documentos se piden al abrirlos (PERF-03).
const loadWithdrawModal = () => import("@/features/buyer-portal/withdraw-modal");
const loadUploadSheet = () => import("@/features/buyer-documents/upload-sheet");
const PRELOADS = [loadUploadSheet, loadWithdrawModal] as const;
const WithdrawModal = dynamic(() => loadWithdrawModal().then((m) => m.WithdrawModal));
const UploadSheet = dynamic(() => loadUploadSheet().then((m) => m.UploadSheet));

function HomeSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-5">
      <span className="sr-only" role="status">
        Cargando…
      </span>
      <div className="bg-bg-muted h-9 w-48 animate-pulse rounded-md motion-reduce:animate-none" />
      <div className="bg-bg-muted h-56 animate-pulse rounded-xl motion-reduce:animate-none" />
      <div className="bg-bg-muted h-32 animate-pulse rounded-xl motion-reduce:animate-none" />
    </div>
  );
}

/** Inicio del portal (`/portal`, mockup `portal.html`). */
export function PortalHome() {
  const { session, applicationId } = usePortal();
  const detailQuery = useBuyerDetail(applicationId);
  const slotsQuery = useBuyerSlots(applicationId);
  const detail = detailQuery.data?.detail;
  const monthlyIncome = useMonthlyIncome(applicationId, detail?.participants ?? []);
  const [withdrawing, setWithdrawing] = useState(false);
  const [uploading, setUploading] = useState<BuyerDocumentSlot | null>(null);
  useIdlePreload(PRELOADS);
  const withdrawMounted = useMountedOnce(withdrawing);
  const uploadMounted = useMountedOnce(uploading !== null);

  if (detailQuery.isPending || slotsQuery.isPending) {
    return (
      <PortalPage>
        <HomeSkeleton />
      </PortalPage>
    );
  }

  const error = detailQuery.error ?? slotsQuery.error;
  if (error || !detail || !slotsQuery.data) {
    return (
      <PortalPage>
        <ErrorState
          variant="page"
          titleAs="h1"
          title="No pudimos cargar tu solicitud"
          message={error?.message}
          onRetry={() => {
            void detailQuery.refetch();
            void slotsQuery.refetch();
          }}
          retrying={detailQuery.isFetching || slotsQuery.isFetching}
        />
      </PortalPage>
    );
  }

  const slots = slotsQuery.data;
  const version = detailQuery.data?.version ?? detail.version;
  const bank = detail.financing?.bank_product?.bank;
  const pendingDocuments = slots.filter((s) => s.needs_action).length;

  return (
    <PortalPage>
      <PageHeader
        variant="portal"
        title={`Hola, ${firstName(session.buyer.display_name)}`}
        description={
          <>
            Tu crédito de {inSentence(detail.purpose.label)}
            {bank && ` con ${bankName(bank)}`} ·{" "}
            <span className="text-text-tertiary font-mono whitespace-nowrap">{detail.code}</span>
          </>
        }
      />

      <StatusCard detail={detail} slots={slots} />
      {detail.latest_bank_update && <BankUpdateCard update={detail.latest_bank_update} />}
      <TodoSection slots={slots} onUpload={setUploading} />
      <ApplicationSection
        detail={detail}
        monthlyIncome={monthlyIncome}
        pendingDocuments={pendingDocuments}
      />
      {detail.advisor && <AdvisorCard advisor={detail.advisor} />}

      {!detail.is_closed && (
        <footer className="grid justify-items-center pb-4">
          <Button
            size="large"
            type="link"
            className="text-text-secondary! text-sm underline"
            onClick={() => setWithdrawing(true)}
          >
            Ya no quiero continuar con la solicitud
          </Button>
          {withdrawMounted && (
            <WithdrawModal
              applicationId={applicationId}
              version={version}
              open={withdrawing}
              onClose={() => setWithdrawing(false)}
            />
          )}
        </footer>
      )}
      {uploadMounted && <UploadSheet slot={uploading} onClose={() => setUploading(null)} />}
    </PortalPage>
  );
}
