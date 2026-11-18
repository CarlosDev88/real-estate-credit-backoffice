import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ActionModal } from "@/components/ui/action-modal";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Card, DataList, Datum } from "@/components/ui/card";
import { CompletenessBar, CompletenessTotal } from "@/components/ui/completeness-bar";
import { CardList, DataTable, dataColumns, type TableSort } from "@/components/ui/data-table";
import { ListPagination, rangeText } from "@/components/ui/list-pagination";
import { BackLink, PageHeader } from "@/components/ui/page-header";
import { ScrollTabs } from "@/components/ui/scroll-tabs";
import { SidePanel } from "@/components/ui/side-panel";
import { ErrorState, LoadingState } from "@/components/ui/state-views";
import { Stepper, type ProgressStage } from "@/components/ui/stepper";

describe("Card, DataList y Datum", () => {
  it("la tarjeta es una región con el nombre de su título y su acción", () => {
    render(
      <Card title="Datos del cliente" action={<button type="button">Editar</button>}>
        contenido
      </Card>,
    );
    const card = screen.getByRole("region", { name: "Datos del cliente" });
    expect(within(card).getByRole("button", { name: "Editar" })).toBeInTheDocument();
    expect(card).toHaveTextContent("contenido");
  });

  it("sin título no es una región con nombre; en el portal los hijos van directo", () => {
    const { container } = render(
      <Card variant="portal" id="seccion">
        <p>uno</p>
        <p>dos</p>
      </Card>,
    );
    const section = container.querySelector("section#seccion");
    expect(section).not.toHaveAttribute("aria-labelledby");
    expect(section?.children).toHaveLength(2);
  });

  it("los datos vacíos muestran un guion, en grilla y en línea", () => {
    const { rerender } = render(
      <DataList>
        <Datum label="Correo">ana@correo.co</Datum>
        <Datum label="Teléfono">{""}</Datum>
      </DataList>,
    );
    expect(screen.getByText("Correo").tagName).toBe("DT");
    expect(screen.getByText("—")).toBeInTheDocument();

    rerender(
      <DataList layout="inline">
        <Datum label="Banco">{null}</Datum>
      </DataList>,
    );
    expect(screen.getByText("Banco").closest("div")).toHaveClass("contents");
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("PageHeader y BackLink", () => {
  it("título, descripción, volver y acciones", () => {
    render(
      <PageHeader
        title="Clientes"
        description="Personas interesadas en un crédito."
        back={{ href: "/inicio", label: "Volver al inicio" }}
        actions={<button type="button">Nuevo cliente</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Clientes" })).toBeInTheDocument();
    expect(screen.getByText("Personas interesadas en un crédito.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute(
      "href",
      "/inicio",
    );
    expect(screen.getByRole("button", { name: "Nuevo cliente" })).toBeInTheDocument();
  });

  it("el enlace del portal es táctil (44 px)", () => {
    render(
      <BackLink href="/portal" size="touch">
        Volver
      </BackLink>,
    );
    expect(screen.getByRole("link", { name: "Volver" })).toHaveClass("min-h-11");
  });
});

describe("LoadingState y ErrorState", () => {
  it("cargando: esqueleto con un bloque por altura y el texto para el lector", () => {
    const { container } = render(<LoadingState label="Cargando clientes" blocks={[96, 64]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando clientes");
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(2);
  });

  it("cargando sin bloques: una línea de texto", () => {
    render(<LoadingState label="Cargando las respuestas…" blocks={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando las respuestas…");
  });

  it("error en sus tres formas, siempre con Reintentar", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <ErrorState variant="inline" title="No pudimos cargar." onRetry={onRetry} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar.");

    rerender(<ErrorState title="No pudimos cargar la lista" message="Sin red" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Sin red");

    rerender(
      <ErrorState
        variant="page"
        titleAs="h1"
        title="No pudimos cargar tu solicitud"
        message="Detalle"
        onRetry={onRetry}
      />,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "No pudimos cargar tu solicitud" }),
    ).toBeInTheDocument();
  });
});

describe("ActionModal", () => {
  it("confirma con el botón y con Enter, y cancela", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    render(
      <ActionModal
        open
        title="Exonerar documento"
        description="El documento deja de ser obligatorio."
        okText="Exonerar"
        onSubmit={onSubmit}
        onCancel={onCancel}
      >
        <label>
          Motivo <input name="motivo" />
        </label>
      </ActionModal>,
    );
    expect(screen.getByText("El documento deja de ser obligatorio.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Exonerar" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);

    await userEvent.type(screen.getByRole("textbox", { name: "Motivo" }), "x{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit.mock.calls[1]?.[0]).toBeDefined();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("destructiva y deshabilitada", () => {
    render(
      <ActionModal
        open
        title="Cerrar"
        okText="Cerrar mi solicitud"
        danger
        okDisabled
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    );
    const ok = screen.getByRole("button", { name: "Cerrar mi solicitud" });
    expect(ok).toBeDisabled();
    expect(ok).toHaveClass("ant-btn-dangerous");
  });
});

describe("BottomSheet y SidePanel", () => {
  it("la hoja inferior tiene título, cerrar con nombre y pie", async () => {
    const onClose = vi.fn();
    render(
      <BottomSheet
        open
        onClose={onClose}
        title="Filtros"
        closeLabel="Cerrar filtros"
        footer={<button type="button">Ver resultados</button>}
      >
        contenido
      </BottomSheet>,
    );
    expect(screen.getByText("Filtros")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ver resultados" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cerrar filtros" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("el panel lateral muestra de quién es y el título como h2 enfocable", () => {
    render(
      <SidePanel open onClose={() => {}} eyebrow="Daniel Mejía · Titular" title="Cédula">
        detalle
      </SidePanel>,
    );
    expect(screen.getByText("Daniel Mejía · Titular")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Cédula" })).toHaveAttribute(
      "tabindex",
      "-1",
    );
  });

  it("sin título (mientras se cierra) no pinta el h2", () => {
    render(
      <SidePanel open onClose={() => {}} title={undefined}>
        detalle
      </SidePanel>,
    );
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
  });
});

describe("ListPagination", () => {
  it("rango del listado", () => {
    expect(rangeText(1, 20, 0)).toBe("Sin resultados");
    expect(rangeText(2, 20, 48)).toBe("Mostrando 21–40 de 48");
    expect(rangeText(3, 20, 48)).toBe("Mostrando 41–48 de 48");
  });

  it("tamaño de página con el nombre de lo que se lista y páginas solo si hay más de una", () => {
    const { rerender } = render(
      <ListPagination
        page={1}
        pageSize={20}
        total={48}
        itemsLabel="Clientes"
        onPage={() => {}}
        onPageSize={() => {}}
      />,
    );
    expect(screen.getByRole("combobox", { name: "Clientes por página" })).toBeInTheDocument();
    expect(screen.getByText("Mostrando 1–20 de 48")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "2" })).toBeInTheDocument();

    rerender(
      <ListPagination
        page={1}
        pageSize={20}
        total={5}
        itemsLabel="Clientes"
        onPage={() => {}}
        onPageSize={() => {}}
      />,
    );
    expect(screen.queryByRole("listitem", { name: "2" })).toBeNull();
  });
});

interface Row {
  id: string;
  name: string;
  amount: number;
}

const ROWS: Row[] = [
  { id: "1", name: "Ana", amount: 10 },
  { id: "2", name: "Luis", amount: 20 },
];

const col = dataColumns<Row>();
const COLUMNS = col.columns([
  col.accessor((row) => row.name, {
    id: "name",
    header: "Nombre",
    cell: ({ row }) => <a href={`#${row.original.id}`}>{row.original.name}</a>,
  }),
  col.accessor((row) => row.amount, { id: "amount", header: "Monto" }),
  col.display({ id: "note", header: "Nota", cell: () => "—" }),
]);

function SortableTable({ onOpen }: { onOpen: (row: Row) => void }) {
  const [sorting, setSorting] = useState<TableSort>({ field: "name", desc: true });
  return (
    <>
      <DataTable
        ariaLabel="Personas"
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        sorting={sorting}
        sortableFields={["name", "amount", "note"]}
        onSort={setSorting}
        onOpen={onOpen}
        stickyColumn="name"
        alignRight={["amount"]}
      />
      <output>
        {sorting.field}:{sorting.desc ? "desc" : "asc"}
      </output>
    </>
  );
}

describe("DataTable y CardList", () => {
  it("ordena con el botón del encabezado y marca aria-sort", async () => {
    render(<SortableTable onOpen={() => {}} />);
    const table = screen.getByRole("table", { name: "Personas" });
    const nameHeader = within(table).getByRole("columnheader", { name: /Nombre/ });
    expect(nameHeader).toHaveAttribute("aria-sort", "descending");

    await userEvent.click(within(table).getByRole("button", { name: /Monto/ }));
    expect(screen.getByText("amount:desc")).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: /Monto/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    // Una columna sin `accessor` no se ordena aunque esté en la lista.
    expect(within(table).queryByRole("button", { name: /Nota/ })).toBeNull();
    expect(within(table).getByRole("columnheader", { name: "Monto" })).toHaveClass("text-right");
  });

  it("clic o Enter en la fila abre; los enlaces siguen siendo suyos", async () => {
    const onOpen = vi.fn();
    render(<SortableTable onOpen={onOpen} />);
    const rows = screen.getAllByRole("row");
    const first = rows[1] as HTMLElement;
    await userEvent.click(within(first).getByRole("cell", { name: "10" }));
    expect(onOpen).toHaveBeenCalledWith(ROWS[0]);

    await userEvent.click(screen.getByRole("link", { name: "Luis" }));
    expect(onOpen).toHaveBeenCalledTimes(1);

    act(() => (rows[2] as HTMLElement).focus());
    await userEvent.keyboard("{Enter}");
    expect(onOpen).toHaveBeenLastCalledWith(ROWS[1]);
  });

  it("sin onOpen, las filas no son interactivas ni ordenables", () => {
    render(
      <DataTable
        ariaLabel="Personas"
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        busy
      />,
    );
    const table = screen.getByRole("table", { name: "Personas" });
    expect(table).toHaveAttribute("aria-busy", "true");
    expect(within(table).queryAllByRole("button")).toHaveLength(0);
    expect(screen.getAllByRole("row")[1]).not.toHaveAttribute("tabindex");
  });

  it("tarjetas en móvil: toda la tarjeta abre, menos sus enlaces", async () => {
    const onOpen = vi.fn();
    render(
      <CardList
        ariaLabel="Personas"
        rows={ROWS}
        getRowId={(row) => row.id}
        onOpen={onOpen}
        renderCard={(row) => (
          <>
            <a href={`#${row.id}`}>{row.name}</a>
            <span>monto {row.amount}</span>
          </>
        )}
      />,
    );
    const list = screen.getByRole("list", { name: "Personas" });
    await userEvent.click(within(list).getByText("monto 10"));
    expect(onOpen).toHaveBeenCalledWith(ROWS[0]);
    await userEvent.click(within(list).getByRole("link", { name: "Luis" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

const STAGES: ProgressStage[] = [
  { code: "A", label: "Datos", state: "done", state_label: "Completa" },
  { code: "B", label: "Documentos", state: "current", state_label: "En curso" },
  { code: "C", label: "Radicación", state: "pending", state_label: "Pendiente" },
] as ProgressStage[];

describe("Stepper", () => {
  it("horizontal: región desplazable, estado en texto y la actual marcada", () => {
    render(<Stepper stages={STAGES} ariaLabel="Etapas de la solicitud" />);
    const region = screen.getByRole("region", { name: "Etapas de la solicitud" });
    expect(region).toHaveAttribute("tabindex", "0");
    const current = within(region).getByText("Documentos").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    expect(current).toHaveTextContent("Documentos: En curso");
  });

  it("vertical: lista con el estado visible", () => {
    render(<Stepper stages={STAGES} ariaLabel="Etapas" orientation="vertical" />);
    const list = screen.getByRole("list", { name: "Etapas" });
    expect(within(list).getByText("Pendiente")).toBeInTheDocument();
  });

  it("sin etapas no pinta nada", () => {
    const { container } = render(<Stepper stages={[]} ariaLabel="Etapas" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Mejoras de CompletenessBar y ScrollTabs", () => {
  it("total en el encabezado y datos y documentos lado a lado", () => {
    render(
      <Card title="Completitud del expediente" action={<CompletenessTotal percentage={81} />}>
        <CompletenessBar
          percentage={81}
          dataPercentage={100}
          documentsPercentage={62}
          documentsCompleted={10}
          documentsRequired={16}
          layout="split"
          showTotal={false}
        />
      </Card>,
    );
    const card = screen.getByRole("region", { name: "Completitud del expediente" });
    expect(within(card).getByText("81 % en total")).toBeInTheDocument();
    expect(within(card).queryByRole("progressbar", { name: "Completitud total" })).toBeNull();
    const data = within(card).getByRole("progressbar", { name: "Completitud de datos" });
    expect(data.closest(".grid")?.parentElement).toHaveClass("min-[600px]:grid-cols-2");
    expect(within(card).getByText("10 de 16 · 62 %")).toBeInTheDocument();
  });

  it("conteo con texto y en tono de advertencia", () => {
    render(
      <ScrollTabs
        ariaLabel="Secciones"
        value="resumen"
        onChange={() => {}}
        items={[
          { key: "resumen", label: "Resumen" },
          {
            key: "documentos",
            label: "Documentos",
            count: 6,
            countLabel: "6 pendientes",
            countTone: "warning",
          },
        ]}
      />,
    );
    const tab = screen.getByRole("tab", { name: "Documentos 6 pendientes" });
    expect(within(tab).getByText("6 pendientes")).toHaveClass("text-tone-warning-fg");
  });
});
