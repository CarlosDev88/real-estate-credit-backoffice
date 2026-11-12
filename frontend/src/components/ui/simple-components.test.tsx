import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { CompletenessBar } from "@/components/ui/completeness-bar";
import { EmptyState } from "@/components/ui/empty-state";
import { FilterChips } from "@/components/ui/filter-chips";
import { Money, MoneyInput } from "@/components/ui/money";
import { StatusBadge } from "@/components/ui/status-badge";

const NBSP = String.fromCharCode(0xa0); // espacio de no separación

describe("StatusBadge", () => {
  it("muestra el texto de la API con el tono del código", () => {
    render(<StatusBadge kind="application" code="READY_TO_FILE" label="Lista para radicar" />);
    const badge = screen.getByText("Lista para radicar");
    expect(badge).toHaveAttribute("data-tone", "accent");
  });

  it("un código desconocido cae en neutral sin romper", () => {
    render(<StatusBadge kind="application" code="ESTADO_NUEVO" label="Estado nuevo" />);
    expect(screen.getByText("Estado nuevo")).toHaveAttribute("data-tone", "neutral");
  });
});

describe("Money", () => {
  it("formatea COP con cifras tabulares", () => {
    render(<Money value={294000000} />);
    const el = screen.getByText(/294\.000\.000/);
    expect(el).toHaveClass("tabular-nums");
  });

  it("sin valor muestra el texto vacío", () => {
    render(<Money value={null} empty="Sin monto" />);
    expect(screen.getByText("Sin monto")).toBeInTheDocument();
  });
});

describe("MoneyInput", () => {
  function Controlled({ onChange }: { onChange: (v: number | null) => void }) {
    const [value, setValue] = useState<number | null>(null);
    return (
      <MoneyInput
        aria-label="Monto"
        value={value}
        onChange={(v) => {
          setValue(v);
          onChange(v);
        }}
      />
    );
  }

  it("entrega enteros y muestra el separador de miles", async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    const input = screen.getByLabelText("Monto");
    await userEvent.type(input, "294000000");
    expect(onChange).toHaveBeenLastCalledWith(294000000);
    expect(input).toHaveValue("294.000.000");
    expect(screen.getByText("COP")).toBeInTheDocument();
  });

  it("descarta lo que no son dígitos", async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Monto"), "1.5a0");
    expect(onChange).toHaveBeenLastCalledWith(150);
  });
});

describe("CompletenessBar", () => {
  it("completo: total, datos y documentos como en el mockup", () => {
    render(
      <CompletenessBar
        percentage={81}
        dataPercentage={100}
        documentsPercentage={62}
        documentsCompleted={10}
        documentsRequired={16}
      />,
    );
    // Testing Library normaliza el espacio de no separación a un espacio común.
    expect(screen.getByText("81 % en total").textContent).toBe(`81${NBSP}% en total`);
    expect(screen.getByText("10 de 16 · 62 %")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Completitud total" })).toHaveAttribute(
      "aria-valuenow",
      "81",
    );
    expect(screen.getByRole("progressbar", { name: "Completitud de datos" })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
  });

  it("mini: barra corta con el porcentaje, acotada entre 0 y 100", () => {
    render(<CompletenessBar variant="mini" percentage={140} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("140 %")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("muestra título, descripción y acción", () => {
    render(
      <EmptyState
        title="No hay solicitudes con estos filtros"
        description="Prueba con otro estado o limpia los filtros."
        action={<button type="button">Limpiar filtros</button>}
      />,
    );
    expect(screen.getByText("No hay solicitudes con estos filtros")).toBeInTheDocument();
    expect(screen.getByText("Prueba con otro estado o limpia los filtros.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
  });
});

describe("FilterChips", () => {
  const chips = [
    { key: "updated", label: "Actualizada", value: "últimos 30 días" },
    { key: "origin", label: "Origen", value: "Constructora" },
  ];

  it("sin chips no pinta nada", () => {
    const { container } = render(<FilterChips chips={[]} onRemove={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("quita un chip con su botón y limpia todo", async () => {
    const onRemove = vi.fn();
    const onClearAll = vi.fn();
    render(
      <FilterChips
        chips={chips}
        onRemove={onRemove}
        onClearAll={onClearAll}
        caption='Desde "Más filtros":'
      />,
    );
    const list = screen.getByRole("list", { name: "Filtros activos" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);

    await userEvent.click(
      screen.getByRole("button", { name: "Quitar filtro Actualizada: últimos 30 días" }),
    );
    expect(onRemove).toHaveBeenCalledWith("updated");

    await userEvent.click(screen.getByRole("button", { name: "Limpiar" }));
    expect(onClearAll).toHaveBeenCalledOnce();
  });
});
