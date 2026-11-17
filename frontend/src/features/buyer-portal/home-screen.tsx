"use client";

import { Button } from "antd";
import { useState } from "react";

import { UploadSheet } from "@/features/buyer-documents/upload-sheet";
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
import { WithdrawModal } from "@/features/buyer-portal/withdraw-modal";

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
        <div role="alert" className="grid justify-items-start gap-2">
          <h1 className="m-0 text-xl font-semibold">No pudimos cargar tu solicitud</h1>
          {error && <p className="text-text-secondary m-0">{error.message}</p>}
          <Button
            onClick={() => {
              void detailQuery.refetch();
              void slotsQuery.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      </PortalPage>
    );
  }

  const slots = slotsQuery.data;
  const version = detailQuery.data?.version ?? detail.version;
  const bank = detail.financing?.bank_product?.bank;
  const pendingDocuments = slots.filter((s) => s.needs_action).length;

  return (
    <PortalPage>
      <div>
        <h1 className="m-0 text-3xl font-semibold tracking-tight">
          Hola, {firstName(session.buyer.display_name)}
        </h1>
        <p className="text-text-secondary text-md mt-1 mb-0">
          Tu crédito de {inSentence(detail.purpose.label)}
          {bank && ` con ${bankName(bank)}`} ·{" "}
          <span className="text-text-tertiary font-mono whitespace-nowrap">{detail.code}</span>
        </p>
      </div>

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
            type="link"
            className="text-text-secondary! text-sm underline"
            onClick={() => setWithdrawing(true)}
          >
            Ya no quiero continuar con la solicitud
          </Button>
          <WithdrawModal
            applicationId={applicationId}
            version={version}
            open={withdrawing}
            onClose={() => setWithdrawing(false)}
          />
        </footer>
      )}
      <UploadSheet slot={uploading} onClose={() => setUploading(null)} />
    </PortalPage>
  );
}
