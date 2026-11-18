"use client";

import Link from "next/link";
import { useMemo } from "react";

import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { partnerName } from "@/features/admin-common/partner-select";
import { PARTNER_SORT_FIELDS } from "@/features/admin-partners/list-params";
import type { Partner } from "@/features/admin-partners/queries";
import { PartnerStatusBadge } from "@/features/admin-partners/status";
import { formatDate } from "@/lib/format";

const DASH = <span className="text-text-tertiary">—</span>;

interface PartnersListProps {
  rows: Partner[];
  onOpen: (partner: Partner) => void;
  hrefOf: (partner: Partner) => string;
  busy?: boolean;
}

const helper = dataColumns<Partner>();

const makeColumns = (hrefOf: (partner: Partner) => string) =>
  helper.columns([
    helper.accessor((row) => row.legal_name, {
      id: "legal_name",
      header: "Constructora",
      cell: ({ row }) => (
        <div className="grid max-w-[280px]">
          <Link
            href={hrefOf(row.original)}
            scroll={false}
            className="text-text-link truncate font-medium no-underline hover:underline"
          >
            {partnerName(row.original)}
          </Link>
          {row.original.trade_name && (
            <span className="text-text-tertiary truncate text-xs">{row.original.legal_name}</span>
          )}
        </div>
      ),
    }),
    helper.display({
      id: "tax_id",
      header: "NIT",
      cell: ({ row }) => <span className="text-sm tabular-nums">{row.original.tax_id}</span>,
    }),
    helper.display({
      id: "contact",
      header: "Contacto",
      cell: ({ row }) => {
        const { contact_name, contact_email } = row.original;
        if (!contact_name && !contact_email) return DASH;
        return (
          <div className="grid max-w-[240px] text-sm">
            {contact_name && <span className="truncate">{contact_name}</span>}
            {contact_email && (
              <span className="text-text-secondary truncate text-xs">{contact_email}</span>
            )}
          </div>
        );
      },
    }),
    helper.display({
      id: "contact_phone",
      header: "Teléfono",
      cell: ({ row }) =>
        row.original.contact_phone ? (
          <span className="text-sm tabular-nums">{row.original.contact_phone}</span>
        ) : (
          DASH
        ),
    }),
    helper.display({
      id: "status",
      header: "Estado",
      cell: ({ row }) => <PartnerStatusBadge status={row.original.status} />,
    }),
    helper.accessor((row) => row.created_at, {
      id: "created_at",
      header: "Creada",
      cell: ({ row }) => (
        <span className="text-text-secondary text-sm">{formatDate(row.original.created_at)}</span>
      ),
    }),
  ]);

export function PartnersTable({
  rows,
  sorting,
  onSort,
  onOpen,
  hrefOf,
  busy,
}: PartnersListProps & { sorting: TableSort; onSort: (sorting: TableSort) => void }) {
  const columns = useMemo(() => makeColumns(hrefOf), [hrefOf]);
  return (
    <DataTable
      ariaLabel="Constructoras"
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      sortableFields={PARTNER_SORT_FIELDS}
      onSort={onSort}
      onOpen={onOpen}
      busy={busy}
      stickyColumn="legal_name"
    />
  );
}

export function PartnerCards({ rows, onOpen, hrefOf, busy }: PartnersListProps) {
  return (
    <CardList
      ariaLabel="Constructoras"
      rows={rows}
      getRowId={(partner) => partner.id}
      onOpen={onOpen}
      busy={busy}
      renderCard={(partner) => (
        <>
          <div className="flex items-center gap-2">
            <Link
              href={hrefOf(partner)}
              scroll={false}
              className="text-text-link min-w-0 truncate font-medium no-underline"
            >
              {partnerName(partner)}
            </Link>
            <span className="ml-auto shrink-0">
              <PartnerStatusBadge status={partner.status} />
            </span>
          </div>
          <div className="text-text-secondary flex gap-2 text-sm">
            <span className="tabular-nums">NIT {partner.tax_id}</span>
            {partner.contact_name && (
              <span className="min-w-0 truncate">· {partner.contact_name}</span>
            )}
          </div>
        </>
      )}
    />
  );
}
