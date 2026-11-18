import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import Link from "next/link";
import { useState } from "react";

import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ListPagination } from "@/components/ui/list-pagination";
import { Money } from "@/components/ui/money";
import { RelativeTime } from "@/components/ui/relative-time";
import { StatusBadge } from "@/components/ui/status-badge";
import { DARK, MOBILE, minutesAgo } from "@/stories/globals";

interface Row {
  id: string;
  code: string;
  applicant: string;
  status: string;
  statusLabel: string;
  amount: number | null;
  updatedAt: string;
}

const NAMES = ["Daniel Mejía", "Ana Restrepo", "Luis Ortiz", "Marta Gil", "Juan Pérez"];
const STATES = [
  ["WAITING_DOCUMENTS", "Esperando documentos"],
  ["DOCUMENTS_REVIEW", "Revisión documental"],
  ["READY_TO_FILE", "Lista para radicar"],
  ["APPROVED", "Aprobada"],
  ["REJECTED", "Rechazada"],
] as const;

const ROWS: Row[] = Array.from({ length: 48 }, (_, i) => {
  const [status, statusLabel] = STATES[i % STATES.length] ?? STATES[0];
  return {
    id: String(i + 1),
    code: `SOL-${String(184 - i).padStart(6, "0")}`,
    applicant: NAMES[i % NAMES.length] ?? "",
    status,
    statusLabel,
    amount: i % 7 === 3 ? null : 120_000_000 + i * 7_500_000,
    updatedAt: minutesAgo(i * 95),
  };
});

const col = dataColumns<Row>();
const COLUMNS = col.columns([
  col.accessor((r) => r.code, {
    id: "code",
    header: "Código",
    cell: ({ row }) => (
      <Link
        href={`/solicitudes/${row.original.id}`}
        className="text-text-link font-mono text-sm font-medium no-underline hover:underline"
      >
        {row.original.code}
      </Link>
    ),
  }),
  col.accessor((r) => r.applicant, { id: "applicant_name", header: "Titular" }),
  col.display({
    id: "status",
    header: "Estado",
    cell: ({ row }) => (
      <StatusBadge kind="application" code={row.original.status} label={row.original.statusLabel} />
    ),
  }),
  col.accessor((r) => r.amount, {
    id: "requested_amount",
    header: "Monto",
    cell: ({ row }) => <Money value={row.original.amount} />,
  }),
  col.accessor((r) => r.updatedAt, {
    id: "updated_at",
    header: "Actualizada",
    cell: ({ row }) => (
      <RelativeTime value={row.original.updatedAt} className="text-text-secondary text-sm" />
    ),
  }),
]);

const SORTABLE = ["code", "applicant_name", "requested_amount", "updated_at"] as const;

function sortRows(rows: Row[], { field, desc }: TableSort): Row[] {
  const key: Record<string, (r: Row) => string | number> = {
    code: (r) => r.code,
    applicant_name: (r) => r.applicant,
    requested_amount: (r) => r.amount ?? 0,
    updated_at: (r) => r.updatedAt,
  };
  const get = key[field] ?? key.code!;
  return [...rows].sort((a, b) => (get(a) > get(b) ? 1 : -1) * (desc ? -1 : 1));
}

/** Simula el servidor: ordena y pagina en memoria. */
function Listado({ rows, mobile, busy }: { rows: Row[]; mobile?: boolean; busy?: boolean }) {
  const [sorting, setSorting] = useState<TableSort>({ field: "updated_at", desc: true });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const sorted = sortRows(rows, sorting);
  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  const body =
    rows.length === 0 ? (
      <EmptyState
        title="No hay solicitudes con estos filtros"
        description="Prueba con otros filtros."
      />
    ) : mobile ? (
      <CardList
        ariaLabel="Solicitudes"
        rows={visible}
        getRowId={(r) => r.id}
        onOpen={() => {}}
        busy={busy}
        renderCard={(r) => (
          <>
            <div className="flex items-center gap-2">
              <Link
                href={`/solicitudes/${r.id}`}
                className="text-text-link font-mono text-sm font-medium no-underline"
              >
                {r.code}
              </Link>
              <span className="ml-auto">
                <StatusBadge kind="application" code={r.status} label={r.statusLabel} />
              </span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="truncate">{r.applicant}</span>
              <span className="ml-auto">
                <Money value={r.amount} />
              </span>
            </div>
          </>
        )}
      />
    ) : (
      <DataTable
        ariaLabel="Solicitudes"
        columns={COLUMNS}
        rows={visible}
        getRowId={(r) => r.id}
        sorting={sorting}
        sortableFields={SORTABLE}
        onSort={(next) => {
          setSorting(next);
          setPage(1);
        }}
        onOpen={() => {}}
        busy={busy}
        stickyColumn="code"
        alignRight={["requested_amount"]}
        minWidth={720}
      />
    );

  return (
    <div className="bg-bg-surface border-border-default overflow-hidden rounded-lg border">
      {body}
      <ListPagination
        page={page}
        pageSize={pageSize}
        total={rows.length}
        itemsLabel="Solicitudes"
        onPage={setPage}
        onPageSize={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        compact={mobile}
      />
    </div>
  );
}

const meta = {
  title: "Componentes/DataTable",
  component: DataTable,
  subcomponents: { CardList, ListPagination },
  parameters: {
    docs: {
      description: {
        component:
          "Tabla de listado sobre TanStack Table. El servidor ordena y pagina: la tabla lleva el estado del orden. El orden se activa con un botón dentro del encabezado (funciona con teclado) y la flecha solo se ve en la columna ordenada. Un clic o Enter en la fila abre el detalle; los enlaces y botones de la fila siguen siendo suyos. En móvil, `CardList` (una tarjeta por fila). `ListPagination` va al pie.",
      },
    },
  },
  argTypes: {
    columns: { control: false, description: "Columnas de `dataColumns<T>()`." },
    sortableFields: { description: "Columnas que se pueden ordenar (campos de `ordering`)." },
    stickyColumn: { description: "Columna fija a la izquierda al desplazar." },
    alignRight: { description: "Columnas a la derecha (montos)." },
    busy: { control: "boolean", description: "Hay otra página en camino: las filas se atenúan." },
  },
  args: { columns: COLUMNS, rows: ROWS, getRowId: (r: Row) => r.id, ariaLabel: "Solicitudes" },
  render: (args) => <Listado rows={ROWS} busy={args.busy} />,
} satisfies Meta<typeof DataTable<Row>>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OrdenYPaginacion: Story = { name: "Orden y paginación" };
export const Cargando: Story = { name: "Cargando otra página", args: { busy: true } };
export const Vacio: Story = { name: "Vacío", render: () => <Listado rows={[]} /> };
export const UnaPagina: Story = {
  name: "Una página",
  render: () => <Listado rows={ROWS.slice(0, 4)} />,
};
export const Oscuro: Story = { globals: DARK };
/** En móvil, tarjetas en lugar de la tabla y paginación simple. */
export const Movil: Story = {
  name: "Móvil (tarjetas)",
  render: () => <Listado rows={ROWS} mobile />,
  globals: MOBILE,
};
