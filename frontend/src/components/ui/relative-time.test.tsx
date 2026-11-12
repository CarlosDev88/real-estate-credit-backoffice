import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RelativeTime } from "@/components/ui/relative-time";

describe("RelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(new Date("2026-11-11T15:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("el HTML del servidor trae la fecha absoluta (sin depender de la hora)", () => {
    const html = renderToString(<RelativeTime value="2026-11-11T14:48:00Z" />);
    expect(html).toContain("11 nov 2026");
    expect(html).toContain('dateTime="2026-11-11T14:48:00Z"');
  });

  it("en el cliente muestra la relativa, con la fecha completa en el title", () => {
    render(<RelativeTime value="2026-11-11T14:48:00Z" />);
    const time = screen.getByText("Hace 12 min");
    expect(time.tagName).toBe("TIME");
    expect(time).toHaveAttribute("title", "11 nov 2026, 09:48");
  });

  it("se actualiza sola cada minuto", () => {
    render(<RelativeTime value="2026-11-11T14:48:00Z" />);
    expect(screen.getByText("Hace 12 min")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByText("Hace 13 min")).toBeInTheDocument();
  });

  it("con una fecha inválida no pinta nada", () => {
    const { container } = render(<RelativeTime value="no-es-fecha" />);
    expect(container).toBeEmptyDOMElement();
  });
});
