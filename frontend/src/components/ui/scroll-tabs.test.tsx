import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ScrollTabs } from "@/components/ui/scroll-tabs";

const ITEMS = [
  { key: "all", label: "Todas", count: 48 },
  { key: "waiting", label: "Esperando al comprador", count: 14 },
  { key: "review", label: "En revisión", count: 7 },
  { key: "closed", label: "Cerradas", count: null },
];

function Harness({ onChange }: { onChange: (key: string) => void }) {
  const [value, setValue] = useState("all");
  return (
    <ScrollTabs
      ariaLabel="Filtro rápido por estado"
      items={ITEMS}
      value={value}
      onChange={(key) => {
        setValue(key);
        onChange(key);
      }}
    />
  );
}

describe("ScrollTabs", () => {
  it("marca la elegida y muestra los conteos", () => {
    render(<Harness onChange={vi.fn()} />);
    expect(screen.getByRole("tablist", { name: "Filtro rápido por estado" })).toBeInTheDocument();
    const all = screen.getByRole("tab", { name: "Todas 48" });
    expect(all).toHaveAttribute("aria-selected", "true");
    expect(all).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Cerradas" })).toHaveAttribute("tabindex", "-1");
  });

  it("las flechas mueven el foco sin elegir; Enter elige", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    await user.tab();
    expect(screen.getByRole("tab", { name: "Todas 48" })).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    const waiting = screen.getByRole("tab", { name: "Esperando al comprador 14" });
    expect(waiting).toHaveFocus();
    expect(waiting).toHaveAttribute("tabindex", "0");
    expect(onChange).not.toHaveBeenCalled();

    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("waiting");
    expect(waiting).toHaveAttribute("aria-selected", "true");
  });

  it("Inicio, Fin y las flechas dan la vuelta", async () => {
    const user = userEvent.setup();
    render(<Harness onChange={vi.fn()} />);
    await user.tab();

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Cerradas" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Todas 48" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Cerradas" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Todas 48" })).toHaveFocus();
  });

  it("con clic elige directamente", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: "En revisión 7" }));
    expect(onChange).toHaveBeenCalledWith("review");
  });
});
